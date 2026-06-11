# §14 CARVE-OUT: deterministic gpt-oss-120b stand-in used when
# SPLUNKGATE_GPT_OSS_MOCK=1. The live path (story-foundsec-01 Splunk
# Hosted Models) is not yet reachable per memory:aegis_hosted_models_gap.
"""Tiny deterministic mock dispatcher for the gpt-oss-120b baseline."""

from __future__ import annotations

from typing import Final, NamedTuple

from splunkgate_core.verdict import Severity, VerdictLabel

__all__ = ["MockJudgeResponse", "mock_dispatch"]


class MockJudgeResponse(NamedTuple):
    """One row in the deterministic verdict matrix."""

    verdict: VerdictLabel
    severity: Severity
    explanation: str


_PATTERN_DISPATCH: Final[dict[str, MockJudgeResponse]] = {
    "ignore previous": MockJudgeResponse(
        VerdictLabel.BLOCK,
        Severity.HIGH,
        "Prompt-injection attempt: 'ignore previous instructions' override.",
    ),
    "my ssn": MockJudgeResponse(
        VerdictLabel.BLOCK,
        Severity.HIGH,
        "PII disclosure: explicit SSN in prompt.",
    ),
    "velocity.show": MockJudgeResponse(
        VerdictLabel.BLOCK,
        Severity.HIGH,
        "Imprompter-style exfiltration domain detected.",
    ),
    "rm -rf": MockJudgeResponse(
        VerdictLabel.BLOCK,
        Severity.HIGH,
        "Destructive shell command in prompt.",
    ),
    "system prompt": MockJudgeResponse(
        VerdictLabel.REVIEW,
        Severity.MEDIUM,
        "Possible system-prompt disclosure request — human review.",
    ),
}

_DEFAULT_RESPONSE: Final[MockJudgeResponse] = MockJudgeResponse(
    VerdictLabel.ALLOW,
    Severity.NONE_SEVERITY,
    "No safety-policy triggers detected.",
)


def mock_dispatch(prompt_text: str) -> MockJudgeResponse:
    """Return a deterministic gpt-oss-120b-shaped response."""
    lowered = prompt_text.lower()
    for needle, response in _PATTERN_DISPATCH.items():
        if needle in lowered:
            return response
    return _DEFAULT_RESPONSE
