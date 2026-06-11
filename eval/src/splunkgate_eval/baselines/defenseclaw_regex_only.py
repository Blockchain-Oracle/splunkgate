"""DefenseClaw regex-only baseline (story-eval-04).

Runs the vendored DefenseClaw rule pack (115 patterns parsed from
upstream `rules.go`) against an `EvalPrompt`. First-match BLOCK with
the rule's declared severity; no match → ALLOW. Sub-millisecond
latency on a laptop — zero external dependencies.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from splunkgate_core.verdict import RuleHit, Severity, Verdict, VerdictLabel

from splunkgate_eval.baselines._regex_loader import load_defenseclaw_rules

if TYPE_CHECKING:
    from splunkgate_eval.synthetic import EvalPrompt

__all__ = ["defenseclaw_regex_only"]

# rules.go orders SEC-* (CRITICAL credentials) first, then C2-*, CMD-*,
# PATH-*, TRUST-*, COG-* — that ordering is the upstream maintainer's
# priority signal. First-match is faithful to DefenseClaw-as-shipped,
# which is exactly what a baseline should measure.
_SEVERITY_MAP = {
    "CRITICAL": Severity.HIGH,
    "HIGH": Severity.HIGH,
    "MEDIUM": Severity.MEDIUM,
    "LOW": Severity.LOW,
}


def defenseclaw_regex_only(prompt: EvalPrompt) -> Verdict:
    """Return a Verdict from the first matching DefenseClaw rule, else ALLOW."""
    started = time.perf_counter_ns()
    hit = next(
        (r for r in load_defenseclaw_rules() if r.pattern.search(prompt.prompt)),
        None,
    )
    latency_ms = (time.perf_counter_ns() - started) / 1_000_000

    if hit is None:
        return Verdict(
            trace_id=uuid4(),
            timestamp=datetime.now(UTC),
            verdict=VerdictLabel.ALLOW,
            severity=Severity.NONE_SEVERITY,
            rules=[],
            surface="defenseclaw",
            latency_ms=latency_ms,
        )

    return Verdict(
        trace_id=uuid4(),
        timestamp=datetime.now(UTC),
        verdict=VerdictLabel.BLOCK,
        severity=_SEVERITY_MAP.get(hit.severity, Severity.MEDIUM),
        rules=[RuleHit(rule=hit.title, confidence=hit.confidence, source="defenseclaw_regex")],
        surface="defenseclaw",
        latency_ms=latency_ms,
    )
