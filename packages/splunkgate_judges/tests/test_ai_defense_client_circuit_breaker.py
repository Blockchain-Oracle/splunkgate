"""End-to-end tests for AIDefenseClient + CircuitBreaker integration.

respx intercepts httpx; the breaker is wired into the client per-instance.
Confirms: 3 consecutive 503-loops trip the breaker; the 4th call short-
circuits without wire activity; a probe call after the open window
elapses; probe success closes the breaker; probe failure re-opens it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest
import respx

if TYPE_CHECKING:
    from collections.abc import Callable
from splunkgate_judges._circuit_breaker import CircuitBreaker
from splunkgate_judges._errors import (
    AIDefenseAuthError,
    AIDefenseCircuitOpenError,
    AIDefenseUpstreamError,
)
from splunkgate_judges._regions import REGION_BASE_URLS
from splunkgate_judges.ai_defense import AIDefenseClient
from splunkgate_judges.ai_defense_types import InspectMessage, InspectRequest

# Low-entropy synthetic value — respx intercepts the HTTP call so the key
# is never sent over the wire. Avoids gitleaks generic-api-key detector
# (which flags the high-entropy synthetic constant used in
# test_ai_defense_client.py because it predates the gitleaks install).
API_KEY = "test-key"
URL = REGION_BASE_URLS["us"] + "/api/v1/inspect/chat"

HAPPY_RESPONSE = {
    "is_safe": True,
    "severity": "NONE_SEVERITY",
    "classifications": [],
    "rules": [],
    "attack_technique": None,
    "explanation": None,
    "event_id": "evt_ok",
    "client_transaction_id": "tx_ok",
}


@pytest.fixture(autouse=True)
def _patch_tenacity_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip wait_exponential_jitter sleeps so tests run in ms."""
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda _s: None)


def _sample_request() -> InspectRequest:
    return InspectRequest(messages=[InspectMessage(role="user", content="hi")])


def _make_clock() -> tuple[list[float], Callable[[], float]]:
    box = [0.0]
    return box, lambda: box[0]


@pytest.mark.asyncio
async def test_three_consecutive_failures_trip_breaker() -> None:
    """3 user-visible failures (each consuming tenacity's 3 attempts) trip the breaker."""
    breaker = CircuitBreaker(failure_threshold=3, open_duration_s=30.0)
    async with AIDefenseClient(API_KEY, region="us", circuit_breaker=breaker) as client:
        with respx.mock() as router:
            router.post(URL).mock(return_value=httpx.Response(503))
            for _ in range(3):
                with pytest.raises(AIDefenseUpstreamError):
                    await client.inspect_chat(_sample_request())
            assert breaker.state == "OPEN"


@pytest.mark.asyncio
async def test_fourth_call_short_circuits_without_wire_activity() -> None:
    """Once OPEN, additional calls raise AIDefenseCircuitOpenError without hitting httpx."""
    breaker = CircuitBreaker(failure_threshold=3, open_duration_s=30.0)
    async with AIDefenseClient(API_KEY, region="us", circuit_breaker=breaker) as client:
        with respx.mock() as router:
            route = router.post(URL).mock(return_value=httpx.Response(503))
            for _ in range(3):
                with pytest.raises(AIDefenseUpstreamError):
                    await client.inspect_chat(_sample_request())
            assert breaker.state == "OPEN"
            # Count wire calls so far — tenacity makes 3 attempts x 3 user
            # calls = 9 HTTP POSTs (or fewer if respx caps).
            calls_before = route.call_count
            with pytest.raises(AIDefenseCircuitOpenError):
                await client.inspect_chat(_sample_request())
            # Short-circuit verified: no new wire activity on the 4th call.
            assert route.call_count == calls_before


@pytest.mark.asyncio
async def test_probe_allowed_after_open_window_elapses() -> None:
    """After open_duration_s elapses, the next call is allowed as a HALF_OPEN probe."""
    clock, now = _make_clock()
    breaker = CircuitBreaker(failure_threshold=3, open_duration_s=30.0, time_source=now)
    async with AIDefenseClient(API_KEY, region="us", circuit_breaker=breaker) as client:
        with respx.mock() as router:
            router.post(URL).mock(return_value=httpx.Response(503))
            for _ in range(3):
                with pytest.raises(AIDefenseUpstreamError):
                    await client.inspect_chat(_sample_request())
            assert breaker.state == "OPEN"
            clock[0] = 30.1
            # Probe is allowed — but it still hits 503 and re-opens the breaker.
            with pytest.raises(AIDefenseUpstreamError):
                await client.inspect_chat(_sample_request())
            assert breaker.state == "OPEN"


