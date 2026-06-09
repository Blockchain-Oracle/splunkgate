"""Behavioral tests for story-mcp-05: `splunkgate_audit_trace`.

Asserts the 12 BDD acceptance criteria from
`docs/stories/story-mcp-05-tool-audit-trace.md`, with the design-doc
revisions per `docs/plans/2026-06-09-mcp-design.md` applied:

  - AuditReport.aggregate is dict[str, object] (NOT Any)
  - Splunk auth uses USER + PASSWORD (NOT HEC token)
  - SplunkSearchClient lives in splunkgate_judges.splunk_search
  - SPLUNKGATE_DEV_INSECURE_TLS opt-in handled by the search client

No live network: outbound Splunk REST traffic intercepted via `respx`
(documented in `docs/plans/2026-06-09-mcp-design.md` § Test pattern).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import httpx
import pytest
import respx
from opentelemetry import trace
from splunkgate_core.audit_report import AuditReport
from splunkgate_core.errors import ValidationError
from splunkgate_judges._errors import SplunkSearchError
from splunkgate_mcp._test_helpers import list_tools_for_test
from splunkgate_mcp.schemas import AUDIT_REPORT_OUTPUT_SCHEMA
from splunkgate_mcp.tools.audit_trace import (
    AuditTraceInputs,
    audit_trace,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

TOOL_NAME = "splunkgate_audit_trace"

# Synthetic Splunk REST host — respx intercepts every call so we don't
# need a live container. Matches the test_splunk_search.py value.
_HOST = "https://splunk.test.example:8089"
_SEARCH_URL = f"{_HOST}/services/search/jobs"
_USER = "sc_admin"
# Low-entropy placeholder — gitleaks will not flag.
_PASSWORD = "x"  # noqa: S105

_FIXTURE_3EVENTS = Path(__file__).parent / "fixtures" / "splunk_audit_3events.json"


@pytest.fixture(autouse=True)
def _splunk_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wire SPLUNKGATE_SPLUNK_* env vars so SplunkSearchClient.from_env works."""
    monkeypatch.setenv("SPLUNKGATE_SPLUNK_HOST", _HOST)
    monkeypatch.setenv("SPLUNKGATE_SPLUNK_USER", _USER)
    monkeypatch.setenv("SPLUNKGATE_SPLUNK_PASSWORD", _PASSWORD)
    monkeypatch.delenv("SPLUNKGATE_DEV_INSECURE_TLS", raising=False)


@pytest.fixture(autouse=True)
def _restore_bootstrap_registrations() -> None:
    """Re-run the server's idempotent tool bootstrap before each test.

    `test_server_skeleton.py` clears `_REGISTERED_TOOLS` for isolation;
    calling the idempotent ensure_* helpers restores `_ping` + every
    landed tool without spelunking private state.
    """
    from splunkgate_mcp.server import (  # noqa: PLC0415
        _ensure_audit_trace_registered,
        _ensure_check_output_leak_registered,
        _ensure_judge_tool_call_registered,
        _ensure_score_prompt_injection_registered,
        ensure_ping_registered,
    )

    ensure_ping_registered()
    _ensure_score_prompt_injection_registered()
    _ensure_check_output_leak_registered()
    _ensure_judge_tool_call_registered()
    _ensure_audit_trace_registered()


@pytest.fixture
def exporter(otel_exporter: InMemorySpanExporter) -> Iterator[InMemorySpanExporter]:
    """Re-export conftest's shared OTel exporter and clear after each test."""
    otel_exporter.clear()
    yield otel_exporter
    otel_exporter.clear()


def _load_3event_payload() -> dict[str, object]:
    """Read the 3-event Splunk JSON fixture."""
    return json.loads(_FIXTURE_3EVENTS.read_text())


# --- BDD 1+2: tool discoverable + outputSchema -------------------------


def test_tool_is_discoverable_via_list_tools_for_test() -> None:
    """`list_tools_for_test()` includes 'splunkgate_audit_trace'."""
    names = [t.name for t in list_tools_for_test()]
    assert TOOL_NAME in names


def test_tool_output_schema_deep_equals_audit_report_schema() -> None:
    """outputSchema deep-equals `AuditReport.model_json_schema()` (NOT Verdict's).

    Story spec line 41-42: mcp-05 is the ONLY tool whose outputSchema
    differs from the Verdict schema. FastMCP derives it from the
    `-> AuditReport` return annotation.
    """
    tool = next(t for t in list_tools_for_test() if t.name == TOOL_NAME)
    assert tool.outputSchema == AUDIT_REPORT_OUTPUT_SCHEMA
    assert tool.outputSchema == AuditReport.model_json_schema()


# --- BDD 3+4+5: 3-event aggregate ---------------------------------------


async def test_three_events_yield_event_count_three_and_envelope() -> None:
    """3 Splunk-returned events → event_count=3, len(verdicts)=3, first<=last."""
    trace_id = UUID("11111111-1111-1111-1111-111111111111")
    payload = _load_3event_payload()
    with respx.mock() as router:
        router.post(_SEARCH_URL).mock(return_value=httpx.Response(200, json=payload))
        report = await audit_trace(
            AuditTraceInputs(
                trace_id=trace_id,
                eval_dimensions=["verdict", "severity", "surface"],
            ),
        )
    assert report.event_count == 3
    assert len(report.verdicts) == 3
    assert report.first_seen is not None
    assert report.last_seen is not None
    assert report.first_seen <= report.last_seen


