"""Behavioral tests for the Splunk HEC exporter.

Uses respx to intercept httpx calls so no real network traffic escapes.
"""

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import cast
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
import respx
from aegis_core.errors import ConfigError
from aegis_core.otel import emit_verdict_event
from aegis_core.otel_hec_exporter import (
    DEFAULT_SOURCETYPE,
    SplunkHECExporter,
    configure_hec_exporter,
    shutdown_hec_exporter,
)
from aegis_core.verdict import RuleHit, Severity, Verdict, VerdictLabel
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

HEC_URL = "https://hec.example.com:8088"
HEC_TOKEN = "11111111-2222-3333-4444-555555555555"  # noqa: S105 — synthetic test fixture, not a real secret


@pytest.fixture(autouse=True)
def _patch_tenacity_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip real wait_exponential sleeps so retry tests run in milliseconds, not seconds."""
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda _seconds: None)


@pytest.fixture
def captured_span(otel_exporter: InMemorySpanExporter) -> Iterator[ReadableSpan]:
    """Emit a sample verdict event inside a span and yield the captured span."""
    otel_exporter.clear()
    tracer = trace.get_tracer(__name__)
    verdict = _sample_verdict()
    with tracer.start_as_current_span("test_span"):
        emit_verdict_event(verdict)
    spans = otel_exporter.get_finished_spans()
    yield cast("ReadableSpan", spans[0])
    otel_exporter.clear()


def _sample_verdict() -> Verdict:
    return Verdict(
        trace_id=uuid4(),
        timestamp=datetime.now(UTC),
        verdict=VerdictLabel.BLOCK,
        severity=Severity.HIGH,
        rules=[RuleHit(rule="Prompt Injection", confidence=0.93, source="ai_defense")],
        surface="mw_model",
        latency_ms=42.0,
        explanation="prompt injection detected",
    )


def _exporter() -> SplunkHECExporter:
    return SplunkHECExporter(hec_url=HEC_URL, hec_token=HEC_TOKEN)


def test_exporter_ships_single_event_with_envelope_keys(
    captured_span: ReadableSpan,
) -> None:
    with respx.mock(base_url=HEC_URL) as mock_router:
        route = mock_router.post("/services/collector/event").mock(
            return_value=httpx.Response(200, json={"text": "Success", "code": 0})
        )
        result = _exporter().export([captured_span])
        assert route.called
        body = json.loads(route.calls.last.request.content.decode("utf-8"))
        for key in ("time", "sourcetype", "source", "event"):
            assert key in body
        assert body["sourcetype"] == DEFAULT_SOURCETYPE
        assert result.name == "SUCCESS"


def test_default_sourcetype_is_cisco_ai_defense_aegis_verdict(
    captured_span: ReadableSpan,
) -> None:
    with respx.mock(base_url=HEC_URL) as mock_router:
        route = mock_router.post("/services/collector/event").mock(
            return_value=httpx.Response(200, json={"text": "Success"})
        )
        _exporter().export([captured_span])
        body = json.loads(route.calls.last.request.content.decode("utf-8"))
        assert body["sourcetype"] == "cisco_ai_defense:aegis_verdict"


def test_authorization_header_uses_splunk_prefix(
    captured_span: ReadableSpan,
) -> None:
    with respx.mock(base_url=HEC_URL) as mock_router:
        route = mock_router.post("/services/collector/event").mock(return_value=httpx.Response(200))
        _exporter().export([captured_span])
        auth = route.calls.last.request.headers["Authorization"]
        assert auth == f"Splunk {HEC_TOKEN}"


def test_index_kwarg_flows_through_to_envelope(captured_span: ReadableSpan) -> None:
    exp = SplunkHECExporter(
        hec_url=HEC_URL,
        hec_token=HEC_TOKEN,
        index="aegis_demo",
    )
    with respx.mock(base_url=HEC_URL) as mock_router:
        route = mock_router.post("/services/collector/event").mock(return_value=httpx.Response(200))
        exp.export([captured_span])
        body = json.loads(route.calls.last.request.content.decode("utf-8"))
        assert body["index"] == "aegis_demo"


def test_retries_on_503_then_succeeds_on_200(captured_span: ReadableSpan) -> None:
    with respx.mock(base_url=HEC_URL) as mock_router:
        route = mock_router.post("/services/collector/event").mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(503),
                httpx.Response(200, json={"text": "Success"}),
            ]
        )
        result = _exporter().export([captured_span])
        assert route.call_count == 3
        assert result.name == "SUCCESS"


def test_400_is_not_retried(captured_span: ReadableSpan) -> None:
    with respx.mock(base_url=HEC_URL) as mock_router:
        route = mock_router.post("/services/collector/event").mock(
            return_value=httpx.Response(400, json={"text": "bad request"})
        )
        result = _exporter().export([captured_span])
        assert route.call_count == 1
        assert result.name == "SUCCESS"  # 4xx returns success-from-exporter but logs error


def test_non_evaluation_events_are_filtered_out(
    otel_exporter: InMemorySpanExporter,
) -> None:
    """Spans with non-gen_ai.evaluation.result events produce no HEC POST."""
    # Create a fresh span containing only a non-matching event.
    otel_exporter.clear()
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("other_span") as span:
        span.add_event("tool.invoked", attributes={"name": "search"})
    other_span = cast("ReadableSpan", otel_exporter.get_finished_spans()[-1])
    with respx.mock(base_url=HEC_URL, assert_all_called=False) as mock_router:
        route = mock_router.post("/services/collector/event").mock(return_value=httpx.Response(200))
        result = _exporter().export([other_span])
        assert not route.called
        assert result.name == "SUCCESS"


def test_configure_raises_when_url_missing() -> None:
    with patch.dict("os.environ", {}, clear=True):  # noqa: SIM117 — narrow patch scope
        with pytest.raises(ConfigError, match="AEGIS_SPLUNK_HEC_URL"):
            configure_hec_exporter(hec_token=HEC_TOKEN)


def test_configure_raises_when_token_missing() -> None:
    with patch.dict("os.environ", {}, clear=True):  # noqa: SIM117 — narrow patch scope
        with pytest.raises(ConfigError, match="AEGIS_SPLUNK_HEC_TOKEN"):
            configure_hec_exporter(hec_url=HEC_URL)


def test_configure_reads_env_var_fallback() -> None:
    env = {"AEGIS_SPLUNK_HEC_URL": HEC_URL, "AEGIS_SPLUNK_HEC_TOKEN": HEC_TOKEN}
    with patch.dict("os.environ", env, clear=True):
        configure_hec_exporter()
        # Configuration succeeded without raising — env-var fallback worked.
        shutdown_hec_exporter()


def test_shutdown_idempotent_when_not_configured() -> None:
    """shutdown_hec_exporter is safe to call without prior configure."""
    shutdown_hec_exporter()
    shutdown_hec_exporter()


def test_envelope_event_field_contains_otel_attributes(
    captured_span: ReadableSpan,
) -> None:
    with respx.mock(base_url=HEC_URL) as mock_router:
        route = mock_router.post("/services/collector/event").mock(return_value=httpx.Response(200))
        _exporter().export([captured_span])
        body = json.loads(route.calls.last.request.content.decode("utf-8"))
        event_payload = body["event"]
        # The flattened OTel attributes from emit_verdict_event must be inside `event`.
        assert event_payload.get("gen_ai.evaluation.name") == "aegis.safety_verdict"
        assert event_payload.get("aegis.surface") == "mw_model"


def test_custom_sourcetype_kwarg_overrides_default(
    captured_span: ReadableSpan,
) -> None:
    exp = SplunkHECExporter(
        hec_url=HEC_URL,
        hec_token=HEC_TOKEN,
        sourcetype="custom:sourcetype",
    )
    with respx.mock(base_url=HEC_URL) as mock_router:
        route = mock_router.post("/services/collector/event").mock(return_value=httpx.Response(200))
        exp.export([captured_span])
        body = json.loads(route.calls.last.request.content.decode("utf-8"))
        assert body["sourcetype"] == "custom:sourcetype"


def test_empty_span_list_is_noop() -> None:
    with respx.mock(base_url=HEC_URL, assert_all_called=False) as mock_router:
        route = mock_router.post("/services/collector/event").mock(return_value=httpx.Response(200))
        result = _exporter().export([])
        assert not route.called
        assert result.name == "SUCCESS"


def test_transport_error_retries_then_succeeds(captured_span: ReadableSpan) -> None:
    with respx.mock(base_url=HEC_URL) as mock_router:
        route = mock_router.post("/services/collector/event").mock(
            side_effect=[
                httpx.ConnectError("connection refused"),
                httpx.Response(200),
            ]
        )
        result = _exporter().export([captured_span])
        assert route.call_count == 2
        assert result.name == "SUCCESS"
