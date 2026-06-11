"""Async Cisco AI Defense Inspection API client.

Per ../../../context/07-cisco-stack/01-ai-defense-deep.md §§ 2-4:
- Header: X-Cisco-AI-Defense-API-Key: <generated api key>
- Path:   POST /api/v1/inspect/chat
- Regions: us / eu / ap (fed is opt-in, undocumented)

Retries: 3 attempts, exponential backoff, retry only on 5xx + TimeoutException.
4xx is non-retryable (caller error — bad key, malformed payload).
TLS verification defaults to True per architecture.md Hard Rule 7; do NOT
disable TLS verification (splunklib/ai/tools.py:308 disables it — documented
anti-pattern, not a template).

Live mode is gated by passing api_key to the constructor. story-judges-04
adds an env-var-toggled stub-client sibling for tests + dev runs without a
real key.
"""

import os
import time
from typing import TYPE_CHECKING, Final, Self

import httpx
import structlog

if TYPE_CHECKING:
    from splunkgate_judges.ai_defense_mock import MockAIDefenseClient
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from splunkgate_judges._circuit_breaker import CircuitBreaker
from splunkgate_judges._errors import (
    AIDefenseAuthError,
    AIDefenseCircuitOpenError,
    AIDefenseTimeoutError,
    AIDefenseUpstreamError,
)
from splunkgate_judges._regions import INSPECT_CHAT_PATH, REGION_BASE_URLS, Region
from splunkgate_judges.ai_defense_types import InspectRequest, InspectResponse

_HTTP_4XX_FLOOR: Final[int] = 400
_HTTP_5XX_FLOOR: Final[int] = 500
_HTTP_6XX_FLOOR: Final[int] = 600
_AUTH_STATUS: Final[frozenset[int]] = frozenset({401, 403})
_QUOTA_PER_APP_PER_YEAR: Final[int] = 10_000_000

# Exception message constants (ruff EM101 — exception strings must be variables).
_MSG_TIMEOUT_AFTER_RETRIES: Final[str] = "Cisco AI Defense Inspection API timed out after retries"
_MSG_RETRY_LOOP_EXITED: Final[str] = "Cisco AI Defense retry loop exited without response"
_MSG_MISSING_API_KEY: Final[str] = (
    "SPLUNKGATE_AI_DEFENSE_API_KEY is unset and SPLUNKGATE_AI_DEFENSE_MOCK is not truthy; "
    "either set SPLUNKGATE_AI_DEFENSE_API_KEY for live mode or SPLUNKGATE_AI_DEFENSE_MOCK=1 "
    "for the deterministic mock client"
)
_MSG_CIRCUIT_OPEN: Final[str] = (
    "Cisco AI Defense client circuit breaker is OPEN — short-circuiting request "
    "to protect the 10M-queries/year quota and the upstream during an outage"
)

_TRUTHY: Final[frozenset[str]] = frozenset({"1", "true", "yes", "on"})

_logger = structlog.get_logger(__name__)
_quota_note_logged = False


