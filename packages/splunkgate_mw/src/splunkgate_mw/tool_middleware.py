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

Backend failures (DefenseClaw crash, AI Defense network error, OTel
exporter crash) DO NOT propagate; they get converted to fail-closed
BLOCK verdicts so the audit row is preserved. A network blip CANNOT
silently let a dangerous tool call through. See `_fail_closed.py`.
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
from splunkgate_core.verdict import RuleHit, Severity, Verdict, VerdictLabel
from splunklib.ai.middleware import AgentMiddleware, ToolRequest, ToolResponse

from splunkgate_mw._fail_closed import (
    FailClosedError,
    fail_closed_verdict,
    run_cheap_pass,
    run_escalation,
    safe_emit,
)
from splunkgate_mw._sanitize import compose_sanitized, is_supported_rule, sanitize_args
from splunkgate_mw.config import Config
from splunkgate_mw.profiles import Profile, resolve_profile

if TYPE_CHECKING:
    from uuid import UUID

    from splunkgate_judges.ai_defense_types import InspectRequest, InspectResponse


__all__ = [
    "AIDefenseLike",
    "SafetyToolMiddleware",
    "judge_tool_call",
]

_logger = structlog.get_logger(__name__)

_SURFACE = "mw_tool"

_MSG_MISSING_SANITIZED_ARGS = (
    "MODIFY verdict on tool call missing modifications['sanitized_args']; "
    "the contract requires sanitized args when label is MODIFY"
)

_MSG_EMPTY_SANITIZED_ARGS = "MODIFY produced empty sanitized_args for non-empty input"


class AIDefenseLike(Protocol):
    """Duck-typed AI Defense client surface; satisfied by every concrete client class."""

    async def inspect_chat(
        self, request: InspectRequest, *, trace_id: str | None = None
    ) -> InspectResponse:
        """POST /api/v1/inspect/chat — returns parsed InspectResponse."""


ToolMiddlewareHandler = Callable[[ToolRequest], Awaitable[ToolResponse]]


@dataclass(frozen=True, kw_only=True)
class _VerdictCtx:
    """Bundle the identity fields every verdict-build helper needs."""

    trace_uuid: UUID
    now: datetime
    latency_ms: float
    tool_args: dict[str, object]
    tool_name: str


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
    entry — AI Defense rules append after. If AI Defense returns any rule
    outside our v1 redactor map (Code Detection, Harassment, etc.), the
    MODIFY branch would silently ship byte-identical sanitized_args (the
    PR #117 `_redact` no-op shape). Force BLOCK instead — fail closed
    rather than ship a dangerous payload that looks redacted.
    """
    if response.is_safe:
        return _cheap_only_verdict(cheap_hit, ctx)
    ai_defense_rules = [
        RuleHit(rule=str(r.rule_name.value), confidence=1.0, source="ai_defense")
        for r in response.rules
    ]
    severity = Severity(response.severity.value)
    rule_names = [str(r.rule_name.value) for r in response.rules]
    unmapped = [r for r in rule_names if not is_supported_rule(r)]
    explanation: str | None
    if cheap_hit.rule == "Shell Injection" or severity is Severity.HIGH or unmapped:
        if unmapped:
            _logger.warning(
                "compose_sanitized.unmapped_rule_forced_block",
                trace_id=str(ctx.trace_uuid),
                tool_name=ctx.tool_name,
                unmapped_rules=unmapped,
            )
            explanation = (
                f"AI Defense rules {unmapped} have no v1 redactor — "
                "failing closed instead of MODIFY"
            )
        else:
            explanation = response.explanation
        label = VerdictLabel.BLOCK
        modifications: dict[str, object] | None = None
    else:
        label = VerdictLabel.MODIFY
        modifications = {"sanitized_args": compose_sanitized(ctx.tool_args, rule_names)}
        explanation = response.explanation
    return Verdict(
        trace_id=ctx.trace_uuid,
        timestamp=ctx.now,
        verdict=label,
        severity=severity,
        rules=[cheap_hit, *ai_defense_rules],
        modifications=modifications,
        surface=_SURFACE,
        latency_ms=ctx.latency_ms,
        explanation=explanation,
    )


def _build_ctx(
    *,
    trace_uuid: UUID,
    now: datetime,
    started: float,
    tool_args: dict[str, object],
    tool_name: str,
) -> _VerdictCtx:
    return _VerdictCtx(
        trace_uuid=trace_uuid,
        now=now,
        latency_ms=(time.perf_counter() - started) * 1000,
        tool_args=tool_args,
        tool_name=tool_name,
    )


async def judge_tool_call(
    request: ToolRequest,
    profile: Profile,
    config: Config,
    ai_defense: AIDefenseLike | None = None,
) -> Verdict:
    """Pure verdict producer — NEVER raises on BLOCK, NEVER calls a handler.

    Routes (call.name, call.args) through DefenseClaw's cheap rule-pack;
    if a hit fires + `config.escalate_on_first_pass_hit` is True + an
    `ai_defense` client is wired, escalates to AI Defense Inspection API.
    Returns ALLOW when cheap path is clean — AI Defense is NOT called
    on clean payloads (would burn the 10M/year quota for no signal gain).

    Backend failures convert to fail-closed BLOCK via `_fail_closed.run_*`
    helpers. `profile` is bound to the structlog context for now.
    """
    call = request.call
    trace_uuid = uuid4()
    now = datetime.now(UTC)
    started = time.perf_counter()
    tool_args = dict(call.args)

    try:
        cheap_hit = await run_cheap_pass(call, tool_args, trace_uuid)

        if cheap_hit is None:
            latency_ms = (time.perf_counter() - started) * 1000
            _logger.debug(
                "tool_middleware.allow",
                trace_id=str(trace_uuid),
                tool_name=call.name,
                profile=profile.name,
            )
            return _allow_verdict(trace_uuid, now, latency_ms)

        ctx = _build_ctx(
            trace_uuid=trace_uuid,
            now=now,
            started=started,
            tool_args=tool_args,
            tool_name=call.name,
        )

        if not config.escalate_on_first_pass_hit or ai_defense is None:
            return _cheap_only_verdict(cheap_hit, ctx)

        response = await run_escalation(call, cheap_hit, ai_defense, trace_uuid)
        ctx = _build_ctx(
            trace_uuid=trace_uuid,
            now=now,
            started=started,
            tool_args=tool_args,
            tool_name=call.name,
        )
        return _ai_defense_verdict(response, cheap_hit, ctx)
    except FailClosedError as fc:
        return fail_closed_verdict(
            fc,
            trace_uuid=trace_uuid,
            now=now,
            latency_ms=(time.perf_counter() - started) * 1000,
        )


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
        self._profile = resolve_profile(profile)
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
        safe_emit(verdict)

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

    Raises SplunkGateError if `sanitized_args` is missing OR empty when
    the original args were non-empty — silently passing through original
    args OR shipping `{}` to the downstream tool both defeat the MODIFY
    contract.
    """
    mods = verdict.modifications or {}
    sanitized = mods.get("sanitized_args")
    if not isinstance(sanitized, dict):
        raise SplunkGateError(_MSG_MISSING_SANITIZED_ARGS)
    if not sanitized and request.call.args:
        _logger.warning(
            "modify.empty_sanitized_args",
            trace_id=str(verdict.trace_id),
            tool_name=request.call.name,
            original_keys=sorted(request.call.args.keys()),
        )
        raise SplunkGateError(_MSG_EMPTY_SANITIZED_ARGS)
    new_call = replace(request.call, args=sanitized)
    return replace(request, call=new_call)
