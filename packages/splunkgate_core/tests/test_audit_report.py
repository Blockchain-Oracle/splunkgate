"""Behavioral tests for the AuditReport Pydantic shape (story-mcp-05).

`AuditReport` is the aggregate view returned by `splunkgate_audit_trace`
and consumed by Surface 4 dashboards. These tests cover the shape
guarantees the consumers depend on:

  - event_count + verdicts list arity
  - first_seen / last_seen envelope (None when event_count == 0)
  - surfaces_seen typed against the locked Literal
  - aggregate is dict[str, object] — accepts strings, ints, bools, dicts
  - round-trip through JSON
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError
from splunkgate_core.audit_report import AuditReport, audit_report_to_json_schema
from splunkgate_core.verdict import Severity, Verdict, VerdictLabel


def _make_verdict(*, surface: str = "mcp_audit", offset_s: int = 0) -> Verdict:
    """Build a Verdict at a deterministic timestamp offset."""
    return Verdict(
        trace_id=uuid4(),
        timestamp=datetime(2026, 6, 9, 12, 0, 0, tzinfo=UTC) + timedelta(seconds=offset_s),
        verdict=VerdictLabel.ALLOW,
        severity=Severity.NONE_SEVERITY,
        rules=[],
        surface=surface,  # type: ignore[arg-type]
        latency_ms=1.0,
    )


def test_audit_report_with_three_verdicts_validates() -> None:
    """3 verdicts → event_count=3 + verdicts list of length 3."""
    trace_id = uuid4()
    verdicts = [_make_verdict(offset_s=i) for i in range(3)]
    report = AuditReport(
        trace_id=trace_id,
        event_count=3,
        verdicts=verdicts,
        first_seen=verdicts[0].timestamp,
        last_seen=verdicts[-1].timestamp,
        surfaces_seen=["mcp_audit"],
        aggregate={"ALLOW": 3},
    )
    assert report.event_count == 3
    assert len(report.verdicts) == 3
    assert report.first_seen == verdicts[0].timestamp
    assert report.last_seen == verdicts[-1].timestamp


def test_audit_report_empty_result_has_none_envelope() -> None:
    """event_count == 0 → first_seen and last_seen are both None."""
    report = AuditReport(
        trace_id=uuid4(),
        event_count=0,
        verdicts=[],
        first_seen=None,
        last_seen=None,
        surfaces_seen=[],
        aggregate={},
    )
    assert report.event_count == 0
    assert report.verdicts == []
    assert report.first_seen is None
    assert report.last_seen is None
    assert report.surfaces_seen == []


def test_audit_report_first_seen_before_last_seen() -> None:
    """The envelope MUST allow first_seen <= last_seen (consumers index on this)."""
    early = datetime(2026, 6, 9, 12, 0, 0, tzinfo=UTC)
    late = datetime(2026, 6, 9, 12, 5, 0, tzinfo=UTC)
    report = AuditReport(
        trace_id=uuid4(),
        event_count=2,
        verdicts=[_make_verdict(offset_s=0), _make_verdict(offset_s=300)],
        first_seen=early,
        last_seen=late,
        surfaces_seen=["mcp_audit"],
        aggregate={"ALLOW": 2},
    )
    # Sanity inequality the consumers depend on. Pydantic does NOT enforce
    # the ordering by itself (it would over-constrain rebuild); the tool
    # ensures it via `min()` + `max()` on the same iterable.
    assert report.first_seen is not None
    assert report.last_seen is not None
    assert report.first_seen <= report.last_seen


def test_audit_report_rejects_unknown_surface() -> None:
    """surfaces_seen is typed against the Surface Literal — unknown rejected."""
    with pytest.raises(ValidationError):
        AuditReport(
            trace_id=uuid4(),
            event_count=0,
            verdicts=[],
            first_seen=None,
            last_seen=None,
            surfaces_seen=["nonsense_surface"],  # type: ignore[list-item]
            aggregate={},
        )


def test_audit_report_aggregate_accepts_freeform_object_values() -> None:
    """aggregate is dict[str, object] — counts (int), strings, nested dicts all work."""
    aggregate: dict[str, object] = {
        "BLOCK": 2,
        "ALLOW": 1,
        "label": "fsi",
        "nested": {"PII": 1, "PCI": 1},
    }
    report = AuditReport(
        trace_id=uuid4(),
        event_count=3,
        verdicts=[_make_verdict(offset_s=i) for i in range(3)],
        first_seen=datetime(2026, 6, 9, 12, 0, 0, tzinfo=UTC),
        last_seen=datetime(2026, 6, 9, 12, 0, 2, tzinfo=UTC),
        surfaces_seen=["mcp_audit"],
        aggregate=aggregate,
    )
    assert report.aggregate == aggregate


def test_audit_report_round_trips_through_json() -> None:
    """model_dump_json → model_validate_json must round-trip identically."""
    report = AuditReport(
        trace_id=uuid4(),
        event_count=2,
        verdicts=[_make_verdict(offset_s=0), _make_verdict(offset_s=10)],
        first_seen=datetime(2026, 6, 9, 12, 0, 0, tzinfo=UTC),
        last_seen=datetime(2026, 6, 9, 12, 0, 10, tzinfo=UTC),
        surfaces_seen=["mcp_audit", "mcp_score"],
        aggregate={"ALLOW": 2},
    )
    raw = report.model_dump_json()
    restored = AuditReport.model_validate_json(raw)
    assert restored == report


def test_audit_report_extra_forbid_rejects_unknown_field() -> None:
    """extra='forbid' catches typos / drift at the API boundary."""
    with pytest.raises(ValidationError):
        AuditReport(
            trace_id=uuid4(),
            event_count=0,
            verdicts=[],
            first_seen=None,
            last_seen=None,
            surfaces_seen=[],
            aggregate={},
            future_field="nope",  # type: ignore[call-arg]
        )


def test_audit_report_is_frozen() -> None:
    """frozen=True so consumers can hash + memoize without surprise mutation."""
    report = AuditReport(
        trace_id=uuid4(),
        event_count=0,
        verdicts=[],
        first_seen=None,
        last_seen=None,
        surfaces_seen=[],
        aggregate={},
    )
    with pytest.raises(ValidationError):
        report.event_count = 99  # type: ignore[misc]


def test_audit_report_json_schema_helper_returns_pydantic_schema() -> None:
    """audit_report_to_json_schema() == AuditReport.model_json_schema()."""
    assert audit_report_to_json_schema() == AuditReport.model_json_schema()