async def test_three_events_surfaces_seen_matches_union() -> None:
    """surfaces_seen matches the union of `surface` across returned events."""
    trace_id = UUID("11111111-1111-1111-1111-111111111111")
    payload = _load_3event_payload()
    with respx.mock() as router:
        router.post(_SEARCH_URL).mock(return_value=httpx.Response(200, json=payload))
        report = await audit_trace(
            AuditTraceInputs(trace_id=trace_id, eval_dimensions=["surface"]),
        )
    # Fixture has surfaces: mcp_score, mw_tool, mcp_check_output.
    assert set(report.surfaces_seen) == {"mcp_score", "mw_tool", "mcp_check_output"}


# --- BDD 6: default eval_dimensions ------------------------------------


async def test_default_eval_dimensions_used_when_not_provided() -> None:
    """Default ["verdict","severity","surface"] applied + reflected in SPL."""
    trace_id = uuid4()
    with respx.mock() as router:
        route = router.post(_SEARCH_URL).mock(
            return_value=httpx.Response(200, json={"results": []}),
        )
        await audit_trace(AuditTraceInputs(trace_id=trace_id))
    body = route.calls.last.request.content.decode("utf-8")
    # Form-encoded body — SPL contains the by-clause verbatim.
    assert "by+verdict%2Cseverity%2Csurface" in body or "by verdict,severity,surface" in body


# --- BDD 7+8: custom dimensions reflected verbatim + sourcetype --------


async def test_custom_eval_dimensions_reach_spl_verbatim() -> None:
    """Custom eval_dimensions=["severity"] → SPL contains 'by severity'."""
    trace_id = uuid4()
    with respx.mock() as router:
        route = router.post(_SEARCH_URL).mock(
            return_value=httpx.Response(200, json={"results": []}),
        )
        await audit_trace(
            AuditTraceInputs(trace_id=trace_id, eval_dimensions=["severity"]),
        )
    # Form body is URL-encoded; assert against decoded view.
    body = route.calls.last.request.content.decode("utf-8")
    from urllib.parse import parse_qs  # noqa: PLC0415

    parsed = parse_qs(body)
    spl_values = parsed.get("search", [])
    assert spl_values, body
    spl = spl_values[0]
    assert "by severity" in spl, spl


async def test_spl_includes_sourcetype_verbatim() -> None:
    """SPL must include `sourcetype=cisco_ai_defense:splunkgate_verdict`."""
    trace_id = uuid4()
    with respx.mock() as router:
        route = router.post(_SEARCH_URL).mock(
            return_value=httpx.Response(200, json={"results": []}),
        )
        await audit_trace(AuditTraceInputs(trace_id=trace_id))
    body = route.calls.last.request.content.decode("utf-8")
    from urllib.parse import parse_qs  # noqa: PLC0415

    parsed = parse_qs(body)
    spl = parsed["search"][0]
    assert "sourcetype=cisco_ai_defense:splunkgate_verdict" in spl


# --- BDD 9: SPL injection guard ----------------------------------------


async def test_spl_injection_attempt_rejected_before_rest_call() -> None:
    """eval_dimensions=['severity; | delete'] → ValidationError, ZERO REST calls.

    The allowlist guard MUST fire BEFORE the SplunkSearchClient is
    constructed (we never want a malicious dimension list to even
    reach the network layer). Verify via respx.call_count == 0.

    `assert_all_called=False` because the whole point of this test is
    that the registered route is NEVER hit.
    """
    trace_id = uuid4()
    with respx.mock(assert_all_called=False) as router:
        route = router.post(_SEARCH_URL).mock(
            return_value=httpx.Response(200, json={"results": []}),
        )
        with pytest.raises(ValidationError):
            await audit_trace(
                AuditTraceInputs(
                    trace_id=trace_id,
                    eval_dimensions=["severity; | delete"],
                ),
            )
    # CRITICAL: zero outbound requests. The guard runs BEFORE REST.
    assert route.call_count == 0


# --- BDD 10: Splunk REST failure → SplunkSearchError -------------------


async def test_splunk_rest_5xx_raises_splunk_search_error() -> None:
    """Splunk 500 → SplunkSearchError propagates out (FastMCP → isError)."""
    trace_id = uuid4()
    with respx.mock() as router:
        router.post(_SEARCH_URL).mock(
            return_value=httpx.Response(500, text="Splunk internal error"),
        )
        with pytest.raises(SplunkSearchError):
            await audit_trace(AuditTraceInputs(trace_id=trace_id))


# --- BDD 11: empty result → event_count=0 (NOT isError) ----------------