class AIDefenseClient:
    """Async client for POST /api/v1/inspect/chat.

    Construct once per process; reuse across calls — httpx.AsyncClient
    connection pooling cuts handshake overhead on busy paths.
    """

    def __init__(
        self,
        api_key: str,
        *,
        region: Region = "us",
        timeout_s: float = 10.0,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        """Wire the regional base URL + auth header + httpx client + breaker.

        The breaker is per-instance — orchestrators that construct one
        client per region for failover get independent breakers (a regional
        outage tripping `us` should not lock `eu`). Pass a custom breaker
        for tests or to share one across regions intentionally.
        """
        self._api_key = api_key
        self._region = region
        self._base_url = REGION_BASE_URLS[region]
        self._url = self._base_url + INSPECT_CHAT_PATH
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s),
            headers={
                "X-Cisco-AI-Defense-API-Key": api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        self._breaker = circuit_breaker or CircuitBreaker()
        _log_quota_note_once()

    async def inspect_chat(
        self,
        request: InspectRequest,
        *,
        trace_id: str | None = None,
    ) -> InspectResponse:
        """POST the request to /api/v1/inspect/chat; retry 5xx + TimeoutException.

        Raises:
            AIDefenseAuthError on 401/403 (no retry).
            AIDefenseTimeoutError on httpx.TimeoutException after retries exhausted.
            AIDefenseUpstreamError on persistent 5xx after retries exhausted.
        """
        _logger.info(
            "aidefense.request.start",
            trace_id=trace_id,
            region=self._region,
        )
        # Breaker check is the OUTERMOST gate. If it's OPEN, we return
        # without touching httpx at all — protecting the 10M-queries/year
        # quota and the upstream during an outage.
        if not await self._breaker.allow_request():
            _logger.warning(
                "aidefense.cb.short_circuit",
                trace_id=trace_id,
                region=self._region,
                state=self._breaker.state,
            )
            raise AIDefenseCircuitOpenError(_MSG_CIRCUIT_OPEN)
        # Track whether a terminal record_*/release was called so the
        # finally block can refund a HALF_OPEN probe slot on the bypass
        # paths (auth errors, malformed-body parse, asyncio.CancelledError,
        # any other unexpected exception). Without this the probe slot
        # leaks and the breaker is stuck HALF_OPEN forever. (PR #126 review.)
        breaker_resolved = False
        start = time.perf_counter()
        try:
            try:
                response = await self._post_with_retry(request, trace_id=trace_id)
            except RetryError as exc:
                # Tenacity exhausted its 3 retries. Tell the breaker — this
                # is ONE failure from its perspective, not three.
                await self._breaker.record_failure()
                breaker_resolved = True
                inner = exc.last_attempt.exception()
                if isinstance(inner, httpx.TimeoutException):
                    raise AIDefenseTimeoutError(_MSG_TIMEOUT_AFTER_RETRIES) from exc
                if isinstance(inner, AIDefenseUpstreamError):
                    # Re-raise the original error preserving its message —
                    # don't double-wrap it inside another AIDefenseUpstreamError.
                    raise inner from exc
                if inner is None:
                    msg = "Cisco AI Defense retry loop ended without an exception"
                    raise AIDefenseUpstreamError(msg) from exc
                msg = f"Cisco AI Defense Inspection API failed after retries: {inner!r}"
                raise AIDefenseUpstreamError(msg) from exc

            latency_ms = (time.perf_counter() - start) * 1000
            if response.status_code in _AUTH_STATUS:
                _logger.warning(
                    "aidefense.request.failure",
                    trace_id=trace_id,
                    region=self._region,
                    status_code=response.status_code,
                    latency_ms=latency_ms,
                )
                msg = (
                    f"Cisco AI Defense returned {response.status_code}: "
                    "bad api_key or missing entitlement"
                )
                raise AIDefenseAuthError(msg)
            if _HTTP_4XX_FLOOR <= response.status_code < _HTTP_5XX_FLOOR:
                _logger.warning(
                    "aidefense.request.failure",
                    trace_id=trace_id,
                    region=self._region,
                    status_code=response.status_code,
                    latency_ms=latency_ms,
                )
                msg = (
                    f"Cisco AI Defense returned client error {response.status_code}: "
                    f"{response.text[:200]}"
                )
                raise AIDefenseUpstreamError(msg)

            parsed = InspectResponse.model_validate_json(response.content)
            # Tell the breaker — a complete-and-parseable 2xx is a real
            # upstream success. Auth/4xx errors above raise before reaching
            # here and are NOT counted as breaker successes OR failures (they
            # mean "the credential is bad", not "the endpoint is down").
            await self._breaker.record_success()
            breaker_resolved = True
            _logger.info(
                "aidefense.request.success",
                trace_id=trace_id,
                region=self._region,
                rules_count=len(parsed.rules),
                severity=parsed.severity.value,
                is_safe=parsed.is_safe,
                latency_ms=latency_ms,
            )
            return parsed
        finally:
            # Any exception path that bypassed record_success/record_failure
            # (auth errors, 4xx, malformed-body parse, CancelledError, …)
            # would otherwise leak a HALF_OPEN probe slot and brick the
            # breaker. Release it explicitly.
            if not breaker_resolved:
                await self._breaker.release_probe()

    async def aclose(self) -> None:
        """Close the underlying httpx client."""
        await self._client.aclose()

    @classmethod
    def from_env(cls) -> "AIDefenseClient | MockAIDefenseClient":
        """Construct the right client based on env vars.

        SPLUNKGATE_AI_DEFENSE_MOCK truthy → MockAIDefenseClient
        else SPLUNKGATE_AI_DEFENSE_API_KEY required → live AIDefenseClient
        else raise AIDefenseAuthError naming the missing env var.

        SPLUNKGATE_AI_DEFENSE_REGION defaults to "us".
        """
        if os.environ.get("SPLUNKGATE_AI_DEFENSE_MOCK", "").strip().lower() in _TRUTHY:
            # Local import — avoids importing the mock module in live deployments.
            from splunkgate_judges.ai_defense_mock import MockAIDefenseClient  # noqa: PLC0415

            _logger.info("aidefense.client.constructed", mode="mock", region="n/a")
            return MockAIDefenseClient()
        api_key = os.environ.get("SPLUNKGATE_AI_DEFENSE_API_KEY", "").strip()
        if not api_key:
            raise AIDefenseAuthError(_MSG_MISSING_API_KEY)
        region_raw = os.environ.get("SPLUNKGATE_AI_DEFENSE_REGION", "us").strip().lower()
        region: Region = "us"
        if region_raw in REGION_BASE_URLS:
            region = region_raw  # narrowing handled at runtime
        _logger.info("aidefense.client.constructed", mode="live", region=region)
        return cls(api_key, region=region)

    async def __aenter__(self) -> Self:
        """Allow `async with AIDefenseClient(...) as client:` usage."""
        return self

    async def __aexit__(self, *_args: object) -> None:
        """Auto-close on context-manager exit."""
        await self.aclose()

    async def _post_with_retry(
        self,
        request: InspectRequest,
        *,
        trace_id: str | None,
    ) -> httpx.Response:
        """Async retry loop: 5xx + httpx.TimeoutException only; 3 attempts."""
        body = request.model_dump_json()
        retrying = AsyncRetrying(
            retry=retry_if_exception_type((AIDefenseUpstreamError, httpx.TimeoutException)),
            stop=stop_after_attempt(3),
            wait=wait_exponential_jitter(initial=0.2, max=5),
            reraise=False,
        )
        async for attempt in retrying:
            with attempt:
                response = await self._client.post(self._url, content=body)
                if _HTTP_5XX_FLOOR <= response.status_code < _HTTP_6XX_FLOOR:
                    _logger.warning(
                        "aidefense.request.failure",
                        trace_id=trace_id,
                        region=self._region,
                        status_code=response.status_code,
                    )
                    msg = f"Cisco AI Defense returned {response.status_code} (retryable)"
                    raise AIDefenseUpstreamError(msg)
                return response
        # AsyncRetrying always raises or returns from inside the loop; reaching
        # here means tenacity gave up without raising — surface a typed error.
        raise AIDefenseUpstreamError(_MSG_RETRY_LOOP_EXITED)


def _log_quota_note_once() -> None:
    """One-time process-startup note about the verified 10M queries/app/year quota."""
    global _quota_note_logged  # noqa: PLW0603 — module-level singleton flag
    if _quota_note_logged:
        return
    _quota_note_logged = True
    _logger.debug(
        "aidefense.quota.note",
        quota_per_app_per_year=_QUOTA_PER_APP_PER_YEAR,
        source="../context/07-cisco-stack/01-ai-defense-deep.md § 8",
    )
