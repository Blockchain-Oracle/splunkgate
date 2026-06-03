"""OpenTelemetry → Splunk HEC exporter for `gen_ai.evaluation.result` events.

Filters captured spans to ONLY ship events whose name is
`gen_ai.evaluation.result` (per story-core-02). For each matching event,
builds the Splunk HEC envelope and POSTs to `/services/collector/event`.

Per ADR-005 the default sourcetype is `cisco_ai_defense:aegis_verdict`,
which colocates Aegis events with Cisco Security Cloud (Splunkbase app
7404, 55K+ installs) so SOC analysts get unified search.

Per architecture.md § "Stack (locked)": httpx (not requests), tenacity
(not hand-rolled backoff). Per Hard Rule 7: TLS verify defaults to True;
`AEGIS_DEV_INSECURE_TLS=1` opt-in for self-signed certs, logs a WARN.
"""

import json
import os
import socket
from collections.abc import Sequence
from typing import Final

import httpx
import structlog
from opentelemetry import trace as otel_trace
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace import TracerProvider as SDKTracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    retry_if_result,
    stop_after_attempt,
    wait_exponential,
)

from aegis_core.errors import ConfigError

EVALUATION_EVENT_NAME: Final[str] = "gen_ai.evaluation.result"
DEFAULT_SOURCETYPE: Final[str] = "cisco_ai_defense:aegis_verdict"
DEFAULT_SOURCE: Final[str] = "aegis-otel"
DEFAULT_INDEX: Final[str] = "main"
DEFAULT_BATCH_SIZE: Final[int] = 50
DEFAULT_FLUSH_INTERVAL_MS: Final[int] = 5_000

_HTTP_5XX_FLOOR: Final[int] = 500
_HTTP_6XX_FLOOR: Final[int] = 600
_HTTP_4XX_FLOOR: Final[int] = 400

_logger = structlog.get_logger(__name__)
_installed_processor: BatchSpanProcessor | None = None


def _retryable_status(response: httpx.Response) -> bool:
    """Tenacity predicate: retry on 5xx; 4xx are caller errors and non-retryable."""
    return _HTTP_5XX_FLOOR <= response.status_code < _HTTP_6XX_FLOOR


class SplunkHECExporter(SpanExporter):
    """Splunk HEC exporter that ships ONLY `gen_ai.evaluation.result` events.

    Aegis-specific by design — not a generic OTel→Splunk shim. If a future
    use case needs the generic case, that's an upstream OTel exporter.
    """

    def __init__(  # noqa: PLR0913 — kwarg-only init mirrors Splunk HEC config surface
        self,
        *,
        hec_url: str,
        hec_token: str,
        index: str = DEFAULT_INDEX,
        sourcetype: str = DEFAULT_SOURCETYPE,
        source: str = DEFAULT_SOURCE,
        verify_tls: bool = True,
        timeout_s: float = 5.0,
    ) -> None:
        """Build a one-shot HEC exporter; reuse one instance per process."""
        self._hec_url = hec_url.rstrip("/") + "/services/collector/event"
        self._hec_token = hec_token
        self._index = index
        self._sourcetype = sourcetype
        self._source = source
        self._host = socket.gethostname()
        self._client = httpx.Client(
            verify=verify_tls,
            timeout=timeout_s,
            headers={
                "Authorization": f"Splunk {hec_token}",
                "Content-Type": "application/json",
            },
        )

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        """Ship every gen_ai.evaluation.result event in spans; retry on 5xx."""
        envelopes = list(self._build_envelopes(spans))
        if not envelopes:
            return SpanExportResult.SUCCESS
        try:
            self._post_with_retry(envelopes)
        except (RetryError, httpx.RequestError) as exc:
            _logger.warning(
                "hec_export_gave_up",
                event_count=len(envelopes),
                error=str(exc),
            )
            return SpanExportResult.FAILURE
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        """Close the underlying httpx client."""
        self._client.close()

    def _build_envelopes(self, spans: Sequence[ReadableSpan]) -> list[dict[str, object]]:
        envelopes: list[dict[str, object]] = []
        for span in spans:
            for event in span.events:
                if event.name != EVALUATION_EVENT_NAME:
                    continue
                envelopes.append(
                    {
                        # Splunk HEC `time` is epoch seconds; OTel event.timestamp
                        # is nanoseconds since epoch.
                        "time": event.timestamp / 1e9,
                        "sourcetype": self._sourcetype,
                        "source": self._source,
                        "index": self._index,
                        "host": self._host,
                        "event": dict(event.attributes or {}),
                    }
                )
        return envelopes

    @retry(
        retry=(retry_if_exception_type(httpx.TransportError) | retry_if_result(_retryable_status)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, max=10),
        reraise=True,
    )
    def _post_with_retry(self, envelopes: list[dict[str, object]]) -> httpx.Response:
        body = "\n".join(_json_dumps_compact(env) for env in envelopes)
        response = self._client.post(self._hec_url, content=body)
        if _HTTP_4XX_FLOOR <= response.status_code < _HTTP_5XX_FLOOR:
            # 4xx is non-retryable; log and return so caller treats it as failure.
            _logger.error(
                "hec_4xx_rejected",
                status_code=response.status_code,
                body=response.text[:500],
            )
        return response