async def test_empty_result_returns_zero_event_count_not_error() -> None:
    """0 events → AuditReport(event_count=0), NOT raised + NOT isError."""
    trace_id = uuid4()
    with respx.mock() as router:
        router.post(_SEARCH_URL).mock(
            return_value=httpx.Response(200, json={"results": []}),
        )
        report = await audit_trace(AuditTraceInputs(trace_id=trace_id))
    assert report.event_count == 0
    assert report.verdicts == []
    assert report.first_seen is None
    assert report.last_seen is None
    assert report.surfaces_seen == []


# --- BDD 12: OTel event w/ surface + custom event_count attr -----------


async def test_otel_event_carries_surface_and_audit_event_count_attr(
    exporter: InMemorySpanExporter,
) -> None:
    """Exactly one `gen_ai.evaluation.result` w/ surface + audit.event_count.

    Spec lines 69-73:
      - exactly one event named "gen_ai.evaluation.result"
      - splunkgate.surface == "mcp_audit"
      - splunkgate.audit.event_count == integer count
    """
    trace_id = UUID("11111111-1111-1111-1111-111111111111")
    payload = _load_3event_payload()
    tracer = trace.get_tracer(__name__)
    with respx.mock() as router:
        router.post(_SEARCH_URL).mock(return_value=httpx.Response(200, json=payload))
        with tracer.start_as_current_span("tools/call"):
            await audit_trace(
                AuditTraceInputs(
                    trace_id=trace_id,
                    eval_dimensions=["verdict", "severity", "surface"],
                ),
            )
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    events = [e for e in spans[0].events if e.name == "gen_ai.evaluation.result"]
    assert len(events) == 1
    attrs = dict(events[0].attributes or {})
    assert attrs["splunkgate.surface"] == "mcp_audit"
    assert attrs["splunkgate.audit.event_count"] == 3


# --- Bonus: empty-result OTel still emits event_count=0 ----------------


async def test_otel_event_emits_zero_event_count_on_empty_result(
    exporter: InMemorySpanExporter,
) -> None:
    """Empty-result path still emits OTel w/ splunkgate.audit.event_count == 0."""
    trace_id = uuid4()
    tracer = trace.get_tracer(__name__)
    with respx.mock() as router:
        router.post(_SEARCH_URL).mock(
            return_value=httpx.Response(200, json={"results": []}),
        )
        with tracer.start_as_current_span("tools/call"):
            await audit_trace(AuditTraceInputs(trace_id=trace_id))
    spans = exporter.get_finished_spans()
    events = [e for span in spans for e in span.events if e.name == "gen_ai.evaluation.result"]
    assert len(events) == 1
    attrs = dict(events[0].attributes or {})
    assert attrs["splunkgate.surface"] == "mcp_audit"
    assert attrs["splunkgate.audit.event_count"] == 0


# --- Bonus: SPL injection variants all rejected -----------------------


@pytest.mark.parametrize(
    "bad_dim",
    [
        "tool_name; | delete",
        "rules | outputlookup",
        "../../../etc/passwd",
        "surface OR 1=1",
        "",  # empty string
    ],
)
async def test_spl_injection_variants_rejected(bad_dim: str) -> None:
    """Any non-allowlist entry → ValidationError, never reaches Splunk.

    `assert_all_called=False` because the registered route MUST NOT be
    called — that's the test contract.
    """
    trace_id = uuid4()
    with respx.mock(assert_all_called=False) as router:
        route = router.post(_SEARCH_URL).mock(
            return_value=httpx.Response(200, json={"results": []}),
        )
        with pytest.raises(ValidationError):
            await audit_trace(
                AuditTraceInputs(trace_id=trace_id, eval_dimensions=[bad_dim]),
            )
    assert route.call_count == 0


# --- Bonus: aggregate shape mirrors stats output ----------------------


async def test_aggregate_dict_mirrors_stats_count_by_verdict() -> None:
    """aggregate keyed by dimension-tuple, values are counts."""
    trace_id = uuid4()
    payload = {
        "results": [
            {"_time": "2026-06-09T12:00:00.000+00:00", "verdict": "BLOCK", "count": "2"},
            {"_time": "2026-06-09T12:01:00.000+00:00", "verdict": "ALLOW", "count": "1"},
        ],
    }
    with respx.mock() as router:
        router.post(_SEARCH_URL).mock(return_value=httpx.Response(200, json=payload))
        report = await audit_trace(
            AuditTraceInputs(trace_id=trace_id, eval_dimensions=["verdict"]),
        )
    assert report.aggregate == {"BLOCK": 2, "ALLOW": 1}


# --- Bonus: round-trip schema validation ------------------------------


async def test_audit_report_round_trip_validates_against_output_schema() -> None:
    """AuditReport.model_dump(mode='json') validates against AUDIT_REPORT_OUTPUT_SCHEMA."""
    import jsonschema  # noqa: PLC0415

    trace_id = uuid4()
    payload = _load_3event_payload()
    with respx.mock() as router:
        router.post(_SEARCH_URL).mock(return_value=httpx.Response(200, json=payload))
        report = await audit_trace(AuditTraceInputs(trace_id=trace_id))
    dumped = report.model_dump(mode="json")
    jsonschema.validate(instance=dumped, schema=AUDIT_REPORT_OUTPUT_SCHEMA)
