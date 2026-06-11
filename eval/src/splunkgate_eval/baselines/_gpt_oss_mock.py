# §14 CARVE-OUT: deterministic gpt-oss-120b stand-in used when
# SPLUNKGATE_GPT_OSS_MOCK=1. The live path (story-foundsec-01 Splunk
# Hosted Models) is not yet reachable per memory:aegis_hosted_models_gap.
"""Tiny deterministic mock dispatcher for the gpt-oss-120b baseline."""

from __future__ import annotations

import hashlib
from typing import Final

from splunkgate_core.verdict import Severity, VerdictLabel

__all__ = ["MockJudgeResponse", "mock_dispatch"]


class MockJudgeResponse:
    """One row in the deterministic verdict matrix."""

    __slots__ = ("explanation", "severity", "verdict")

    def __init__(
        self,
        *,
        verdict: VerdictLabel,
        severity: Severity,
        explanation: str,
    ) -> None:
        """Wrap the three fields the gpt-oss-120b baseline returns."""
        self.verdict = verdict
        self.severity = severity
        self.explanation = explanation


_PATTERN_DISPATCH: Final[tuple[tuple[str, MockJudgeResponse], ...]] = (
    (
        "ignore previous",
        MockJudgeResponse(
            verdict=VerdictLabel.BLOCK,
            severity=Severity.HIGH,
            explanation="Prompt-injection attempt: 'ignore previous instructions' override.",
        ),
    ),
    (
        "my ssn",
        MockJudgeResponse(
            verdict=VerdictLabel.BLOCK,
            severity=Severity.HIGH,
            explanation="PII disclosure: explicit SSN in prompt.",
        ),
    ),
    (
        "velocity.show",
        MockJudgeResponse(
            verdict=VerdictLabel.BLOCK,
            severity=Severity.HIGH,
            explanation="Imprompter-style exfiltration domain detected.",
        ),
    ),
    (
        "rm -rf",
        MockJudgeResponse(
            verdict=VerdictLabel.BLOCK,
            severity=Severity.HIGH,
            explanation="Destructive shell command in prompt.",
        ),
    ),
    (
        "system prompt",
        MockJudgeResponse(
            verdict=VerdictLabel.REVIEW,
            severity=Severity.MEDIUM,
            explanation="Possible system-prompt disclosure request — human review.",
        ),
    ),
)

_DEFAULT_RESPONSE: Final[MockJudgeResponse] = MockJudgeResponse(
    verdict=VerdictLabel.ALLOW,
    severity=Severity.NONE_SEVERITY,
    explanation="No safety-policy triggers detected.",
)


def mock_dispatch(prompt_text: str) -> MockJudgeResponse:
    """Return a deterministic gpt-oss-120b-shaped response for `prompt_text`."""
    lowered = prompt_text.lower()
    for needle, response in _PATTERN_DISPATCH:
        if needle in lowered:
            return response
    # Hash-stable default so cross-corpus runs still produce a verdict.
    _ = hashlib.sha256(prompt_text.encode()).hexdigest()
    return _DEFAULT_RESPONSE
