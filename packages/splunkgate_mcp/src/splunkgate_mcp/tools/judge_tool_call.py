"""MCP tool `splunkgate_judge_tool_call` (story-mcp-03, Surface 2).

Pre-execution judgement on a downstream tool invocation. Routes
(tool_name, tool_args) through DefenseClaw's local regex pack
(`splunkgate_judges.defenseclaw_backend`) first — catches shell
injection / US SSN / 16-digit card / base64 payload in process. If
the cheap path is clean, escalates to Cisco AI Defense's Inspection
API. Returns a typed `Verdict` (`surface="mcp_judge_tool"`); on MODIFY
the `modifications.suggested_args` field carries the input dict with
PII/PCI substrings replaced by verbatim `[REDACTED:<rule>]` tokens.
EVERY input key is preserved per story-mcp-03 spec line 146.

Per the MCP spec, execution errors are reported in-band via
`isError: true`; we RAISE `AIDefenseError` / `ValidationError` and let
FastMCP convert. Per spec line 147 serialised tool_args are capped
at 64 KB; `ValidationError` fires BEFORE either backend is invoked.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict
from splunkgate_core.errors import ValidationError
from splunkgate_core.otel import emit_verdict_event
from splunkgate_core.verdict import (
    RuleHit as VerdictRuleHit,
)
from splunkgate_core.verdict import (
    Severity,
    Verdict,
    VerdictLabel,
)
from splunkgate_judges.ai_defense import AIDefenseClient
from splunkgate_judges.ai_defense_types import (
    InspectConfig,
    InspectMessage,
    InspectRequest,
)
from splunkgate_judges.defenseclaw_backend import evaluate_tool_call

if TYPE_CHECKING:
    from splunkgate_core.verdict import RuleHit as DefenseclawRuleHit
    from splunkgate_judges.ai_defense_types import InspectResponse


_LOGGER = logging.getLogger(__name__)

# Locked literals — Surface 4 dashboards filter on these exact strings.
_SURFACE: Literal["mcp_judge_tool"] = "mcp_judge_tool"
_MCP_METHOD: str = "tools/call"

# 64 KB cap on serialised tool_args (story-mcp-03 spec line 147).
_MAX_TOOL_ARGS_BYTES: Final[int] = 64 * 1024

# Cheap-pass explanation surfaces the rule-pack subset caveat per design
# doc § "DefenseClaw rule-pack fidelity". Searchable in Splunk dashboards.
_DEFENSECLAW_EXPLANATION: str = (
    "matched defenseclaw_regex subset; full rule-pack pending EPIC-08 integration."
)

# Cheap-pass rules that warrant outright BLOCK rather than MODIFY (the
# suggestion would be too dangerous to forward even with redaction).
_BLOCKING_DEFENSECLAW_RULES: Final[frozenset[str]] = frozenset({"Shell Injection"})

# Local redactor patterns. Duplicated from check_output_leak.py rather
# than imported across tool modules — keeps each tool independently
# refactorable. Consolidate into a shared helper when mcp-05 lands.
_REDACTION_PATTERNS: Final[dict[str, list[re.Pattern[str]]]] = {
    "PII": [
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # US SSN
        re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),  # email
        re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),  # US phone
    ],
    "PCI": [
        re.compile(r"\b(?:\d[ -]*?){12,18}\d\b"),
    ],
    "PHI": [
        re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
        re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b"),
    ],
}


class JudgeToolCallInputs(BaseModel):
    """Input arguments for `splunkgate_judge_tool_call`.

    `tool_args` is the JSON-shaped arg dict the agent would pass;
    opaque per spec line 147, capped at 64 KB by `_validate_size`.
    """

    model_config = ConfigDict(extra="forbid")

    tool_name: str
    tool_args: dict[str, object]


def _validate_size(tool_args: dict[str, object]) -> str:
    """Serialise tool_args + enforce the 64 KB cap. Return the JSON string."""
    serialised = json.dumps(tool_args, ensure_ascii=False, sort_keys=True)
    byte_len = len(serialised.encode("utf-8"))
    if byte_len > _MAX_TOOL_ARGS_BYTES:
        msg = f"tool_args exceeds 64 KB cap ({byte_len} > {_MAX_TOOL_ARGS_BYTES} bytes)"
        raise ValidationError(msg)
    return serialised


def _redact_string(text: str, rule: str) -> str:
    """Substitute matched substrings for `rule` with `[REDACTED:<rule>]`.

    Rules without patterns (e.g. `Base64 Payload`, `Shell Injection`)
    pass through unchanged — those rules don't have a sensible
    substring substitution; their MODIFY path is best-effort.
    """
    token = f"[REDACTED:{rule}]"
    patterns = _REDACTION_PATTERNS.get(rule, [])
    redacted = text
    for pattern in patterns:
        redacted = pattern.sub(token, redacted)
    return redacted


def _redact_value(value: object, rule: str) -> object:
    """Walk a JSON-shaped value and redact every string leaf for `rule`.

    Preserves the structural shape: dicts stay dicts, lists stay lists,
    scalars stay scalars. Only string leaves get the regex substitution.
    Makes spec line 146 hold — EVERY input key survives.
    """
    if isinstance(value, str):
        return _redact_string(value, rule)
    if isinstance(value, dict):
        return {k: _redact_value(v, rule) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_value(v, rule) for v in value]
    if isinstance(value, tuple):
        return tuple(_redact_value(v, rule) for v in value)
    return value


def _build_suggested_args(
    tool_args: dict[str, object],
    rules: list[str],
) -> dict[str, object]:
    """Apply every rule's redactor patterns over the input dict.

    Multiple rule hits compose: PII redactor runs, then PCI redactor
    runs on the partially-redacted result. EVERY original key is
    preserved per spec line 146 — only values get substring-substituted.
    """
    out: dict[str, object] = dict(tool_args)
    for rule in rules:
        out = {k: _redact_value(v, rule) for k, v in out.items()}
    return out


def _verdict_from_defenseclaw_hit(
    *,
    hit: DefenseclawRuleHit,
    tool_args: dict[str, object],
    trace_id: UUID,
    started: float,
) -> Verdict:
    """Route a cheap-first-pass DefenseClaw match to a Verdict.

    Shell Injection → BLOCK + HIGH (no suggested_args). Base64 Payload
    → REVIEW + MEDIUM (human-in-the-loop). PII / PCI → MODIFY + MEDIUM
    + suggested_args with regex substitution.
    """
    if hit.rule in _BLOCKING_DEFENSECLAW_RULES:
        label, severity = VerdictLabel.BLOCK, Severity.HIGH
        modifications: dict[str, object] | None = None
    elif hit.rule == "Base64 Payload":
        label, severity = VerdictLabel.REVIEW, Severity.MEDIUM
        modifications = None
    else:
        label, severity = VerdictLabel.MODIFY, Severity.MEDIUM
        modifications = {"suggested_args": _build_suggested_args(tool_args, [hit.rule])}
    return Verdict(
        trace_id=trace_id,
        timestamp=datetime.now(UTC),
        verdict=label,
        severity=severity,
        rules=[hit],
        explanation=_DEFENSECLAW_EXPLANATION,
        modifications=modifications,
        surface=_SURFACE,
        latency_ms=(time.perf_counter() - started) * 1000,
    )


def _build_inspect_request(serialised_args: str, tool_name: str) -> InspectRequest:
    """Compose the AI Defense Inspection request for a tool-call judgement.

    Role is `"user"` — the (tool_name, tool_args) pair represents what
    the agent (acting on user instruction) is asking to do.
    """
    body = f"tool_name={tool_name}\ntool_args={serialised_args}"
    return InspectRequest(
        messages=[InspectMessage(role="user", content=body)],
        metadata={},
        config=InspectConfig(),
    )


def _map_aidefense_to_verdict_label(
    *,
    is_safe: bool,
    severity: Severity,
) -> VerdictLabel:
    """Map (is_safe, severity) → VerdictLabel for the escalation path.

    Mirror of score_prompt_injection (mcp-02). is_safe=False with
    severity=NONE_SEVERITY logs a contradiction WARN and defaults to
    ALLOW so the protocol violation is visible in dashboards.
    """
    if is_safe:
        return VerdictLabel.ALLOW
    if severity is Severity.HIGH:
        return VerdictLabel.BLOCK
    if severity is Severity.MEDIUM:
        return VerdictLabel.REVIEW
    if severity is Severity.LOW:
        return VerdictLabel.MODIFY
    _LOGGER.warning(
        "ai_defense.contradiction",
        extra={
            "issue": "is_safe=False with severity=NONE_SEVERITY",
            "resolution": "defaulting to ALLOW",
        },
    )
    return VerdictLabel.ALLOW


def _verdict_from_aidefense(
    *,
    response: InspectResponse,
    tool_args: dict[str, object],
    trace_id: UUID,
    started: float,
) -> Verdict:
    """Translate an InspectResponse into the tool's Verdict shape.

    On MODIFY, suggested_args preserves every input key (spec line 146);
    every fired rule's redactor composes over the values.
    """
    rules: list[VerdictRuleHit] = [
        VerdictRuleHit(rule=hit.rule_name.value, confidence=1.0, source="ai_defense")
        for hit in response.rules
    ]
    classifications: list[str] = [c.value for c in response.classifications]
    label = _map_aidefense_to_verdict_label(
        is_safe=response.is_safe,
        severity=response.severity,
    )
    modifications: dict[str, object] | None = None
    if label is VerdictLabel.MODIFY:
        rule_names = [hit.rule_name.value for hit in response.rules]
        modifications = {"suggested_args": _build_suggested_args(tool_args, rule_names)}
    return Verdict(
        trace_id=trace_id,
        timestamp=datetime.now(UTC),
        verdict=label,
        severity=response.severity,
        rules=rules,
        explanation=response.explanation,
        classifications=classifications,
        modifications=modifications,
        surface=_SURFACE,
        latency_ms=(time.perf_counter() - started) * 1000,
    )


async def _call_ai_defense(
    *,
    serialised_args: str,
    tool_name: str,
    trace_id: UUID,
) -> InspectResponse:
    """Call AI Defense via the env-resolved client."""
    request = _build_inspect_request(serialised_args, tool_name)
    client = AIDefenseClient.from_env()
    try:
        return await client.inspect_chat(request, trace_id=str(trace_id))
    finally:
        await client.aclose()


def _allow_verdict(*, trace_id: UUID, started: float) -> Verdict:
    """Build the ALLOW verdict when both the cheap path and AI Defense are clean."""
    return Verdict(
        trace_id=trace_id,
        timestamp=datetime.now(UTC),
        verdict=VerdictLabel.ALLOW,
        severity=Severity.NONE_SEVERITY,
        rules=[],
        explanation="defenseclaw_regex clean; ai_defense clean",
        surface=_SURFACE,
        latency_ms=(time.perf_counter() - started) * 1000,
    )


async def judge_tool_call(args: JudgeToolCallInputs) -> Verdict:
    """Judge a downstream tool invocation; return a typed Verdict.

    Logic:
      1. Cap serialised tool_args at 64 KB (spec line 147) — raise
         `ValidationError` BEFORE invoking either backend.
      2. Cheap first pass via `defenseclaw_backend.evaluate_tool_call`.
         Match → return the routed cheap-pass Verdict.
      3. Else escalate to AI Defense. Map (is_safe, severity) →
         VerdictLabel.
      4. Always emit exactly one `gen_ai.evaluation.result` OTel event
         before returning.

    Raises `AIDefenseError` / `ValidationError` on judge-side failure
    or input violation — FastMCP converts to in-band `isError: true`.
    """
    trace_id = uuid4()
    started = time.perf_counter()

    serialised = _validate_size(args.tool_args)

    cheap_hit = await evaluate_tool_call(args.tool_name, args.tool_args)
    if cheap_hit is not None:
        verdict = _verdict_from_defenseclaw_hit(
            hit=cheap_hit,
            tool_args=args.tool_args,
            trace_id=trace_id,
            started=started,
        )
        _safe_emit(verdict)
        return verdict

    response = await _call_ai_defense(
        serialised_args=serialised,
        tool_name=args.tool_name,
        trace_id=trace_id,
    )
    if response.is_safe:
        verdict = _allow_verdict(trace_id=trace_id, started=started)
    else:
        verdict = _verdict_from_aidefense(
            response=response,
            tool_args=args.tool_args,
            trace_id=trace_id,
            started=started,
        )
    _safe_emit(verdict)
    return verdict


def _safe_emit(verdict: Verdict) -> None:
    """Emit OTel event without letting observability failures lose the verdict.

    Per silent-failure-hunter on PR #116/#117: an exporter crash would
    otherwise propagate out of the tool and drop the verdict on the
    floor. Catch broadly, log, continue. Duplicated from the prior
    tools per the implementer brief; consolidate when mcp-05 lands.
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

    Mirrors `score_prompt_injection.register` and `check_output_leak.register`.
    `server_module` is the imported `splunkgate_mcp.server`; accepted as
    `object` here to keep the import graph one-way.
    """
    register_tool = server_module.register_tool  # type: ignore[attr-defined]
    register_tool(
        name="splunkgate_judge_tool_call",
        fn=judge_tool_call,
        description=(
            "Judge a downstream tool invocation (tool_name + tool_args) "
            "before the agent executes it. Routes through DefenseClaw's "
            "local regex rule-pack first (shell injection / PII / PCI / "
            "Base64), then escalates ambiguous cases to Cisco AI Defense. "
            "Returns a typed Verdict; on MODIFY, modifications.suggested_args "
            "carries the same input keys with dangerous substrings replaced "
            "by [REDACTED:<rule>] tokens. Surface='mcp_judge_tool'."
        ),
    )
