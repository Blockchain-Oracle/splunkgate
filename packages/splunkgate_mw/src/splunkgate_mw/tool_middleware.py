"""SafetyToolMiddleware — tool-call interception with DefenseClaw + AI Defense escalation.

Surface 1 counterpart to the MCP `splunkgate_judge_tool_call` tool. Wires
the same DefenseClaw → Cisco AI Defense escalation chain into the
splunklib.ai middleware lifecycle, so tool calls flowing through any
agent constructed with `Agent(tool_middleware=[SafetyToolMiddleware(...)])`
are judged before they execute.

Per-label branch:
  - ALLOW  → pass through to `await handler(request)`.
  - BLOCK  → emit OTel verdict, raise `ToolBlockedBySplunkGate(verdict)`;
             the inner handler is NEVER called.
  - MODIFY → reissue the tool with `verdict.modifications["sanitized_args"]`;
             the original args never reach the downstream tool.

The runtime backend `splunkgate_judges.defenseclaw_backend.evaluate_tool_call`
is the cheap first-pass classifier. When it hits + the caller configured
`escalate_on_first_pass_hit=True`, this module escalates to Cisco AI
Defense's Inspection API for the authoritative verdict, mirroring the
SafetyModelMiddleware pattern in `model_middleware.py`.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol
from uuid import uuid4

import structlog
from splunkgate_core.errors import SplunkGateError, ToolBlockedBySplunkGate
from splunkgate_core.otel import emit_verdict_event
from splunkgate_core.verdict import RuleHit, Severity, Verdict, VerdictLabel
from splunkgate_judges.defenseclaw_backend import evaluate_tool_call
from splunklib.ai.middleware import AgentMiddleware, ToolRequest, ToolResponse

from splunkgate_mw._sanitize import compose_sanitized, sanitize_args
from splunkgate_mw._serialization import serialize_tool_call
from splunkgate_mw.config import Config
from splunkgate_mw.profiles import Profile

if TYPE_CHECKING:
    from uuid import UUID

    from splunkgate_judges.ai_defense_types import InspectRequest, InspectResponse
    from splunklib.ai.messages import ToolCall


__all__ = [
    "AIDefenseLike",
    "SafetyToolMiddleware",
    "judge_tool_call",
]

_logger = structlog.get_logger(__name__)

# Surface alias is locked: every Verdict from this chain reports
# `surface="mw_tool"` so Splunk dashboards filtering on the literal
# stay stable across releases.
_SURFACE = "mw_tool"

_MSG_MISSING_SANITIZED_ARGS = (
    "MODIFY verdict on tool call missing modifications['sanitized_args']; "
    "the contract requires sanitized args when label is MODIFY"
)


class AIDefenseLike(Protocol):
    """Duck-typed AI Defense client surface; satisfied by every concrete client class."""

    async def inspect_chat(
        self, request: InspectRequest, *, trace_id: str | None = None
    ) -> InspectResponse:
        """POST /api/v1/inspect/chat — returns parsed InspectResponse."""


ToolMiddlewareHandler = Callable[[ToolRequest], Awaitable[ToolResponse]]


@dataclass(frozen=True, kw_only=True)
class _VerdictCtx:
    """Bundle the four identity fields every verdict-build helper needs."""

    trace_uuid: UUID
    now: datetime
    latency_ms: float
    tool_args: dict[str, object]


def _allow_verdict(trace_uuid: UUID, now: datetime, latency_ms: float) -> Verdict:
    """Build the ALLOW verdict when both cheap path and AI Defense are clean."""
    return Verdict(
        trace_id=trace_uuid,
        timestamp=now,
        verdict=VerdictLabel.ALLOW,
        severity=Severity.NONE_SEVERITY,
        rules=[],
        surface=_SURFACE,
        latency_ms=latency_ms,
    )


def _cheap_only_verdict(hit: RuleHit, ctx: _VerdictCtx) -> Verdict:
    """Route a cheap-only DefenseClaw match to a Verdict (no AI Defense call).

    Shell Injection → BLOCK + HIGH (no sanitized_args — too catastrophic
    to redact-and-forward). PII / PCI → MODIFY + MEDIUM with sanitized_args
    carrying the input keys preserved + dangerous substrings replaced.
    Base64 Payload → BLOCK + MEDIUM (refuses to redact opaque binary).
    """
    if hit.rule == "Shell Injection":
        label, severity = VerdictLabel.BLOCK, Severity.HIGH
        modifications: dict[str, object] | None = None
    elif hit.rule == "Base64 Payload":
        label, severity = VerdictLabel.BLOCK, Severity.MEDIUM
        modifications = None
    else:
        label, severity = VerdictLabel.MODIFY, Severity.MEDIUM
        modifications = {"sanitized_args": sanitize_args(ctx.tool_args, hit.rule)}
    return Verdict(
        trace_id=ctx.trace_uuid,
        timestamp=ctx.now,
        verdict=label,
        severity=severity,
        rules=[hit],
        modifications=modifications,
        surface=_SURFACE,
        latency_ms=ctx.latency_ms,
        explanation=f"defenseclaw_regex hit on {hit.rule!r}",
    )


def _ai_defense_verdict(
    response: InspectResponse,
    cheap_hit: RuleHit,
    ctx: _VerdictCtx,
) -> Verdict:
    """Translate an AI Defense escalation response into a Verdict.

    The cheap-pass DefenseClaw hit is always preserved as the first rule
    entry — AI Defense rules append after. This gives operators a clear
    audit trail: "DefenseClaw caught it first, AI Defense confirmed it."
    """
    if response.is_safe:
        # AI Defense cleared a DefenseClaw cheap hit. Conservative: respect
        # the cheap-pass match and keep the BLOCK/MODIFY branch — the
        # rule-pack subset is intentionally narrow + high-precision.
        return _cheap_only_verdict(cheap_hit, ctx)
    ai_defense_rules = [
        RuleHit(rule=str(r.rule_name.value), confidence=1.0, source="ai_defense")
        for r in response.rules
    ]
    severity = Severity(response.severity.value)
    if cheap_hit.rule == "Shell Injection" or severity is Severity.HIGH:
        label = VerdictLabel.BLOCK
        modifications: dict[str, object] | None = None
    else:
        label = VerdictLabel.MODIFY
        rule_names = [str(r.rule_name.value) for r in response.rules]
        modifications = {"sanitized_args": compose_sanitized(ctx.tool_args, rule_names)}
    return Verdict(
        trace_id=ctx.trace_uuid,
        timestamp=ctx.now,
        verdict=label,
        severity=severity,
        rules=[cheap_hit, *ai_defense_rules],
        modifications=modifications,
        surface=_SURFACE,
        latency_ms=ctx.latency_ms,
        explanation=response.explanation,
    )


async def _escalate_to_ai_defense(
    *,
    call: ToolCall,
    ai_defense: AIDefenseLike,
    trace_uuid: UUID,
) -> InspectResponse:
    """Compose + POST the Inspection request via the injected client."""
    from splunkgate_judges.ai_defense_types import (  # noqa: PLC0415 — lazy import
        InspectConfig,
        InspectMessage,
        InspectRequest,
    )

    body = serialize_tool_call(call)
    req = InspectRequest(
        messages=[InspectMessage(role="user", content=body)],
        metadata={"tool_name": call.name},
        config=InspectConfig(),
    )
    return await ai_defense.inspect_chat(req, trace_id=str(trace_uuid))


async def judge_tool_call(
    request: ToolRequest,
    profile: Profile,
    config: Config,
    ai_defense: AIDefenseLike | None = None,
) -> Verdict:
    """Pure verdict producer — NEVER raises on BLOCK, NEVER calls a handler.

    Routes (call.name, call.args) through DefenseClaw's cheap rule-pack;
    if a hit fires + `config.escalate_on_first_pass_hit` is True + an
    `ai_defense` client is wired, escalates to AI Defense Inspection API
    for the authoritative verdict. Otherwise routes the cheap hit directly
    via `_cheap_only_verdict`. Returns ALLOW when cheap path is clean —
    AI Defense is NOT called on clean payloads (would burn the 10M/year
    quota for no signal gain).

    `profile` is bound only to the structlog context for now — the profile
    registry (story-mw-07) will tune rule weights here later.
    """
    call = request.call
    trace_uuid = uuid4()
    now = datetime.now(UTC)
    started = time.perf_counter()
    tool_args = dict(call.args)

    cheap_hit = await evaluate_tool_call(call.name, tool_args)

    if cheap_hit is None:
        latency_ms = (time.perf_counter() - started) * 1000
        _logger.debug(
            "tool_middleware.allow",
            trace_id=str(trace_uuid),
            tool_name=call.name,
            profile=profile.name,
        )
        return _allow_verdict(trace_uuid, now, latency_ms)

    if not config.escalate_on_first_pass_hit or ai_defense is None:
        ctx = _VerdictCtx(
            trace_uuid=trace_uuid,
            now=now,
            latency_ms=(time.perf_counter() - started) * 1000,
            tool_args=tool_args,
        )
        return _cheap_only_verdict(cheap_hit, ctx)

    response = await _escalate_to_ai_defense(
        call=call,
        ai_defense=ai_defense,
        trace_uuid=trace_uuid,
    )
    ctx = _VerdictCtx(
        trace_uuid=trace_uuid,
        now=now,
        latency_ms=(time.perf_counter() - started) * 1000,
        tool_args=tool_args,
    )
    return _ai_defense_verdict(response, cheap_hit, ctx)


class SafetyToolMiddleware(AgentMiddleware):  # type: ignore[misc]
    """Tool-call safety wrap for splunklib.ai 3.0.0 agents.

    Inspects every tool invocation via DefenseClaw cheap regex + optional
    Cisco AI Defense escalation. Per-label branch:
      - ALLOW  → pass through to the inner handler.
      - BLOCK  → emit OTel verdict, raise ToolBlockedBySplunkGate.
      - MODIFY → reissue the tool with verdict.modifications["sanitized_args"].

    The middleware does NOT swallow downstream handler exceptions — only
    the rule-engine path is wrapped. Anything from `await handler(request)`
    propagates verbatim to the agent loop.
    """

    def __init__(
        self,
        *,
        profile: str | Profile = "default",
        config: Config | None = None,
        ai_defense: AIDefenseLike | None = None,
    ) -> None:
        """Wire profile + config + optional AI Defense client (None = no escalation)."""
        self._config: Config = config if config is not None else Config()
        self._profile = (
            profile if isinstance(profile, Profile) else Profile(name=profile, description="")
        )
        self._ai_defense = ai_defense
        self._logger = structlog.get_logger("SafetyToolMiddleware").bind(profile=self._profile.name)

    async def tool_middleware(
        self,
        request: ToolRequest,
        handler: ToolMiddlewareHandler,
    ) -> ToolResponse:
        """Run judge → emit OTel → branch on label → delegate / block / sanitize."""
        verdict = await judge_tool_call(
            request,
            self._profile,
            self._config,
            self._ai_defense,
        )
        emit_verdict_event(verdict)

        if verdict.verdict is VerdictLabel.BLOCK:
            self._logger.warning(
                "tool_blocked",
                trace_id=str(verdict.trace_id),
                tool_name=request.call.name,
                rules=[r.rule for r in verdict.rules],
                severity=verdict.severity.value,
            )
            raise ToolBlockedBySplunkGate(verdict)

        if verdict.verdict is VerdictLabel.MODIFY:
            sanitized_request = _rewrite_request(request, verdict)
            self._logger.info(
                "tool_modified",
                trace_id=str(verdict.trace_id),
                tool_name=request.call.name,
                rules=[r.rule for r in verdict.rules],
            )
            return await handler(sanitized_request)

        return await handler(request)


def _rewrite_request(request: ToolRequest, verdict: Verdict) -> ToolRequest:
    """Replace request.call.args with verdict.modifications['sanitized_args'].

    Raises SplunkGateError if `sanitized_args` is missing — silently passing
    through original args would defeat the MODIFY contract.
    """
    mods = verdict.modifications or {}
    sanitized = mods.get("sanitized_args")
    if not isinstance(sanitized, dict):
        raise SplunkGateError(_MSG_MISSING_SANITIZED_ARGS)
    new_call = replace(request.call, args=sanitized)
    return replace(request, call=new_call)
