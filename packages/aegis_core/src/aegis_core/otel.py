"""OTel GenAI `gen_ai.evaluation.result` event emitter.

Every Aegis surface calls emit_verdict_event(verdict, ...) after rendering a
Verdict. The function attaches a span event with the four standardized
gen_ai.evaluation.* slots (per ../context/10-standards/02-otel-genai-
semantic-conventions.md), plus three aegis-custom attrs (`aegis.surface`,
`aegis.rules`, `aegis.trace_id`), plus the MCP sub-convention attrs
(`mcp.method.name`, `mcp.session.id`) when the call originated from MCP.

The four `gen_ai.evaluation.*` slots are spec; the aegis.* attrs are
namespaced so they don't collide with future upstream gen_ai.* additions.

Per architecture.md § "Open architectural questions" item 3, the score.label
values block/allow/modify/review are custom; we propose this upstream
post-hackathon.
"""

from uuid import UUID

from opentelemetry import trace

from aegis_core.verdict import Severity, Verdict

EVALUATION_NAME = "aegis.safety_verdict"

_SEVERITY_SCORE: dict[Severity, float] = {
    Severity.NONE_SEVERITY: 0.0,
    Severity.LOW: 0.33,
    Severity.MEDIUM: 0.66,
    Severity.HIGH: 1.0,
}


# OTel attribute values may be str | int | float | bool | list of those —
# narrow to the union we actually use to keep mypy --strict clean.
AttrValue = str | int | float | bool | list[str]


def severity_to_score(severity: Severity) -> float:
    """Map Verdict.severity to a monotonic float score in [0.0, 1.0]."""
    return _SEVERITY_SCORE[severity]


def _build_attributes(
    verdict: Verdict,
    *,
    mcp_method_name: str | None,
    mcp_session_id: UUID | None,
) -> dict[str, AttrValue]:
    """Compose the event attributes per OTel GenAI conventions + Aegis custom."""
    attrs: dict[str, AttrValue] = {
        "gen_ai.evaluation.name": EVALUATION_NAME,
        "gen_ai.evaluation.score.value": severity_to_score(verdict.severity),
        "gen_ai.evaluation.score.label": verdict.verdict.value.lower(),
        "aegis.surface": verdict.surface,
        "aegis.rules": [hit.rule for hit in verdict.rules],
        "aegis.trace_id": str(verdict.trace_id),
    }
    if verdict.explanation is not None:
        attrs["gen_ai.evaluation.explanation"] = verdict.explanation
    if mcp_method_name is not None:
        attrs["mcp.method.name"] = mcp_method_name
    if mcp_session_id is not None:
        attrs["mcp.session.id"] = str(mcp_session_id)
    return attrs


def emit_verdict_event(
    verdict: Verdict,
    *,
    mcp_method_name: str | None = None,
    mcp_session_id: UUID | None = None,
) -> None:
    """Attach a `gen_ai.evaluation.result` event to the current span.

    Idempotent if no active span exists — OTel returns a NonRecordingSpan
    whose add_event is a no-op. Downstream collectors handle no-op events
    correctly.
    """
    span = trace.get_current_span()
    attrs = _build_attributes(
        verdict,
        mcp_method_name=mcp_method_name,
        mcp_session_id=mcp_session_id,
    )
    span.add_event("gen_ai.evaluation.result", attributes=attrs)
