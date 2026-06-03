"""Behavioral tests for the OTel verdict-event emitter.

Uses opentelemetry-sdk's InMemorySpanExporter to capture emitted spans
+ events and assert on the actual attribute keys/values. No mocks.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
from aegis_core.otel import (
    EVALUATION_NAME,
    emit_verdict_event,
    severity_to_score,
)
from aegis_core.verdict import RuleHit, Severity, Verdict, VerdictLabel
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

# OTel's TracerProvider is process-global and set-once. Initialize once at
# module load; expose the shared exporter and clear it between tests.
_EXPORTER = InMemorySpanExporter()
_PROVIDER = TracerProvider()
_PROVIDER.add_span_processor(SimpleSpanProcessor(_EXPORTER))
trace.set_tracer_provider(_PROVIDER)


@pytest.fixture
def exporter() -> Iterator[InMemorySpanExporter]:
    """Yield the module-shared in-memory exporter, clearing before + after each test."""
    _EXPORTER.clear()
    yield _EXPORTER
    _EXPORTER.clear()


def _verdict(
    *,
    label: VerdictLabel = VerdictLabel.ALLOW,
    severity: Severity = Severity.NONE_SEVERITY,
    explanation: str | None = None,
    rules: list[RuleHit] | None = None,
) -> Verdict:
    return Verdict(
        trace_id=uuid4(),
        timestamp=datetime.now(UTC),
        verdict=label,
        severity=severity,
        rules=rules if rules is not None else [],
        surface="mw_model",
        latency_ms=10.0,
        explanation=explanation,
    )


def _emit_inside_span(
    exporter: InMemorySpanExporter,
    verdict: Verdict,
    *,
    mcp_method_name: str | None = None,
    mcp_session_id: UUID | None = None,
) -> ReadableSpan:
    """Emit within an enclosing span so the exporter actually captures it."""
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("test_span"):
        emit_verdict_event(
            verdict,
            mcp_method_name=mcp_method_name,
            mcp_session_id=mcp_session_id,
        )
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    return cast("ReadableSpan", spans[0])


def test_event_name_is_gen_ai_evaluation_result(exporter: InMemorySpanExporter) -> None:
    span = _emit_inside_span(exporter, _verdict())
    assert len(span.events) == 1
    assert span.events[0].name == "gen_ai.evaluation.result"


def test_evaluation_name_attr_is_aegis_safety_verdict(
    exporter: InMemorySpanExporter,
) -> None:
    span = _emit_inside_span(exporter, _verdict())
    attrs = dict(span.events[0].attributes or {})
    assert attrs["gen_ai.evaluation.name"] == EVALUATION_NAME


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        (VerdictLabel.ALLOW, "allow"),
        (VerdictLabel.BLOCK, "block"),
        (VerdictLabel.MODIFY, "modify"),
        (VerdictLabel.REVIEW, "review"),
    ],
)
def test_score_label_is_lowercased(
    exporter: InMemorySpanExporter, label: VerdictLabel, expected: str
) -> None:
    span = _emit_inside_span(exporter, _verdict(label=label))
    attrs = dict(span.events[0].attributes or {})
    assert attrs["gen_ai.evaluation.score.label"] == expected


def test_score_value_is_float_in_unit_interval(
    exporter: InMemorySpanExporter,
) -> None:
    span = _emit_inside_span(exporter, _verdict(severity=Severity.HIGH))
    attrs = dict(span.events[0].attributes or {})
    value = attrs["gen_ai.evaluation.score.value"]
    assert isinstance(value, float)
    assert 0.0 <= value <= 1.0


def test_explanation_attr_absent_when_none(exporter: InMemorySpanExporter) -> None:
    span = _emit_inside_span(exporter, _verdict(explanation=None))
    attrs = dict(span.events[0].attributes or {})
    assert "gen_ai.evaluation.explanation" not in attrs


def test_explanation_attr_present_when_string(
    exporter: InMemorySpanExporter,
) -> None:
    span = _emit_inside_span(exporter, _verdict(explanation="prompt injection detected in field X"))
    attrs = dict(span.events[0].attributes or {})
    assert attrs["gen_ai.evaluation.explanation"] == "prompt injection detected in field X"


def test_mcp_attrs_populated_when_supplied(exporter: InMemorySpanExporter) -> None:
    session_id = uuid4()
    span = _emit_inside_span(
        exporter,
        _verdict(),
        mcp_method_name="tools/call",
        mcp_session_id=session_id,
    )
    attrs = dict(span.events[0].attributes or {})
    assert attrs["mcp.method.name"] == "tools/call"
    assert attrs["mcp.session.id"] == str(session_id)


def test_mcp_attrs_absent_when_not_supplied(exporter: InMemorySpanExporter) -> None:
    span = _emit_inside_span(exporter, _verdict())
    attrs = dict(span.events[0].attributes or {})
    assert "mcp.method.name" not in attrs
    assert "mcp.session.id" not in attrs


def test_aegis_surface_attr_matches_verdict_surface(
    exporter: InMemorySpanExporter,
) -> None:
    span = _emit_inside_span(exporter, _verdict())
    attrs = dict(span.events[0].attributes or {})
    assert attrs["aegis.surface"] == "mw_model"


def test_aegis_rules_attr_is_list_of_rule_names(
    exporter: InMemorySpanExporter,
) -> None:
    rules = [
        RuleHit(rule="Prompt Injection", confidence=0.95, source="ai_defense"),
        RuleHit(rule="PII", confidence=0.82, source="ai_defense"),
    ]
    span = _emit_inside_span(exporter, _verdict(rules=rules))
    attrs = dict(span.events[0].attributes or {})
    rules_attr = attrs["aegis.rules"]
    assert list(rules_attr) == ["Prompt Injection", "PII"]  # type: ignore[arg-type]


def test_aegis_trace_id_is_stringified_uuid(exporter: InMemorySpanExporter) -> None:
    v = _verdict()
    span = _emit_inside_span(exporter, v)
    attrs = dict(span.events[0].attributes or {})
    assert attrs["aegis.trace_id"] == str(v.trace_id)


def test_severity_to_score_is_monotonic() -> None:
    n = severity_to_score(Severity.NONE_SEVERITY)
    low = severity_to_score(Severity.LOW)
    med = severity_to_score(Severity.MEDIUM)
    high = severity_to_score(Severity.HIGH)
    assert 0.0 <= n < low < med < high <= 1.0


def test_emit_outside_span_is_noop_safe() -> None:
    """No enclosing span — emit should not raise. OTel returns NonRecordingSpan."""
    emit_verdict_event(_verdict())
