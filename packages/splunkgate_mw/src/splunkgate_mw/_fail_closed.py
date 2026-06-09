"""Fail-closed plumbing for SafetyToolMiddleware (story-mw-02 fix round).

Per silent-failure-hunter on PR #121, a dependent-service crash (DefenseClaw
backend raising, AI Defense network error, OTel exporter crash) would
otherwise propagate out of `judge_tool_call`, bypass the BLOCK / MODIFY
branch in `tool_middleware`, and drop the audit row for a dangerous
attempted call. This module owns the conversions that keep
`judge_tool_call` total + the OTel emission resilient:

  - `FailClosedError`       : sentinel control-flow exception
  - `run_cheap_pass`        : DefenseClaw call, wraps crashes
  - `run_escalation`        : AI Defense call, wraps AIDefenseError variants
  - `fail_closed_verdict`   : builds the BLOCK Verdict the outer catch returns
  - `cheap_hit_severity`    : maps cheap rule name → fail-closed severity rank
  - `safe_emit`             : OTel emit wrapper that never lets exporter crashes
                              lose the verdict

Split from `tool_middleware.py` to stay under the 400-LOC cap; logic is
unchanged from the inlined version.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog
from splunkgate_core.otel import emit_verdict_event
from splunkgate_core.verdict import RuleHit, Severity, Verdict, VerdictLabel
from splunkgate_judges._errors import AIDefenseError
from splunkgate_judges.defenseclaw_backend import evaluate_tool_call

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from splunkgate_judges.ai_defense_types import InspectResponse
    from splunklib.ai.messages import ToolCall

    from splunkgate_mw.tool_middleware import AIDefenseLike

__all__ = [
    "FailClosedError",
    "cheap_hit_severity",
    "fail_closed_verdict",
    "run_cheap_pass",
    "run_escalation",
    "safe_emit",
]

_SURFACE = "mw_tool"

_logger = structlog.get_logger(__name__)


@dataclass
class FailClosedError(Exception):
    """Control-flow signal: produce a fail-closed BLOCK verdict.

    Raised by `run_cheap_pass` / `run_escalation` when a dependent
    service fails. `judge_tool_call` catches at the outer boundary and
    converts to a Verdict via `fail_closed_verdict` so the audit row +
    OTel event are preserved.
    """

    synthetic_rule: str
    severity: Severity
    explanation: str
    cheap_hit: RuleHit | None


def cheap_hit_severity(rule: str) -> Severity:
    """Map a DefenseClaw cheap-hit rule to its fail-closed severity rank."""
    if rule == "Shell Injection":
        return Severity.HIGH
    return Severity.MEDIUM


def fail_closed_verdict(
    fc: FailClosedError,
    *,
    trace_uuid: UUID,
    now: datetime,
    latency_ms: float,
) -> Verdict:
    """Build a fail-closed BLOCK verdict carrying a synthetic operations rule.

    Operators can SPL-filter on the synthetic rule to triage operational
    failures (`ai_defense_unavailable`, `defenseclaw_backend_unavailable`)
    vs. real attempted attacks.
    """
    synthetic = RuleHit(rule=fc.synthetic_rule, confidence=1.0, source="defenseclaw_regex")
    rules = [fc.cheap_hit, synthetic] if fc.cheap_hit is not None else [synthetic]
    return Verdict(
        trace_id=trace_uuid,
        timestamp=now,
        verdict=VerdictLabel.BLOCK,
        severity=fc.severity,
        rules=rules,
        modifications=None,
        surface=_SURFACE,
        latency_ms=latency_ms,
        explanation=fc.explanation,
    )


async def run_cheap_pass(
    call: ToolCall,
    tool_args: dict[str, object],
    trace_uuid: UUID,
) -> RuleHit | None:
    """Run DefenseClaw cheap pass; raise `FailClosedError` on backend exception."""
    try:
        return await evaluate_tool_call(call.name, tool_args)
    except Exception as exc:
        # Backend failure MUST fail-closed, not silently ALLOW. Catch broadly
        # so a future regex-compile / lookup-table error can't bypass the row.
        _logger.warning(
            "defenseclaw.backend_failed",
            trace_id=str(trace_uuid),
            tool_name=call.name,
            error=type(exc).__name__,
            exc_info=True,
        )
        raise FailClosedError(
            synthetic_rule="defenseclaw_backend_unavailable",
            severity=Severity.MEDIUM,
            explanation=f"DefenseClaw backend failed ({type(exc).__name__}) — failing closed",
            cheap_hit=None,
        ) from exc


async def run_escalation(
    call: ToolCall,
    cheap_hit: RuleHit,
    ai_defense: AIDefenseLike,
    trace_uuid: UUID,
) -> InspectResponse:
    """Escalate to AI Defense; raise `FailClosedError` on AIDefenseError."""
    from splunkgate_judges.ai_defense_types import (  # noqa: PLC0415 — lazy import
        InspectConfig,
        InspectMessage,
        InspectRequest,
    )

    from splunkgate_mw._serialization import (  # noqa: PLC0415 — break import cycle
        serialize_tool_call,
    )

    try:
        body = serialize_tool_call(call)
        req = InspectRequest(
            messages=[InspectMessage(role="user", content=body)],
            metadata={"tool_name": call.name},
            config=InspectConfig(),
        )
        return await ai_defense.inspect_chat(req, trace_id=str(trace_uuid))
    except AIDefenseError as exc:
        _logger.warning(
            "ai_defense.escalation_failed",
            trace_id=str(trace_uuid),
            tool_name=call.name,
            error=type(exc).__name__,
            exc_info=True,
        )
        raise FailClosedError(
            synthetic_rule="ai_defense_unavailable",
            severity=cheap_hit_severity(cheap_hit.rule),
            explanation=(
                f"DefenseClaw cheap-hit on {cheap_hit.rule!r}; "
                f"AI Defense escalation failed ({type(exc).__name__}) — failing closed"
            ),
            cheap_hit=cheap_hit,
        ) from exc


def safe_emit(verdict: Verdict) -> None:
    """Emit OTel verdict event without letting exporter failures lose the verdict.

    Per silent-failure-hunter on PR #116/#117 + PR #121: an exporter
    crash would otherwise propagate out of `tool_middleware`, bypass the
    BLOCK / MODIFY branch, and drop the verdict on the floor.
    """
    try:
        emit_verdict_event(verdict)
    except Exception:  # noqa: BLE001 — observability must never lose the verdict
        _logger.warning(
            "otel.emit_failed",
            trace_id=str(verdict.trace_id),
            surface=verdict.surface,
            exc_info=True,
        )
