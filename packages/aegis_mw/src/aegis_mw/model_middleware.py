"""SafetyModelMiddleware — pre-inference scan (mw-03) + post-inference seam (mw-04).

Pre-inference scan: extract user-supplied content, run cheap_first_pass; if
hit + escalate_on_first_pass_hit=True, call Cisco AI Defense Inspection API
with rules_enabled=["Prompt Injection"]. Returns a Verdict regardless of label.

Per-label branch interpreted by the wrap:
  BLOCK  -> emit OTel verdict, raise ModelInputBlockedByAegis (handler NOT called)
  MODIFY -> rewrite HumanMessage with redacted_text; call handler with the
           rewritten request; post-inference scan (story-mw-04)
  ALLOW  -> call handler with the original request; post-inference scan (mw-04)
"""

from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol
from uuid import uuid4

import structlog
from aegis_core.errors import ModelInputBlockedByAegis, ModelOutputBlockedByAegis
from aegis_core.otel import emit_verdict_event
from aegis_core.verdict import RuleHit, Severity, Verdict, VerdictLabel
from splunklib.ai.messages import AIMessage, HumanMessage
from splunklib.ai.middleware import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
)

from aegis_mw._first_pass import (
    cheap_first_pass,
    extract_user_text,
    truncate_input,
)
from aegis_mw._post_inference import post_inference_scan
from aegis_mw.config import Config
from aegis_mw.profiles import Profile

if TYPE_CHECKING:
    from aegis_judges.ai_defense_types import InspectRequest, InspectResponse

__all__ = ["AIDefenseLike", "SafetyModelMiddleware", "pre_inference_scan"]

_logger = structlog.get_logger(__name__)


class AIDefenseLike(Protocol):
    """Duck-typed client surface satisfied by both live + stub clients."""

    async def inspect_chat(
        self, request: "InspectRequest", *, trace_id: str | None = None
    ) -> "InspectResponse":
        """POST /api/v1/inspect/chat — returns parsed InspectResponse."""


type ModelMiddlewareHandler = Callable[[ModelRequest], Awaitable[ModelResponse]]


def _allow_verdict(trace_uuid: object, now: datetime) -> Verdict:
    return Verdict(
        trace_id=trace_uuid,
        timestamp=now,
        verdict=VerdictLabel.ALLOW,
        severity=Severity.NONE_SEVERITY,
        rules=[],
        surface="mw_model",
        latency_ms=0.0,
    )


def _splunklib_block_verdict(trace_uuid: object, now: datetime, profile: Profile) -> Verdict:
    return Verdict(
        trace_id=trace_uuid,
        timestamp=now,
        verdict=VerdictLabel.BLOCK,
        severity=Severity.HIGH,
        rules=[RuleHit(rule="Prompt Injection", confidence=1.0, source="splunklib_security")],
        surface="mw_model",
        latency_ms=0.0,
        explanation=f"splunklib.ai.security flagged injection in profile {profile.name!r}",
    )


async def pre_inference_scan(
    messages: list[object],
    profile: Profile,
    config: Config,
    ai_defense: AIDefenseLike | None = None,
    trace_id: str | None = None,
) -> Verdict:
    """Cheap first-pass + optional AI Defense escalation -> Verdict.

    Pure verdict producer: NEVER raises on BLOCK, NEVER calls handler.
    """
    text = truncate_input(extract_user_text(messages))
    trace_uuid = uuid4()
    now = datetime.now(UTC)

    if not cheap_first_pass(text):
        return _allow_verdict(trace_uuid, now)

    if not config.escalate_on_first_pass_hit or ai_defense is None:
        return _splunklib_block_verdict(trace_uuid, now, profile)

    from aegis_judges.ai_defense_types import (  # noqa: PLC0415
        AIDefenseRule,
        EnabledRule,
        InspectConfig,
        InspectMessage,
        InspectRequest,
    )

    req = InspectRequest(
        messages=[InspectMessage(role="user", content=text)],
        config=InspectConfig(
            enabled_rules=[EnabledRule(rule_name=AIDefenseRule.PROMPT_INJECTION)],
        ),
    )
    resp = await ai_defense.inspect_chat(req, trace_id=trace_id)
    splunklib_hit = RuleHit(rule="Prompt Injection", confidence=1.0, source="splunklib_security")
    ai_defense_rules = [
        RuleHit(rule=str(r.rule_name.value), confidence=1.0, source="ai_defense")
        for r in resp.rules
    ]
    return Verdict(
        trace_id=trace_uuid,
        timestamp=now,
        verdict=VerdictLabel.BLOCK if not resp.is_safe else VerdictLabel.ALLOW,
        severity=Severity(resp.severity.value),
        rules=[splunklib_hit, *ai_defense_rules],
        surface="mw_model",
        latency_ms=0.0,
        explanation=resp.explanation,
    )


