"""Post-inference scan helper (story-mw-04).

Runs Cisco AI Defense against the LLM's output text + the rule subset that
focuses on regulated-data exposure: PII / PHI / PCI / Code Detection. On
non-ALLOW verdict, the helper optionally attaches a WHY-string via
`splunkgate_judges.explainer.explain_verdict` (gated on `config.foundation_sec_enabled`
— per ADR-013 the explainer is the v1 template; the Foundation-Sec swap
happens behind the same call site).

Surface = `mw_model` (same as pre-scan; both are model-boundary events).
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import structlog
from splunkgate_core.verdict import RuleHit, Severity, Verdict, VerdictLabel
from splunkgate_judges.explainer import explain_verdict

from splunkgate_mw.config import Config
from splunkgate_mw.profiles import Profile

if TYPE_CHECKING:
    from splunklib.ai.messages import AIMessage
    from splunklib.ai.middleware import ModelResponse

    from splunkgate_mw.model_middleware import AIDefenseLike

__all__ = ["post_inference_scan"]

_logger = structlog.get_logger(__name__)


def _extract_output_text(response: "ModelResponse") -> str:
    """Return the concatenated text content of an AIMessage.

    splunklib's AIMessage.content is `str | list[str | ContentBlock]`. We
    coerce both shapes to a single string; ContentBlock instances stringify
    via their repr (the model-output path doesn't surface them in typical
    chat use, but the defensive coercion keeps the scanner total).
    """
    msg: AIMessage = response.message
    if isinstance(msg.content, str):
        return msg.content
    return "".join(chunk if isinstance(chunk, str) else str(chunk) for chunk in msg.content)


def _allow_verdict(trace_uuid: UUID, now: datetime) -> Verdict:
    return Verdict(
        trace_id=trace_uuid,
        timestamp=now,
        verdict=VerdictLabel.ALLOW,
        severity=Severity.NONE_SEVERITY,
        rules=[],
        surface="mw_model",
        latency_ms=0.0,
    )


async def post_inference_scan(
    response: "ModelResponse",
    profile: Profile,
    config: Config,
    ai_defense: "AIDefenseLike | None" = None,
    trace_id: str | None = None,
) -> Verdict:
    """Scan model output via AI Defense; produce a Verdict with WHY-string."""
    text = _extract_output_text(response)
    trace_uuid = uuid4()
    now = datetime.now(UTC)

    # Per pr-review N1: split the two short-circuit ALLOWs so operators
    # triaging "why did SplunkGate skip this scan?" can distinguish the two
    # legitimate cases from the structured-log stream.
    if not text.strip():
        _logger.debug(
            "post_inference.allow.empty_text",
            trace_id=str(trace_uuid),
            profile=profile.name,
        )
        return _allow_verdict(trace_uuid, now)
    if ai_defense is None:
        _logger.debug(
            "post_inference.allow.no_client",
            trace_id=str(trace_uuid),
            profile=profile.name,
            text_length=len(text),
        )
        return _allow_verdict(trace_uuid, now)

    # Lazy import keeps splunkgate_mw decoupled from splunkgate_judges at module load.
    from splunkgate_judges.ai_defense_types import (  # noqa: PLC0415
        InspectConfig,
        InspectMessage,
        InspectRequest,
    )

    from splunkgate_mw._rule_mapping import profile_rules_to_enabled_rules  # noqa: PLC0415

    enabled_rules = profile_rules_to_enabled_rules(
        profile.rules_post_inference,
        profile_name=profile.name,
        surface="mw_model_post",
    )
    req = InspectRequest(
        messages=[InspectMessage(role="assistant", content=text)],
        config=InspectConfig(enabled_rules=enabled_rules),
    )
    resp = await ai_defense.inspect_chat(req, trace_id=trace_id)

    if resp.is_safe:
        return _allow_verdict(trace_uuid, now)

    severity = Severity(resp.severity.value)
    label = VerdictLabel.BLOCK if severity is Severity.HIGH else VerdictLabel.MODIFY
    modifications: dict[str, object] | None = (
        {"redacted_text": "[REDACTED]"} if label is VerdictLabel.MODIFY else None
    )
    rules = [
        RuleHit(rule=str(r.rule_name.value), confidence=1.0, source="ai_defense")
        for r in resp.rules
    ]

    verdict = Verdict(
        trace_id=trace_uuid,
        timestamp=now,
        verdict=label,
        severity=severity,
        rules=rules,
        modifications=modifications,
        surface="mw_model",
        latency_ms=0.0,
    )

    if config.foundation_sec_enabled:
        verdict = verdict.model_copy(update={"explanation": explain_verdict(verdict)})

    _logger.debug(
        "post_inference.verdict",
        trace_id=str(verdict.trace_id),
        label=label.value,
        severity=severity.value,
        rule_count=len(rules),
        explanation_set=verdict.explanation is not None,
        profile=profile.name,
    )

    return verdict
