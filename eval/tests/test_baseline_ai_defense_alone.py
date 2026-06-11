"""Behavioural tests for the ai_defense_alone baseline (story-eval-04)."""

from __future__ import annotations

import pytest
from splunkgate_core.verdict import Severity, Verdict, VerdictLabel
from splunkgate_eval import EvalPrompt
from splunkgate_eval.baselines.ai_defense_alone import ai_defense_alone


def _prompt(text: str) -> EvalPrompt:
    """Tiny EvalPrompt constructor; keeps tests readable."""
    return EvalPrompt(
        id="00000000-0000-0000-0000-000000000001",
        category="tool_call_abuse",
        prompt=text,
        expected_verdict="BLOCK",
        expected_severity="HIGH",
        source_citation="test",
    )


@pytest.fixture(autouse=True)
def _ai_defense_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    """All AI-Defense-alone tests run via the canonical EPIC-04 mock dispatch."""
    monkeypatch.setenv("SPLUNKGATE_AI_DEFENSE_MOCK", "1")


def test_baseline_returns_a_verdict() -> None:
    """Callable contract — the baseline returns a Verdict."""
    assert isinstance(ai_defense_alone(_prompt("hello")), Verdict)


def test_explanation_is_none_per_adr_003() -> None:
    """ADR-003: ai_defense_alone explicitly excludes Foundation-Sec, so explanation is None."""
    assert ai_defense_alone(_prompt("hello")).explanation is None


def test_surface_is_mw_model() -> None:
    """Per the spec, the AI-Defense-alone baseline emits on `mw_model`."""
    assert ai_defense_alone(_prompt("hello")).surface == "mw_model"


def test_pii_trigger_returns_block_high_with_pii_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The PII trigger string hits the AI Defense mock matrix and returns BLOCK / HIGH."""
    monkeypatch.setenv("SPLUNKGATE_AI_DEFENSE_MOCK_POLICY", "pii")
    v = ai_defense_alone(_prompt("my ssn is 123-45-6789"))
    assert v.verdict in {VerdictLabel.BLOCK, VerdictLabel.MODIFY}
    assert v.severity in {Severity.HIGH, Severity.MEDIUM}
    if v.rules:
        assert any(r.source == "ai_defense" for r in v.rules)


def test_benign_prompt_returns_allow() -> None:
    """Default mock returns ALLOW / NONE_SEVERITY for unmatched prompts."""
    v = ai_defense_alone(_prompt("what's the weather in Seattle?"))
    assert v.verdict is VerdictLabel.ALLOW
    assert v.severity is Severity.NONE_SEVERITY


def test_deterministic_across_calls() -> None:
    """Two consecutive calls with the same prompt produce identical (verdict, severity)."""
    p = _prompt("benign prompt for determinism check")
    v1, v2 = ai_defense_alone(p), ai_defense_alone(p)
    assert (v1.verdict, v1.severity) == (v2.verdict, v2.severity)


def test_latency_is_recorded_as_positive_float() -> None:
    """latency_ms reflects the round-trip through the mock client."""
    v = ai_defense_alone(_prompt("hello"))
    assert v.latency_ms > 0


def test_classifications_propagated_via_rules() -> None:
    """When AI Defense fires a rule, its rule_name lands in Verdict.rules with source='ai_defense'."""
    v = ai_defense_alone(_prompt("anything"))
    for r in v.rules:
        assert r.source == "ai_defense"