class SafetyModelMiddleware(AgentMiddleware):  # type: ignore[misc]
    """Pre-inference prompt-injection scan + post-inference seam (mw-04)."""

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
        self._logger = structlog.get_logger("SafetyModelMiddleware").bind(
            profile=self._profile.name
        )

    async def model_middleware(
        self,
        request: ModelRequest,
        handler: ModelMiddlewareHandler,
    ) -> ModelResponse:
        """Run pre-scan; branch on label; emit OTel event; delegate or block."""
        pre_verdict = await pre_inference_scan(
            list(request.state.messages),
            self._profile,
            self._config,
            self._ai_defense,
        )
        emit_verdict_event(pre_verdict)

        if pre_verdict.verdict is VerdictLabel.BLOCK:
            self._logger.warning(
                "model_input_blocked",
                trace_id=str(pre_verdict.trace_id),
                rules=[r.rule for r in pre_verdict.rules],
                severity=pre_verdict.severity.value,
            )
            raise ModelInputBlockedByAegis(pre_verdict)

        if pre_verdict.verdict is VerdictLabel.MODIFY:
            new_request = _rewrite_request(request, pre_verdict)
            response = await handler(new_request)
            # --- POST-INFERENCE SCAN: see story-mw-04 ---
            return await self._apply_post_scan(response)

        response = await handler(request)
        # --- POST-INFERENCE SCAN: see story-mw-04 ---
        return await self._apply_post_scan(response)

    async def _apply_post_scan(self, response: ModelResponse) -> ModelResponse:
        """Run post-inference scan; branch on label; emit OTel; deliver / redact / block."""
        post_verdict = await post_inference_scan(
            response,
            self._profile,
            self._config,
            self._ai_defense,
        )
        emit_verdict_event(post_verdict)

        if post_verdict.verdict is VerdictLabel.BLOCK:
            self._logger.warning(
                "model_output_blocked",
                trace_id=str(post_verdict.trace_id),
                rules=[r.rule for r in post_verdict.rules],
                severity=post_verdict.severity.value,
            )
            raise ModelOutputBlockedByAegis(post_verdict)

        if post_verdict.verdict is VerdictLabel.MODIFY:
            mods = post_verdict.modifications or {}
            redacted = str(mods.get("redacted_text", "[REDACTED]"))
            return ModelResponse(
                message=AIMessage(content=redacted, calls=[]),
                structured_output=response.structured_output,
            )

        return response


def _rewrite_request(request: ModelRequest, verdict: Verdict) -> ModelRequest:
    """Replace the latest HumanMessage content with verdict.modifications['redacted_text']."""
    mods = verdict.modifications or {}
    redacted = str(mods.get("redacted_text", "[REDACTED]"))
    new_messages: list[object] = []
    rewrote = False
    for msg in reversed(list(request.state.messages)):
        if not rewrote and isinstance(msg, HumanMessage):
            new_messages.append(HumanMessage(content=redacted))
            rewrote = True
            continue
        new_messages.append(msg)
    new_messages.reverse()
    new_state = replace(request.state, messages=new_messages)
    return replace(request, state=new_state)
