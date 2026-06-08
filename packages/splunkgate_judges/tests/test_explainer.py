"""Behavioral tests for the v1 template-based verdict explainer.

Per story-explainer-01 + ADR-013. Asserts deterministic, dependency-free
explanation generation that surfaces Cisco AI Defense rule names + source
attribution without leaking raw redacted content.
"""

from datetime import UTC, datetime
from uuid import uuid4

from splunkgate_core import (
    RuleHit,
    Severity,
    Verdict,
    VerdictContext,
    VerdictLabel,
)
from splunkgate_judges.explainer import explain_verdict

_FIXED_TIME = datetime(2026, 6, 5, 12, 0, 0, tzinfo=UTC)
_FIXED_UUID = uuid4()


def _verdict(
    *,
    label: VerdictLabel = VerdictLabel.BLOCK,
    severity: Severity = Severity.HIGH,
    rules: list[RuleHit] | None = None,
    modifications: dict[str, object] | None = None,
) -> Verdict:
    return Verdict(
        trace_id=_FIXED_UUID,
        timestamp=_FIXED_TIME,
        verdict=label,
        severity=severity,
        rules=rules
        or [
            RuleHit(
                rule="Prompt Injection",
                confidence=1.0,
                source="ai_defense",
            )
        ],
        modifications=modifications,
        surface="mw_model",
        latency_ms=12.5,
    )


def _ctx() -> VerdictContext:
    return VerdictContext(
        trace_id=_FIXED_UUID,
        agent_id="support-agent",
        model_name="claude-sonnet-4-6",
        system_prompt_summary="Customer support routing",
        recent_messages=["Hello", "How can I help?"],
        surface="mw_model",
    )


def test_block_high_prompt_injection_contains_required_tokens() -> None:
    verdict = _verdict(label=VerdictLabel.BLOCK, severity=Severity.HIGH)
    out = explain_verdict(verdict)
    assert "Prompt Injection" in out
    assert "BLOCK" in out
    assert "HIGH" in out
    assert "None" not in out
    assert "null" not in out


def test_allow_no_rules_is_non_empty_and_safe_signal() -> None:
    verdict = _verdict(
        label=VerdictLabel.ALLOW,
        severity=Severity.NONE_SEVERITY,
        rules=[],
    )
    out = explain_verdict(verdict)
    assert out.strip(), "ALLOW output must be non-empty"
    lowered = out.lower()
    assert any(t in lowered for t in ("allow", "no rules", "safe")), out


def test_multiple_rules_from_distinct_sources_all_surface() -> None:
    verdict = _verdict(
        rules=[
            RuleHit(rule="Prompt Injection", confidence=1.0, source="splunklib_security"),
            RuleHit(rule="PII", confidence=0.9, source="ai_defense"),
        ]
    )
    out = explain_verdict(verdict)
    assert out.count("Prompt Injection") == 1
    assert out.count("PII") == 1
    assert "splunklib_security" in out
    assert "ai_defense" in out


def test_determinism_byte_equal_on_identical_input() -> None:
    verdict = _verdict()
    a = explain_verdict(verdict)
    b = explain_verdict(verdict)
    assert a == b
    # Encoding-stable too — no smart quotes / locale-sensitive whitespace
    assert a.encode("utf-8") == b.encode("utf-8")


def test_modify_with_redacted_text_references_redaction_only() -> None:
    verdict = _verdict(
        label=VerdictLabel.MODIFY,
        severity=Severity.MEDIUM,
        modifications={"redacted_text": "[REDACTED]"},
    )
    out = explain_verdict(verdict)
    assert "MODIFY" in out
    # Mentions redaction but does NOT inline literal raw PII markers.
    # We accept either the word "redact" (any case) or the redaction sentinel.
    lowered = out.lower()
    assert "redact" in lowered or "[REDACTED]" in out
    # And critically, no raw SSN / credit-card / email patterns should sneak in.
    assert "123-45-6789" not in out
    assert "@" not in out  # no inline emails


def test_ctx_is_forward_compat_only_v1_ignores_it() -> None:
    """The optional ctx parameter MUST be unused by v1 template — regression guard
    for the day someone is tempted to make output ctx-dependent without ADR review.
    """
    verdict = _verdict()
    with_ctx = explain_verdict(verdict, _ctx())
    without_ctx = explain_verdict(verdict, None)
    no_ctx_arg = explain_verdict(verdict)
    assert with_ctx == without_ctx == no_ctx_arg


def test_output_is_bounded_in_length() -> None:
    """Dashboards + PDF cells truncate long strings — keep output compact."""
    verdict = _verdict()
    out = explain_verdict(verdict)
    assert len(out) <= 280, f"output too long ({len(out)} chars): {out!r}"


def test_review_label_renders_cleanly() -> None:
    """REVIEW is one of the four VerdictLabel values; the template must render it."""
    verdict = _verdict(label=VerdictLabel.REVIEW, severity=Severity.LOW)
    out = explain_verdict(verdict)
    assert "REVIEW" in out
    assert "LOW" in out