def _json_dumps_compact(obj: dict[str, object]) -> str:
    """Compact JSON encoder (no whitespace) used per Splunk HEC newline-delimited format."""
    return json.dumps(obj, separators=(",", ":"))


def _resolve_env(name: str) -> str | None:
    """Return env var value or None if unset/empty."""
    val = os.environ.get(name, "").strip()
    return val or None


def configure_hec_exporter(  # noqa: PLR0913 — kwarg surface mirrors Splunk HEC config
    hec_url: str | None = None,
    hec_token: str | None = None,
    *,
    index: str | None = None,
    sourcetype: str | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    flush_interval_s: float = 5.0,
) -> None:
    """Install a SplunkHECExporter wrapped in BatchSpanProcessor on the global TracerProvider.

    Env-var fallbacks: AEGIS_SPLUNK_HEC_URL, AEGIS_SPLUNK_HEC_TOKEN,
    AEGIS_SPLUNK_INDEX, AEGIS_SPLUNK_HEC_SOURCETYPE. Kwargs win.

    TLS: defaults to verify=True. AEGIS_DEV_INSECURE_TLS=1 opts in to
    insecure mode (self-signed certs) with a WARN log.
    """
    global _installed_processor  # noqa: PLW0603 — module-level singleton is the intended pattern

    url = hec_url or _resolve_env("AEGIS_SPLUNK_HEC_URL")
    token = hec_token or _resolve_env("AEGIS_SPLUNK_HEC_TOKEN")
    idx = index or _resolve_env("AEGIS_SPLUNK_INDEX") or DEFAULT_INDEX
    stype = sourcetype or _resolve_env("AEGIS_SPLUNK_HEC_SOURCETYPE") or DEFAULT_SOURCETYPE

    if not url:
        msg = "AEGIS_SPLUNK_HEC_URL not set (or pass hec_url kwarg)"
        raise ConfigError(msg)
    if not token:
        msg = "AEGIS_SPLUNK_HEC_TOKEN not set (or pass hec_token kwarg)"
        raise ConfigError(msg)

    insecure = _resolve_env("AEGIS_DEV_INSECURE_TLS") == "1"
    if insecure:
        _logger.warning(
            "hec_tls_verify_disabled",
            reason="AEGIS_DEV_INSECURE_TLS=1 is set; production deployments must verify TLS",
        )

    exporter = SplunkHECExporter(
        hec_url=url,
        hec_token=token,
        index=idx,
        sourcetype=stype,
        verify_tls=not insecure,
    )
    processor = BatchSpanProcessor(
        exporter,
        max_export_batch_size=batch_size,
        schedule_delay_millis=int(flush_interval_s * 1000),
    )
    provider = otel_trace.get_tracer_provider()
    if isinstance(provider, SDKTracerProvider):
        provider.add_span_processor(processor)
    else:
        sdk_provider = SDKTracerProvider()
        sdk_provider.add_span_processor(processor)
        otel_trace.set_tracer_provider(sdk_provider)
    _installed_processor = processor


def shutdown_hec_exporter() -> None:
    """Flush pending events and close the HEC connection."""
    global _installed_processor  # noqa: PLW0603 — module-level singleton is the intended pattern

    if _installed_processor is None:
        return
    _installed_processor.shutdown()  # type: ignore[no-untyped-call]
    _installed_processor = None
