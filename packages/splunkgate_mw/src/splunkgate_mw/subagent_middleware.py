"""SafetySubagentMiddleware — subagent-call interception with per-subagent profile + trace_id propagation.

Surface 1 counterpart for subagent boundaries. Mirrors `tool_middleware.py`
in shape but:

- The verdict surface is `mw_subagent`.
- `per_subagent_profile: dict[str, str | Profile]` lets users say
  "the draft-writer subagent runs at financial_services strictness while
  the parent stays on default." Resolution order:
  `per_subagent_profile[call.name] -> self.profile -> "default"`.
- `trace_id` is pulled from the parent's contextvars binding via
  `splunkgate_core.trace.current_trace_id()` (set by story-mw-06's
  SafetyAgentMiddleware), NOT freshly generated. Every Verdict emitted
  for a single parent invocation — parent + all subagent calls — shares
  the parent's trace_id. Fresh UUID only when no parent context exists
  (top-level invocation in tests, or middleware used standalone).
- BLOCK raises `splunkgate_core.errors.SubagentBlockedBySplunkGate(verdict)`;
  the inner handler is NEVER called.
- MODIFY only applies to dict-args (per SubagentCall.args: str | dict).
  When args are a string the rule pack would have to redact-in-place and
  v1 lacks that contract; we fail-closed by raising BLOCK instead. The
  AI Defense MODIFY-but-unmapped-rule fail-closed path inherits from
  tool_middleware.compose_sanitized via `is_supported_rule`.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from uuid import UUID, uuid4

import structlog
from splunkgate_core.errors import SplunkGateError, SubagentBlockedBySplunkGate
from splunkgate_core.trace import current_trace_id
from splunkgate_core.verdict import RuleHit, Severity, Verdict, VerdictLabel
from splunklib.ai.middleware import AgentMiddleware, SubagentRequest, SubagentResponse

from splunkgate_mw._fail_closed import (
    FailClosedError,
    fail_closed_verdict,
    run_cheap_pass,
    run_escalation,
    safe_emit,
)
from splunkgate_mw._sanitize import compose_sanitized, is_supported_rule, sanitize_args
from splunkgate_mw.config import Config
from splunkgate_mw.profiles import Profile, log_if_custom_profile_shadows_canonical, resolve_profile

if TYPE_CHECKING:
    from splunkgate_judges.ai_defense_types import InspectResponse
    from splunklib.ai.messages import SubagentCall

    from splunkgate_mw.tool_middleware import AIDefenseLike

__all__ = [
    "SafetySubagentMiddleware",
    "judge_subagent_call",
]

_logger = structlog.get_logger(__name__)
_SURFACE = "mw_subagent"

_MSG_MISSING_SANITIZED_ARGS = (
    "MODIFY verdict on subagent call missing modifications['sanitized_args']; "
    "the contract requires sanitized args when label is MODIFY"
)
_MSG_STRING_ARGS_MODIFY_NOT_SUPPORTED = (
    "MODIFY on a string-args subagent call is not supported in v1; fail-closed BLOCK instead"
)

SubagentMiddlewareHandler = Callable[[SubagentRequest], Awaitable[SubagentResponse]]


@dataclass(frozen=True, kw_only=True)
class _VerdictCtx:
    """Bundle the identity fields every verdict-build helper needs."""

    trace_uuid: UUID
    now: datetime
    latency_ms: float
    subagent_args: dict[str, object]
    subagent_name: str


def _allow_verdict(trace_uuid: UUID, now: datetime, latency_ms: float) -> Verdict:
    """Build the ALLOW verdict for a clean subagent call."""
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
    """Route a DefenseClaw-only match to a Verdict (no AI Defense call)."""
    if hit.rule == "Shell Injection":
        label, severity = VerdictLabel.BLOCK, Severity.HIGH
        modifications: dict[str, object] | None = None
    elif hit.rule == "Base64 Payload":
        label, severity = VerdictLabel.BLOCK, Severity.MEDIUM
        modifications = None
    else:
        label, severity = VerdictLabel.MODIFY, Severity.MEDIUM
        modifications = {"sanitized_args": sanitize_args(ctx.subagent_args, hit.rule)}
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

    Fail-closed BLOCK when AI Defense fires an unmapped rule (no v1
    sanitizer exists for that rule). Matches the tool_middleware
    discipline — silently MODIFYing with byte-identical sanitized_args
    would defeat the contract.
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
                subagent_name=ctx.subagent_name,
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
        modifications = {"sanitized_args": compose_sanitized(ctx.subagent_args, rule_names)}
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


_STRING_ARGS_KEY = "__splunkgate_string_input__"


def _resolve_args(call: SubagentCall) -> dict[str, object]:
    """Normalise SubagentCall.args (str | dict) into the dict form used by the rule pack.

    Strings get wrapped under `__splunkgate_string_input__` (namespaced to
    avoid collision with any real subagent arg key) so DefenseClaw regexes
    can still scan the text. Any other shape fails-closed via
    FailClosedError — PR #128 review caught raw dict(list) silently
    misinterpreting iterables of pairs.
    """
    if isinstance(call.args, str):
        return {_STRING_ARGS_KEY: call.args}
    if isinstance(call.args, dict):
        return dict(call.args)
    raise FailClosedError(
        synthetic_rule="subagent_args_unsupported_shape",
        severity=Severity.HIGH,
        explanation=(
            f"SubagentCall.args is {type(call.args).__name__}; v1 supports "
            "only str | dict — failing closed."
        ),
        cheap_hit=None,
    )


async def judge_subagent_call(
    request: SubagentRequest,
    profile: Profile,
    config: Config,
    ai_defense: AIDefenseLike | None = None,
    *,
    trace_uuid: UUID | None = None,
) -> Verdict:
    """Pure verdict producer — NEVER raises on BLOCK, NEVER calls a handler.

    Mirrors `tool_middleware.judge_tool_call`. The caller passes
    `trace_uuid` to share with the parent's bind; defaults to a fresh
    UUID when called standalone (e.g. from a unit test).

    EPIC-08 will add a dedicated `evaluate_subagent_call(name, input)`
    contract to `splunkgate_judges.defenseclaw_backend`; until then we
    reuse `evaluate_tool_call` (via `run_cheap_pass`) with the subagent's
    `name` and `args` so DefenseClaw regexes still fire on the input.
    """
    call = request.call
    if trace_uuid is None:
        trace_uuid = uuid4()
    now = datetime.now(UTC)
    started = time.perf_counter()

    try:
        subagent_args = _resolve_args(call)
        # PR #128 review fix: ALWAYS rebuild the call so its `.args` matches
        # `subagent_args`. The previous conditional left string-args calls
        # in place — meaning `run_cheap_pass` and `run_escalation`
        # inspected different shapes of the same call (cheap saw the
        # wrapped dict, escalation saw the raw string).
        tool_shape_call = cast("object", replace(call, args=subagent_args))
        cheap_hit = await run_cheap_pass(tool_shape_call, subagent_args, trace_uuid)

        if cheap_hit is None:
            latency_ms = (time.perf_counter() - started) * 1000
            _logger.debug(
                "subagent_middleware.allow",
                trace_id=str(trace_uuid),
                subagent_name=call.name,
                profile=profile.name,
            )
            return _allow_verdict(trace_uuid, now, latency_ms)

        ctx = _VerdictCtx(
            trace_uuid=trace_uuid,
            now=now,
            latency_ms=(time.perf_counter() - started) * 1000,
            subagent_args=subagent_args,
            subagent_name=call.name,
        )

        if not config.escalate_on_first_pass_hit or ai_defense is None:
            return _cheap_only_verdict(cheap_hit, ctx)

        response = await run_escalation(
            tool_shape_call,
            cheap_hit,
            ai_defense,
            trace_uuid,
            rules_tool_call=profile.rules_tool_call,
            profile_name=profile.name,
        )
        ctx = _VerdictCtx(
            trace_uuid=trace_uuid,
            now=now,
            latency_ms=(time.perf_counter() - started) * 1000,
            subagent_args=subagent_args,
            subagent_name=call.name,
        )
        return _ai_defense_verdict(response, cheap_hit, ctx)
    except FailClosedError as fc:
        return fail_closed_verdict(
            fc,
            trace_uuid=trace_uuid,
            now=now,
            latency_ms=(time.perf_counter() - started) * 1000,
            surface=_SURFACE,
        )
    except Exception as exc:  # noqa: BLE001 — fail-closed boundary; audit row must survive
        # PR #128 review fix: catch everything else (pydantic.ValidationError
        # from a future InspectResponse shape, ValueError from Severity()
        # cast on a new enum tier, KeyError from a malformed call, MemoryError
        # on a giant payload, etc.) and convert to a fail-closed BLOCK.
        # Without this, the agent loop sees a raw exception with no audit
        # row — the failure mode the _fail_closed.py discipline exists to
        # prevent.
        _logger.warning(
            "judge_subagent_call.internal_error",
            trace_id=str(trace_uuid),
            subagent_name=call.name,
            error=type(exc).__name__,
            exc_info=True,
        )
        return fail_closed_verdict(
            FailClosedError(
                synthetic_rule="judge_internal_error",
                severity=Severity.HIGH,
                explanation=(
                    f"judge_subagent_call internal error ({type(exc).__name__}) — failing closed"
                ),
                cheap_hit=None,
            ),
            trace_uuid=trace_uuid,
            now=now,
            latency_ms=(time.perf_counter() - started) * 1000,
            surface=_SURFACE,
        )


class SafetySubagentMiddleware(AgentMiddleware):  # type: ignore[misc]
    """Subagent-call safety wrap for splunklib.ai 3.0.0 agents."""

    def __init__(
        self,
        *,
        profile: str | Profile = "default",
        per_subagent_profile: dict[str, str | Profile] | None = None,
        config: Config | None = None,
        ai_defense: AIDefenseLike | None = None,
    ) -> None:
        """Wire profile + optional per-subagent overrides + config + AI Defense client."""
        self._config: Config = config if config is not None else Config()
        self._profile = resolve_profile(profile)
        log_if_custom_profile_shadows_canonical(self._profile, owner="SafetySubagentMiddleware")
        # Eagerly resolve string overrides into Profile instances so the
        # hot-path lookup is a plain dict access. resolve_profile() raises
        # UnknownProfile up-front if a typo lands in the override map. The
        # override map is captured at __init__; later mutations to the
        # passed dict have no effect — pass a fresh middleware if you need
        # dynamic overrides.
        overrides = per_subagent_profile or {}
        self._per_subagent_profile: dict[str, Profile] = {}
        for name, p in overrides.items():
            resolved = resolve_profile(p)
            log_if_custom_profile_shadows_canonical(
                resolved,
                owner=f"SafetySubagentMiddleware.per_subagent_profile[{name!r}]",
            )
            self._per_subagent_profile[name] = resolved
        self._ai_defense = ai_defense
        self._logger = structlog.get_logger("SafetySubagentMiddleware").bind(
            profile=self._profile.name,
        )

    async def subagent_middleware(
        self,
        request: SubagentRequest,
        handler: SubagentMiddlewareHandler,
    ) -> SubagentResponse:
        """Run judge → emit OTel → branch on label → delegate / block / sanitize.

        Every emitted verdict carries surface="mw_subagent". The handler is
        called only on ALLOW and MODIFY (with sanitized args).
        """
        effective = self._per_subagent_profile.get(request.call.name, self._profile)
        # Pull trace_id from the parent's bind; fall back to fresh only at
        # top level (e.g. a standalone test). The wire-in caller (story
        # mw-06) sets the contextvar via splunkgate_core.trace.set_trace_id.
        trace_uuid = current_trace_id() or uuid4()
        verdict = await judge_subagent_call(
            request,
            effective,
            self._config,
            self._ai_defense,
            trace_uuid=trace_uuid,
        )
        safe_emit(verdict)

        if verdict.verdict is VerdictLabel.BLOCK:
            self._logger.warning(
                "subagent_blocked",
                trace_id=str(verdict.trace_id),
                subagent_name=request.call.name,
                rules=[r.rule for r in verdict.rules],
                severity=verdict.severity.value,
            )
            raise SubagentBlockedBySplunkGate(verdict)

        if verdict.verdict is VerdictLabel.MODIFY:
            if isinstance(request.call.args, str):
                # PR #128 review fix: emit a synthetic BLOCK verdict
                # (replacing the MODIFY we already emitted) and raise
                # SubagentBlockedBySplunkGate to maintain the documented
                # contract. The old code raised generic SplunkGateError,
                # leaving callers unable to `except SubagentBlocked…`.
                # Pydantic model — use model_copy (not dataclasses.replace).
                forced_block = verdict.model_copy(
                    update={
                        "verdict": VerdictLabel.BLOCK,
                        "modifications": None,
                        "explanation": _MSG_STRING_ARGS_MODIFY_NOT_SUPPORTED,
                    },
                )
                safe_emit(forced_block)
                self._logger.warning(
                    "subagent_modify_on_string_args_fail_closed",
                    trace_id=str(verdict.trace_id),
                    subagent_name=request.call.name,
                )
                raise SubagentBlockedBySplunkGate(forced_block)
            sanitized_request = _rewrite_request(request, verdict)
            self._logger.info(
                "subagent_modified",
                trace_id=str(verdict.trace_id),
                subagent_name=request.call.name,
                rules=[r.rule for r in verdict.rules],
            )
            return await handler(sanitized_request)

        if verdict.verdict is VerdictLabel.ALLOW:
            return await handler(request)

        # PR #128 review fix: VerdictLabel.REVIEW (and any future enum
        # member) used to silently fall through to handler() — silent
        # ALLOW with the audit row contradicting the action. Fail-closed.
        self._logger.error(
            "subagent_unhandled_verdict_label_fail_closed",
            trace_id=str(verdict.trace_id),
            subagent_name=request.call.name,
            label=verdict.verdict.value,
        )
        raise SubagentBlockedBySplunkGate(verdict)


def _rewrite_request(request: SubagentRequest, verdict: Verdict) -> SubagentRequest:
    """Replace request.call.args with verdict.modifications['sanitized_args']."""
    mods = verdict.modifications or {}
    sanitized = mods.get("sanitized_args")
    if not isinstance(sanitized, dict):
        raise SplunkGateError(_MSG_MISSING_SANITIZED_ARGS)
    new_call = replace(request.call, args=sanitized)
    return replace(request, call=new_call)