@pytest.mark.asyncio
async def test_probe_success_closes_breaker() -> None:
    """A HALF_OPEN probe that returns 200 closes the breaker; subsequent calls flow normally."""
    clock, now = _make_clock()
    breaker = CircuitBreaker(failure_threshold=3, open_duration_s=30.0, time_source=now)
    async with AIDefenseClient(API_KEY, region="us", circuit_breaker=breaker) as client:
        with respx.mock() as router:
            # First three calls fail with 503.
            route = router.post(URL)
            route.mock(return_value=httpx.Response(503))
            for _ in range(3):
                with pytest.raises(AIDefenseUpstreamError):
                    await client.inspect_chat(_sample_request())
            assert breaker.state == "OPEN"
            # Swap in a 200; probe succeeds, breaker closes.
            route.mock(return_value=httpx.Response(200, json=HAPPY_RESPONSE))
            clock[0] = 30.1
            response = await client.inspect_chat(_sample_request())
            assert response.is_safe is True
            assert breaker.state == "CLOSED"


@pytest.mark.asyncio
async def test_probe_failure_reopens_breaker() -> None:
    """A HALF_OPEN probe that fails re-opens the breaker and restarts the timer."""
    clock, now = _make_clock()
    breaker = CircuitBreaker(failure_threshold=3, open_duration_s=30.0, time_source=now)
    async with AIDefenseClient(API_KEY, region="us", circuit_breaker=breaker) as client:
        with respx.mock() as router:
            router.post(URL).mock(return_value=httpx.Response(503))
            for _ in range(3):
                with pytest.raises(AIDefenseUpstreamError):
                    await client.inspect_chat(_sample_request())
            clock[0] = 30.1
            with pytest.raises(AIDefenseUpstreamError):
                await client.inspect_chat(_sample_request())
            assert breaker.state == "OPEN"
            # Timer restarted — even at t=50, still open.
            clock[0] = 50.0
            with pytest.raises(AIDefenseCircuitOpenError):
                await client.inspect_chat(_sample_request())


@pytest.mark.asyncio
async def test_independent_breakers_across_regions() -> None:
    """Two clients (eu / us) have independent breakers — one regional outage doesn't lock the other."""
    breaker_us = CircuitBreaker(failure_threshold=3)
    breaker_eu = CircuitBreaker(failure_threshold=3)
    url_eu = REGION_BASE_URLS["eu"] + "/api/v1/inspect/chat"

    async with (
        AIDefenseClient(API_KEY, region="us", circuit_breaker=breaker_us) as client_us,
        AIDefenseClient(API_KEY, region="eu", circuit_breaker=breaker_eu) as client_eu,
    ):
        with respx.mock() as router:
            router.post(URL).mock(return_value=httpx.Response(503))
            router.post(url_eu).mock(return_value=httpx.Response(200, json=HAPPY_RESPONSE))
            for _ in range(3):
                with pytest.raises(AIDefenseUpstreamError):
                    await client_us.inspect_chat(_sample_request())
            assert breaker_us.state == "OPEN"
            # eu is unaffected — both state AND internal failure counter.
            response = await client_eu.inspect_chat(_sample_request())
            assert response.is_safe is True
            assert breaker_eu.state == "CLOSED"
            assert breaker_eu._failure_count == 0  # noqa: SLF001 — invariant lock


@pytest.mark.asyncio
async def test_auth_error_in_half_open_releases_probe_slot() -> None:
    """An auth error during a HALF_OPEN probe must NOT leak the probe slot.

    Regression test for the PR #126 silent-failure finding: without the
    finally-block probe release, a 401 during recovery left the breaker
    stuck HALF_OPEN with all slots consumed.
    """
    clock, now = _make_clock()
    breaker = CircuitBreaker(failure_threshold=3, open_duration_s=30.0, time_source=now)
    async with AIDefenseClient(API_KEY, region="us", circuit_breaker=breaker) as client:
        with respx.mock() as router:
            # Trip the breaker with 3x503 then swap in a 401 for the probe.
            route = router.post(URL)
            route.mock(return_value=httpx.Response(503))
            for _ in range(3):
                with pytest.raises(AIDefenseUpstreamError):
                    await client.inspect_chat(_sample_request())
            assert breaker.state == "OPEN"
            route.mock(return_value=httpx.Response(401))
            clock[0] = 30.1
            with pytest.raises(AIDefenseAuthError):
                await client.inspect_chat(_sample_request())
            # Without the release: stuck HALF_OPEN with probe slot consumed.
            # With the fix: probe was released, so a second call can also probe.
            assert breaker.state == "HALF_OPEN"
            assert breaker._in_flight_probes == 0  # noqa: SLF001 — invariant lock
            with pytest.raises(AIDefenseAuthError):
                await client.inspect_chat(_sample_request())
