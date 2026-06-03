"""Behavioral + property tests for the Verdict pydantic types."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from aegis_core.verdict import (
    RuleHit,
    Severity,
    Verdict,
    VerdictLabel,
    verdict_to_json_schema,
)
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

SURFACES = (
    "mw_model",
    "mw_tool",
    "mw_subagent",
    "mcp_score",
    "mcp_judge_tool",
    "mcp_check_output",
    "mcp_audit",
    "defenseclaw",
)


def _make_verdict(**overrides: object) -> Verdict:
    base: dict[str, object] = {
        "trace_id": uuid4(),
        "timestamp": datetime.now(UTC),
        "verdict": VerdictLabel.ALLOW,
        "severity": Severity.NONE_SEVERITY,
        "rules": [],
        "surface": "mw_model",
        "latency_ms": 0.0,
    }
    base.update(overrides)
    return Verdict(**base)  # type: ignore[arg-type]


def test_severity_enum_has_all_four_values() -> None:
    assert {s.value for s in Severity} == {"NONE_SEVERITY", "LOW", "MEDIUM", "HIGH"}


def test_verdict_label_has_all_four_values() -> None:
    assert {v.value for v in VerdictLabel} == {"ALLOW", "BLOCK", "MODIFY", "REVIEW"}


def test_rule_hit_accepts_zero_confidence() -> None:
    hit = RuleHit(rule="x", confidence=0.0, source="ai_defense")
    assert hit.confidence == 0.0


def test_rule_hit_accepts_unity_confidence() -> None:
    hit = RuleHit(rule="x", confidence=1.0, source="defenseclaw_regex")
    assert hit.confidence == 1.0


def test_rule_hit_rejects_negative_confidence() -> None:
    with pytest.raises(ValidationError):
        RuleHit(rule="x", confidence=-0.01, source="ai_defense")


def test_rule_hit_rejects_above_one_confidence() -> None:
    with pytest.raises(ValidationError):
        RuleHit(rule="x", confidence=1.01, source="ai_defense")


def test_rule_hit_rejects_unknown_source() -> None:
    with pytest.raises(ValidationError):
        RuleHit(rule="x", confidence=0.5, source="foundation_sec_classifier")  # type: ignore[arg-type]


def test_verdict_round_trips_through_json() -> None:
    v = _make_verdict(
        verdict=VerdictLabel.BLOCK,
        severity=Severity.HIGH,
        rules=[RuleHit(rule="Prompt Injection", confidence=0.93, source="ai_defense")],
    )
    raw = v.model_dump_json()
    restored = Verdict.model_validate_json(raw)
    assert restored == v


def test_verdict_severity_none_round_trips() -> None:
    v = _make_verdict(severity=Severity.NONE_SEVERITY)
    raw = v.model_dump_json()
    restored = Verdict.model_validate_json(raw)
    assert restored.severity is Severity.NONE_SEVERITY


def test_verdict_json_schema_has_all_documented_fields() -> None:
    schema = verdict_to_json_schema()
    properties = set(schema["properties"].keys())  # type: ignore[index,union-attr]
    expected = {
        "trace_id",
        "timestamp",
        "verdict",
        "severity",
        "rules",
        "explanation",
        "classifications",
        "modifications",
        "surface",
        "latency_ms",
    }
    assert expected <= properties


def test_verdict_rejects_unknown_surface() -> None:
    with pytest.raises(ValidationError):
        _make_verdict(surface="invalid_surface")


def test_verdict_rejects_non_uuid_trace_id() -> None:
    with pytest.raises(ValidationError):
        _make_verdict(trace_id="not-a-uuid")


def test_verdict_accepts_empty_rules_list() -> None:
    v = _make_verdict(rules=[])
    assert v.rules == []


def test_verdict_accepts_none_explanation() -> None:
    v = _make_verdict(explanation=None)
    assert v.explanation is None


def test_verdict_accepts_none_modifications() -> None:
    v = _make_verdict(modifications=None)
    assert v.modifications is None


def test_verdict_accepts_dict_modifications() -> None:
    mods: dict[str, object] = {"redacted_fields": ["ssn"], "replaced_with": "[REDACTED]"}
    v = _make_verdict(modifications=mods)
    assert v.modifications == mods


@given(
    label=st.sampled_from(list(VerdictLabel)),
    severity=st.sampled_from(list(Severity)),
    surface=st.sampled_from(SURFACES),
    latency_ms=st.floats(min_value=0.0, max_value=10_000.0, allow_nan=False),
)
def test_verdict_round_trip_preserves_fields(
    label: VerdictLabel,
    severity: Severity,
    surface: str,
    latency_ms: float,
) -> None:
    trace = uuid4()
    ts = datetime.now(UTC)
    v = Verdict(
        trace_id=trace,
        timestamp=ts,
        verdict=label,
        severity=severity,
        rules=[],
        surface=surface,  # type: ignore[arg-type]
        latency_ms=latency_ms,
    )
    restored = Verdict.model_validate_json(v.model_dump_json())
    assert restored.trace_id == trace
    assert restored.verdict is label
    assert restored.severity is severity
    assert restored.surface == surface
    assert restored.latency_ms == latency_ms


@given(confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
def test_rule_hit_accepts_in_bounds_confidence(confidence: float) -> None:
    hit = RuleHit(rule="x", confidence=confidence, source="ai_defense")
    assert hit.confidence == confidence


def test_verdict_label_value_lowercases_for_otel() -> None:
    """gen_ai.evaluation.result.score.label gets value.lower() — verify round-trip safe."""
    for label in VerdictLabel:
        assert label.value.lower() in {"allow", "block", "modify", "review"}


def test_verdict_returns_consistent_uuid_type() -> None:
    v = _make_verdict()
    assert isinstance(v.trace_id, UUID)
