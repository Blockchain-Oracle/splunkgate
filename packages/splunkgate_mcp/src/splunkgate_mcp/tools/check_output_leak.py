"""MCP tool `splunkgate_check_output_leak` (story-mcp-04, Surface 2).

Post-inference leak check: routes `output_text` through Cisco AI Defense
with a sensitivity-profile-driven subset of the PII/PHI/PCI rules, and
returns a typed `Verdict` whose `surface` is the literal
`"mcp_check_output"` per docs/architecture.md § "API schemas". On MODIFY
the `modifications.redacted_output` field carries the same text with
matched substrings replaced by the verbatim `[REDACTED:<rule_name>]`
tokens that Surface 4 dashboards grep.

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
import re
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal, get_args
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict
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
    AIDefenseRule,
    EnabledRule,
    InspectConfig,
    InspectMessage,
    InspectRequest,
)

if TYPE_CHECKING:
    from splunkgate_judges.ai_defense_types import (
        InspectResponse,
    )
    from splunkgate_judges.ai_defense_types import (
        RuleHit as InspectRuleHit,
    )


_LOGGER = logging.getLogger(__name__)

# Narrow Literal so mypy enforces alignment with `Verdict.surface: Surface`.
# Locked per docs/architecture.md § "API schemas" + story-mcp-04 line 148.
# Surface 4 dashboard filters key off this exact string — do NOT parametrise.
_SURFACE: Literal["mcp_check_output"] = "mcp_check_output"

# MCP method name lives on the enclosing span as `mcp.method.name`; we
# pass it into emit_verdict_event so the OTel event carries the same
# attribute pair `gen_ai.evaluation.result` + `mcp.method.name`.
_MCP_METHOD: str = "tools/call"

# Sensitivity profile alias — single source of truth shared between the
# Pydantic input model, the helper signatures, and the _SENSITIVITY_RULES
# dict key type. Adding a new profile means updating the Literal once;
# the module-level totality assertion below catches drift if the
# corresponding _SENSITIVITY_RULES entry is missing.
Sensitivity = Literal["default", "fsi", "hipaa", "pubsec"]


# Sensitivity → enabled_rules mapping per story spec lines 143-147.
# Locked: dashboards key off the (surface, sensitivity) pair to size the
# leak-rate panels; changing this map breaks the contract with story-app-05.
_SENSITIVITY_RULES: dict[Sensitivity, list[AIDefenseRule]] = {
    "default": [AIDefenseRule.PII],
    "fsi": [AIDefenseRule.PII, AIDefenseRule.PCI],
    "hipaa": [AIDefenseRule.PII, AIDefenseRule.PHI],
    "pubsec": [AIDefenseRule.PII],
}


# Totality guard: every Sensitivity literal MUST have a corresponding
# _SENSITIVITY_RULES entry. Caught by type-design-analyzer on PR #117 —
# adding a new profile to the Literal but forgetting the dict entry
# would otherwise raise KeyError only at the first call site, not at
# module import. We raise instead of `assert` because production code
# is subject to ruff S101 (no asserts) per CLAUDE.md.
_DECLARED_PROFILES = set(get_args(Sensitivity))
_MAPPED_PROFILES = set(_SENSITIVITY_RULES.keys())
if _DECLARED_PROFILES != _MAPPED_PROFILES:
    msg = (
        f"_SENSITIVITY_RULES keys {_MAPPED_PROFILES} drift from "
        f"Sensitivity Literal {_DECLARED_PROFILES}"
    )
    raise RuntimeError(msg)


# v1 regex patterns keyed by AI Defense rule. The token format
# `[REDACTED:<rule_name>]` is LOCKED by story-mcp-04 spec line 149 —
# Surface 4 dashboards grep for these exact strings to count
# redactions per sourcetype, so the format MUST stay verbatim.
#
# AI Defense's InspectResponse does NOT carry substring offsets, so we
# do the substitution ourselves keyed by which rule fired. The patterns
# below cover the BDD test cases + the common shapes; future stories
# may extend them (e.g. SWIFT codes, IBANs).
_REDACTION_PATTERNS: dict[AIDefenseRule, list[re.Pattern[str]]] = {
    AIDefenseRule.PII: [
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # US SSN
        re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),  # email
        # US phone (with or without country code, hyphen/dot/space-separated)
        re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    ],
    AIDefenseRule.PHI: [
        # DOB-shaped tokens (YYYY-MM-DD and M/D/YYYY). Per story spec line 58
        # the BDD case is "DOB + diagnosis pattern" — AI Defense classifies
        # PHI; we redact the DOB shape (the easiest verifiable substring).
        re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
        re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b"),
    ],
    AIDefenseRule.PCI: [
        # 13-19 digit card number, optionally space-or-dash separated.
        # Spec doesn't require Luhn validation — AI Defense already
        # confirmed PCI, so we just need to redact the shape.
        re.compile(r"\b(?:\d[ -]*?){12,18}\d\b"),
    ],
}


class CheckOutputLeakInputs(BaseModel):
    """Input arguments for `splunkgate_check_output_leak`.

    `output_text` is the candidate text the agent is about to surface to
    the user (or hand to a downstream tool). `sensitivity` selects the
    enabled-rules profile per story spec lines 143-147 — default covers
    PII only; `fsi` adds PCI; `hipaa` adds PHI; `pubsec` is PII-only
    (the deeper PubSec profile lives in S1 middleware, EPIC-06).
    """

    model_config = ConfigDict(extra="forbid")

    output_text: str
    sensitivity: Sensitivity = "default"


def _build_inspect_request(
    *,
    output_text: str,
    sensitivity: Sensitivity,
) -> InspectRequest:
    """Compose the AI Defense Inspection request for an output-leak check.

    Role is `"assistant"` because the text being inspected is what the
    agent (assistant) is about to emit. Per the API docs this lets
    Cisco's classifier apply its output-side heuristics (e.g. weighting
    PHI signals higher when the speaker is a model, not a user).
    """
    enabled = [EnabledRule(rule_name=r) for r in _SENSITIVITY_RULES[sensitivity]]
    return InspectRequest(
        messages=[InspectMessage(role="assistant", content=output_text)],
        metadata={},
        config=InspectConfig(enabled_rules=enabled),
    )


def _redact(output_text: str, rules: list[InspectRuleHit]) -> str:
    """Replace matched substrings with `[REDACTED:<rule_name>]`.

    For each rule_name the InspectResponse flagged, run our regex set
    for that rule over `output_text` and substitute matches with the
    verbatim redaction token. The token format and the three rule names
    are LOCKED by story-mcp-04 spec line 149 — Splunk dashboards grep
    these tokens to count redactions per sourcetype.

    Rules with no patterns in `_REDACTION_PATTERNS` (e.g. Code Detection
    on the output side) pass through unchanged — AI Defense confirmed
    the hit but we don't have a v1 substring redactor for them; the
    Verdict still reports MODIFY so the caller knows to act.

    **Silent-failure guard** (PR #117 silent-failure-hunter finding):
    if a rule HAS patterns but NONE matched, AI Defense disagrees with
    our regex set — a real regex-coverage gap. Log WARN so the gap is
    visible in dashboards instead of silently shipping unredacted text
    in `Verdict.modifications.redacted_output`.
    """
    redacted = output_text
    for hit in rules:
        token = f"[REDACTED:{hit.rule_name.value}]"
        patterns = _REDACTION_PATTERNS.get(hit.rule_name, [])
        if not patterns:
            # Rule has no v1 redactor (e.g. Code Detection). Caller still
            # sees MODIFY; redacted_output equals output. Acceptable.
            continue
        before = redacted
        for pattern in patterns:
            redacted = pattern.sub(token, redacted)
        if redacted == before:
            # AI Defense fired but every pattern missed — surface the
            # regex-coverage gap instead of silently leaking the text
            # that Surface 4 dashboards will display as "redacted".
            _LOGGER.warning(
                "redaction.miss",
                extra={
                    "rule": hit.rule_name.value,
                    "entity_types": list(hit.entity_types),
                    "issue": "AI Defense fired but no client-side pattern matched",
                    "resolution": "redacted_output left unchanged; widen "
                    "_REDACTION_PATTERNS for this rule",
                },
            )
    return redacted


# Rule classes for the BLOCK-on-HIGH routing decision (spec line 152):
# "catastrophic rules" = PII/PCI/PHI, where HIGH severity should never
# leave the system even with redaction. MODIFY is the default
# (preserves agent utility) for non-HIGH severities on these rules.
_CATASTROPHIC_RULES: frozenset[AIDefenseRule] = frozenset(
    {AIDefenseRule.PII, AIDefenseRule.PCI, AIDefenseRule.PHI},
)


def _map_aidefense_to_verdict_label(response: InspectResponse) -> VerdictLabel:
    """Map InspectResponse → VerdictLabel per story-mcp-04 routing rules.

    - is_safe=True → ALLOW (pass-through, no modifications)
    - is_safe=False + HIGH severity on any catastrophic rule (PII/PCI/PHI)
      → BLOCK (never let this out; policy says HIGH means refusal)
    - is_safe=False + any other severity → MODIFY (default — preserves
      agent utility by returning the redacted text instead of refusing)
    """
    if response.is_safe:
        return VerdictLabel.ALLOW
    if response.severity is Severity.HIGH and any(
        hit.rule_name in _CATASTROPHIC_RULES for hit in response.rules
    ):
        return VerdictLabel.BLOCK
    return VerdictLabel.MODIFY


def _build_verdict_from_inspect_response(
    *,
    response: InspectResponse,
    output_text: str,
    trace_id: UUID,
    started: float,
) -> Verdict:
    """Translate an InspectResponse into our Verdict shape.

    On MODIFY (the default for any leak hit below HIGH severity on a
    catastrophic rule), populate `modifications.redacted_output` with
    the post-redaction text so the caller can use it inline without a
    second round-trip. ALLOW returns the verdict with no modifications;
    BLOCK includes the redacted view as well so audit dashboards can
    show the operator what the agent tried to emit.
    """
    rules: list[VerdictRuleHit] = [
        VerdictRuleHit(rule=hit.rule_name.value, confidence=1.0, source="ai_defense")
        for hit in response.rules
    ]
    classifications: list[str] = [c.value for c in response.classifications]
    label = _map_aidefense_to_verdict_label(response)
    modifications: dict[str, object] | None = None
    if label is VerdictLabel.MODIFY or label is VerdictLabel.BLOCK:
        modifications = {"redacted_output": _redact(output_text, response.rules)}
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
    output_text: str,
    sensitivity: Sensitivity,
    trace_id: UUID,
) -> InspectResponse:
    """Call AI Defense via the env-resolved client.

    `AIDefenseClient.from_env()` returns the live client when
    `SPLUNKGATE_AI_DEFENSE_API_KEY` is set (typical production); the
    env-var branch selecting the deterministic in-memory alternative
    used in dev + tests lives in `splunkgate_judges.ai_defense` and is
    out of scope for this tool — we just call `from_env()` and let it
    pick the right implementation. Both implement the same async
    `inspect_chat` + `aclose` surface.
    """
    request = _build_inspect_request(output_text=output_text, sensitivity=sensitivity)
    client = AIDefenseClient.from_env()
    try:
        return await client.inspect_chat(request, trace_id=str(trace_id))
    finally:
        await client.aclose()


async def check_output_leak(args: CheckOutputLeakInputs) -> Verdict:
    """Inspect `args.output_text` for PII/PHI/PCI leaks; return a `Verdict`.

    Logic per story spec § Notes (line 152):
    1. Always call AI Defense (no cheap-pass shortcut — there's no
       splunklib regex equivalent for leak detection; the cheap
       redaction patterns we own are only used POST-classification to
       generate the `redacted_output` token-substituted string).
    2. Map (is_safe, severity, rules) → VerdictLabel:
       - is_safe=True → ALLOW
       - is_safe=False + HIGH on catastrophic rule → BLOCK
       - is_safe=False otherwise → MODIFY (default — preserves utility)
    3. On MODIFY/BLOCK, populate `Verdict.modifications.redacted_output`
       with the same text but with PII/PHI/PCI substrings replaced by
       `[REDACTED:<rule>]` tokens (verbatim, dashboard-grep-friendly).
    4. Always emit exactly one `gen_ai.evaluation.result` OTel event on
       the current span before returning.

    Raises `AIDefenseError` (or subclasses) on judge-side failure —
    FastMCP's lowlevel handler converts the exception to an in-band
    `isError: true` result per the MCP spec.
    """
    trace_id = uuid4()
    started = time.perf_counter()
    response = await _call_ai_defense(
        output_text=args.output_text,
        sensitivity=args.sensitivity,
        trace_id=trace_id,
    )
    verdict = _build_verdict_from_inspect_response(
        response=response,
        output_text=args.output_text,
        trace_id=trace_id,
        started=started,
    )
    _safe_emit(verdict)
    return verdict


def _safe_emit(verdict: Verdict) -> None:
    """Emit OTel event without letting observability failures lose the verdict.

    Per silent-failure-hunter on PR #116: an exporter crash or malformed-
    attribute error during `emit_verdict_event` would otherwise propagate
    out of the tool and drop the verdict on the floor. Catch broadly,
    log, and continue — the verdict the user paid for survives.

    Duplicated from `score_prompt_injection._safe_emit` per the implementer
    brief: mcp-05 may need a different shape (the audit tool can attach
    extra trace attributes), so we don't extract a shared helper yet.
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

    Mirrors `score_prompt_injection.register` exactly. The `server_module`
    parameter is the imported `splunkgate_mcp.server` module; we accept
    it as `object` here to keep the import graph one-way (server.py
    imports tool modules; tool modules do NOT import server.py — they
    call back through the passed-in module reference).
    """
    register_tool = server_module.register_tool  # type: ignore[attr-defined]
    register_tool(
        name="splunkgate_check_output_leak",
        fn=check_output_leak,
        description=(
            "Inspect output_text for PII/PHI/PCI leaks via Cisco AI Defense. "
            "Returns a typed Verdict; on MODIFY/BLOCK, modifications.redacted_output "
            "carries the same text with leaks replaced by [REDACTED:<rule>] tokens. "
            "Sensitivity profiles: default (PII), fsi (+PCI), hipaa (+PHI), pubsec (PII). "
            "Surface='mcp_check_output'."
        ),
    )
