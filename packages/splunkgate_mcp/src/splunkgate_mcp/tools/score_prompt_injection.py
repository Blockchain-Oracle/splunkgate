"""MCP tool `splunkgate_score_prompt_injection` (story-mcp-02, Surface 2).

Routes input through the cheap-first-pass classifier (`splunklib.ai.security.
detect_injection` — 9 verbatim regexes per ADR-010) before optionally
escalating to Cisco AI Defense's Inspection API. Returns a typed `Verdict`
whose `surface` is the literal `"mcp_score"` per docs/architecture.md §
"API schemas".

The typed `-> Verdict` return is load-bearing: FastMCP introspects the
annotation to derive `outputSchema = Verdict.model_json_schema()`, which
is the wire-truth contract tested by story-mcp-01.

Per the MCP spec (`context/10-standards/01-mcp-spec-deep.md`), tool
execution errors are reported in-band via `isError: true` on the result,
NOT as JSON-RPC errors. We honour that by RAISING `AIDefenseError` (or
subclasses) on judge-side failure — FastMCP's lowlevel
`CallToolRequest` handler catches the exception and converts to a
`CallToolResult(isError=True, content=[TextContent(...)])` per
`mcp/server/lowlevel/server.py:584`. This keeps the typed `-> Verdict`
contract intact for the happy path while still surfacing failures as
in-band errors on the wire.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from splunkgate_core.otel import emit_verdict_event
from splunkgate_core.verdict import RuleHit, Severity, Verdict, VerdictLabel
from splunkgate_judges.ai_defense import AIDefenseClient
from splunkgate_judges.ai_defense_types import (
    InspectConfig,
    InspectMessage,
    InspectRequest,
)
from splunklib.ai.security import detect_injection

if TYPE_CHECKING:
    from splunkgate_judges.ai_defense_types import InspectResponse


# Locked literal per docs/architecture.md § "API schemas" + story-mcp-02.
# Do NOT parametrise — Surface 4 dashboard filters key off this string.
_LOGGER = logging.getLogger(__name__)

# Narrow Literal so mypy enforces alignment with `Verdict.surface: Surface`.
# Caught by type-design-analyzer on PR #116.
_SURFACE: Literal["mcp_score"] = "mcp_score"

# MCP method name lives on the enclosing span as `mcp.method.name`; we
# pass it into emit_verdict_event so the OTel event carries the same
# attribute pair `gen_ai.evaluation.result` + `mcp.method.name`.
_MCP_METHOD: str = "tools/call"

_CHEAP_PASS_EXPLANATION: str = "splunklib.security clean"  # noqa: S105 — diagnostic string, not a secret


class ScoreInputs(BaseModel):
    """Input arguments for `splunkgate_score_prompt_injection`.

    `context` is the optional agent-metadata dict (e.g. `{"agent_id": "...",
    "tool_being_called": "..."}`). Passed unchanged into the AI Defense
    request's `metadata` field; `context["agent_id"]`, when a string,
    populates `Verdict.agent_id` for the Splunk ES Risk-Based Alerting
    correlation contract.

    NOTE: `context["trace_id"]` is currently NOT honored — the tool always
    generates a fresh `uuid4()` for `Verdict.trace_id`. Caller-supplied
    correlation IDs intended to tie the verdict to an upstream span must
    be passed via the OTel context (W3C trace-context headers), not via
    this dict. (Caught by silent-failure-hunter on PR #116.)
    """

    model_config = ConfigDict(extra="forbid")

    input_text: str
    context: dict[str, object] | None = Field(default=None)


def _coerce_agent_id(context: dict[str, object] | None) -> str | None:
    """Return `context['agent_id']` if it's a string, else None.

    Defensive narrowing: the input dict is typed `dict[str, object]` so
    Pydantic accepts arbitrary JSON values; mypy refuses to call
    `str(...)` on `object` without a runtime guard.
    """
    if context is None:
        return None
    agent_id = context.get("agent_id")
    if isinstance(agent_id, str):
        return agent_id
    return None


def _allow_verdict_from_cheap_pass(
    *,
    trace_id: UUID,
    started: float,
    agent_id: str | None,
) -> Verdict:
    """Build the cheap-first-pass ALLOW verdict (no AI Defense call)."""
    return Verdict(
        trace_id=trace_id,
        timestamp=datetime.now(UTC),
        verdict=VerdictLabel.ALLOW,
        severity=Severity.NONE_SEVERITY,
        rules=[],
        explanation=_CHEAP_PASS_EXPLANATION,
        classifications=[],
        surface=_SURFACE,
        latency_ms=(time.perf_counter() - started) * 1000,
        agent_id=agent_id,
    )


def _map_aidefense_to_verdict_label(
    *,
    is_safe: bool,
    severity: Severity,
) -> VerdictLabel:
    """Map (is_safe, severity) → VerdictLabel per story-mcp-02 routing rules.

    - is_safe=True              → ALLOW (defer-to-judge clean signal)
    - is_safe=False, HIGH       → BLOCK
    - is_safe=False, MEDIUM     → REVIEW (escalate to human / secondary check)
    - is_safe=False, LOW        → MODIFY (per spec default; the modifier
      surface decides what to redact)
    - is_safe=False, NONE       → ALLOW + WARN (contradictory upstream signal:
      "not safe" but no severity assigned is a real protocol violation we
      should see, not silently swallow — caught by silent-failure-hunter
      on PR #116).
    """
    if is_safe:
        return VerdictLabel.ALLOW
    if severity is Severity.HIGH:
        return VerdictLabel.BLOCK
    if severity is Severity.MEDIUM:
        return VerdictLabel.REVIEW
    if severity is Severity.LOW:
        return VerdictLabel.MODIFY
    # is_safe=False AND severity=NONE — log so the contradiction is
    # visible in Splunk dashboards instead of disappearing into the floor.
    _LOGGER.warning(
        "ai_defense.contradiction",
        extra={
            "issue": "is_safe=False with severity=NONE_SEVERITY",
            "resolution": "defaulting to ALLOW",
        },
    )
    return VerdictLabel.ALLOW


def _build_inspect_request(
    *,
    input_text: str,
    context: dict[str, object] | None,
) -> InspectRequest:
    """Compose the AI Defense Inspection request.

    Per docs/architecture.md soft rules, `metadata` is opaque
    pass-through — the API doesn't constrain its shape beyond JSON-
    serialisable values.
    """
    metadata: dict[str, object] = dict(context) if context else {}
    return InspectRequest(
        messages=[InspectMessage(role="user", content=input_text)],
        metadata=metadata,
        config=InspectConfig(),
    )


def _build_verdict_from_inspect_response(
    *,
    response: InspectResponse,
    trace_id: UUID,
    started: float,
    agent_id: str | None,
) -> Verdict:
    """Translate an InspectResponse into our Verdict shape."""
    rules: list[RuleHit] = [
        RuleHit(rule=hit.rule_name.value, confidence=1.0, source="ai_defense")
        for hit in response.rules
    ]
    classifications: list[str] = [c.value for c in response.classifications]
    label = _map_aidefense_to_verdict_label(
        is_safe=response.is_safe,
        severity=response.severity,
    )
    return Verdict(
        trace_id=trace_id,
        timestamp=datetime.now(UTC),
        verdict=label,
        severity=response.severity,
        rules=rules,
        explanation=response.explanation,
        classifications=classifications,
        surface=_SURFACE,
        latency_ms=(time.perf_counter() - started) * 1000,
        agent_id=agent_id,
    )


async def _escalate_to_ai_defense(
    *,
    input_text: str,
    context: dict[str, object] | None,
    trace_id: UUID,
) -> InspectResponse:
    """Call AI Defense via the env-resolved client.

    `AIDefenseClient.from_env()` returns the live client when
    `SPLUNKGATE_AI_DEFENSE_API_KEY` is set (typical production); the
    env-var branch selecting the deterministic in-memory alternative
    used in dev + tests lives in `splunkgate_judges.ai_defense` and is
    out of scope for this tool — we just call `from_env()` and let it
    pick the right implementation. Both implement the same async
    `inspect_chat` + `aclose` surface so no concrete-type widening is
    needed here.
    """
    request = _build_inspect_request(input_text=input_text, context=context)
    client = AIDefenseClient.from_env()
    try:
        return await client.inspect_chat(request, trace_id=str(trace_id))
    finally:
        await client.aclose()


async def score_prompt_injection(args: ScoreInputs) -> Verdict:
    """Score `args.input_text` for prompt-injection risk; return a `Verdict`.

    Logic per ADR-010:
    1. Cheap first pass: `splunklib.ai.security.detect_injection`. If it
       returns False, short-circuit with ALLOW + NONE_SEVERITY (no AI
       Defense network call).
    2. Otherwise escalate to Cisco AI Defense Inspection. Map (is_safe,
       severity) → VerdictLabel via `_map_aidefense_to_verdict_label`.
    3. Always emit exactly one `gen_ai.evaluation.result` OTel event on
       the current span before returning.

    Raises `AIDefenseError` (or subclasses) on judge-side failure —
    FastMCP's lowlevel handler converts the exception to an in-band
    `isError: true` result per the MCP spec.
    """
    trace_id = uuid4()
    started = time.perf_counter()
    agent_id = _coerce_agent_id(args.context)

    cheap_hit = detect_injection(args.input_text)
    if not cheap_hit:
        verdict = _allow_verdict_from_cheap_pass(
            trace_id=trace_id,
            started=started,
            agent_id=agent_id,
        )
        _safe_emit(verdict)
        return verdict

    response = await _escalate_to_ai_defense(
        input_text=args.input_text,
        context=args.context,
        trace_id=trace_id,
    )
    verdict = _build_verdict_from_inspect_response(
        response=response,
        trace_id=trace_id,
        started=started,
        agent_id=agent_id,
    )
    _safe_emit(verdict)
    return verdict


def _safe_emit(verdict: Verdict) -> None:
    """Emit OTel event without letting observability failures lose the verdict.

    Per silent-failure-hunter on PR #116: an exporter crash or malformed-
    attribute error during `emit_verdict_event` would otherwise propagate
    out of the tool and drop the verdict on the floor. Catch broadly,
    log, and continue — the verdict the user paid for survives.
    """
    try:
        emit_verdict_event(verdict, mcp_method_name=_MCP_METHOD)
    except Exception:  # noqa: BLE001 — observability must never lose the verdict
        _LOGGER.warning(
            "otel.emit_failed",
            extra={"trace_id": str(verdict.trace_id), "surface": verdict.surface},
            exc_info=True,
        )


def register(server_module: object) -> None:
    """Register this tool on the SplunkGate MCP server's registry.

    Indirection through a module-level `register(server)` keeps the
    server bootstrap loop import-symmetric across tool modules and lets
    tests reset + re-register without touching server.py internals.

    The `server_module` parameter is the imported `splunkgate_mcp.server`
    module; we accept it as `object` here to keep the import graph
    one-way (server.py imports tool modules, tool modules do NOT import
    server.py — they call back through the passed-in module reference).
    """
    register_tool = server_module.register_tool  # type: ignore[attr-defined]
    register_tool(
        name="splunkgate_score_prompt_injection",
        fn=score_prompt_injection,
        description=(
            "Score input_text for prompt-injection risk. Routes through "
            "splunklib's cheap regex classifier, then escalates ambiguous "
            "cases to Cisco AI Defense's Inspection API. Returns a typed "
            "Verdict (ALLOW/BLOCK/MODIFY/REVIEW) with surface='mcp_score'."
        ),
    )
