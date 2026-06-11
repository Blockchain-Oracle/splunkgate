"""AI Defense alone baseline (story-eval-04).

Wraps the existing `splunkgate_judges.ai_defense.AIDefenseClient.from_env()`
client and translates `InspectResponse → Verdict`. Foundation-Sec is
deliberately excluded per ADR-003 — that's the whole point of "Cisco
AI Defense alone." `explanation` is hard-set to None; do not wire in
the explainer behind this surface.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from splunkgate_core.verdict import RuleHit, Severity, Verdict, VerdictLabel
from splunkgate_judges.ai_defense import AIDefenseClient

if TYPE_CHECKING:
    from splunkgate_eval.synthetic import EvalPrompt

__all__ = ["ai_defense_alone"]


def ai_defense_alone(prompt: EvalPrompt) -> Verdict:
    """Return a Verdict from AI Defense; no Foundation-Sec explainer (ADR-003)."""
    from splunkgate_judges.ai_defense_types import (  # noqa: PLC0415
        InspectConfig,
        InspectMessage,
        InspectRequest,
    )

    # AIDefenseClient.from_env() honours SPLUNKGATE_AI_DEFENSE_MOCK (EPIC-04).
    client = AIDefenseClient.from_env()
    started = time.perf_counter_ns()
    req = InspectRequest(
        messages=[InspectMessage(role="user", content=prompt.prompt)],
        config=InspectConfig(),
    )
    resp = asyncio.run(client.inspect_chat(req, trace_id=str(uuid4())))
    latency_ms = (time.perf_counter_ns() - started) / 1_000_000

    if resp.is_safe:
        verdict_label = VerdictLabel.ALLOW
        severity = Severity.NONE_SEVERITY
    else:
        severity = Severity(resp.severity.value)
        verdict_label = VerdictLabel.BLOCK if severity is Severity.HIGH else VerdictLabel.MODIFY

    rules = [
        RuleHit(rule=str(r.rule_name.value), confidence=1.0, source="ai_defense")
        for r in resp.rules
    ]

    return Verdict(
        trace_id=uuid4(),
        timestamp=datetime.now(UTC),
        verdict=verdict_label,
        severity=severity,
        rules=rules,
        surface="mw_model",
        latency_ms=latency_ms,
        explanation=None,
    )
