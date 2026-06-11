"""Unit tests for the async CircuitBreaker state machine.

Clock is faked via a deterministic `time_source` callable so the 30-second
open window can be advanced without `asyncio.sleep` or `freezegun`.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest
import structlog
from splunkgate_judges._circuit_breaker import CircuitBreaker
from structlog.testing import capture_logs

if TYPE_CHECKING:
    from collections.abc import Callable


def _make_clock() -> tuple[list[float], Callable[[], float]]:
    """Return (`box`, `now`). Advance time via `box[0] += dt`."""
    box = [0.0]
    return box, lambda: box[0]


# ── State transitions ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_initial_state_is_closed() -> None:
    cb = CircuitBreaker()
    assert cb.state == "CLOSED"
    assert await cb.allow_request() is True


@pytest.mark.asyncio
async def test_three_consecutive_failures_trip_open() -> None:
    _clock, now = _make_clock()
    cb = CircuitBreaker(failure_threshold=3, open_duration_s=30.0, time_source=now)
    for _ in range(3):
        await cb.record_failure()
    assert cb.state == "OPEN"
    assert await cb.allow_request() is False


@pytest.mark.asyncio
async def test_open_to_half_open_after_elapsed_window() -> None:
    clock, now = _make_clock()
    cb = CircuitBreaker(failure_threshold=3, open_duration_s=30.0, time_source=now)
    for _ in range(3):
        await cb.record_failure()
    assert cb.state == "OPEN"
    clock[0] = 30.1
    assert await cb.allow_request() is True
    assert cb.state == "HALF_OPEN"


@pytest.mark.asyncio
async def test_half_open_success_closes_breaker_and_resets_counter() -> None:
    clock, now = _make_clock()
    cb = CircuitBreaker(failure_threshold=3, open_duration_s=30.0, time_source=now)
    for _ in range(3):
        await cb.record_failure()
    clock[0] = 30.1
    await cb.allow_request()  # transition to HALF_OPEN, consume probe slot
    assert cb.state == "HALF_OPEN"
    await cb.record_success()
    assert cb.state == "CLOSED"
    # Counter reset — three more failures (not one) needed to re-trip.
    await cb.record_failure()
    await cb.record_failure()
    assert cb.state == "CLOSED"
    await cb.record_failure()
    assert cb.state == "OPEN"


@pytest.mark.asyncio
async def test_half_open_failure_reopens_breaker_and_restarts_timer() -> None:
    clock, now = _make_clock()
    cb = CircuitBreaker(failure_threshold=3, open_duration_s=30.0, time_source=now)
    for _ in range(3):
        await cb.record_failure()
    clock[0] = 30.1
    await cb.allow_request()  # transition to HALF_OPEN
    await cb.record_failure()
    assert cb.state == "OPEN"
    # Open-timer restarted — needs another 30s from t=30.1, not from t=0.
    clock[0] = 50.0
    assert await cb.allow_request() is False
    clock[0] = 60.2
    assert await cb.allow_request() is True


# ── Counter semantics ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_success_resets_failure_counter_while_closed() -> None:
    cb = CircuitBreaker(failure_threshold=3)
    await cb.record_failure()
    await cb.record_failure()
    await cb.record_success()
    # Counter reset — 3 more failures still needed.
    await cb.record_failure()
    await cb.record_failure()
    assert cb.state == "CLOSED"


@pytest.mark.asyncio
async def test_intermittent_failures_with_successes_do_not_trip() -> None:
    cb = CircuitBreaker(failure_threshold=3)
    for _ in range(10):
        await cb.record_failure()
        await cb.record_success()
    assert cb.state == "CLOSED"


# ── Concurrency ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_concurrent_failures_are_counted_atomically() -> None:
    cb = CircuitBreaker(failure_threshold=10)
    # Hammer the breaker with 10 concurrent failures.
    await asyncio.gather(*(cb.record_failure() for _ in range(10)))
    assert cb.state == "OPEN"


@pytest.mark.asyncio
async def test_half_open_probe_count_caps_parallel_probes() -> None:
    clock, now = _make_clock()
    cb = CircuitBreaker(
        failure_threshold=3,
        open_duration_s=30.0,
        half_open_probe_count=1,
        time_source=now,
    )
    for _ in range(3):
        await cb.record_failure()
    clock[0] = 30.1
    results = await asyncio.gather(*(cb.allow_request() for _ in range(5)))
    # Exactly one caller wins the probe; the rest see False.
    assert sum(results) == 1
    assert cb.state == "HALF_OPEN"


# ── Structlog events ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_opened_event_emitted_on_trip() -> None:
    cb = CircuitBreaker(failure_threshold=3)
    structlog.configure(processors=[structlog.processors.JSONRenderer()])
    with capture_logs() as logs:
        for _ in range(3):
            await cb.record_failure()
    opened = [log for log in logs if log.get("event") == "aidefense.cb.opened"]
    assert len(opened) == 1
    assert opened[0]["state_from"] == "CLOSED"
    assert opened[0]["state_to"] == "OPEN"
    assert opened[0]["failure_count"] == 3


@pytest.mark.asyncio
async def test_half_open_and_closed_events_emitted_in_order() -> None:
    clock, now = _make_clock()
    cb = CircuitBreaker(failure_threshold=3, open_duration_s=30.0, time_source=now)
    for _ in range(3):
        await cb.record_failure()
    clock[0] = 30.1
    structlog.configure(processors=[structlog.processors.JSONRenderer()])
    with capture_logs() as logs:
        await cb.allow_request()
        await cb.record_success()
    event_names = [log["event"] for log in logs if log.get("event", "").startswith("aidefense.cb.")]
    assert event_names == ["aidefense.cb.half_open", "aidefense.cb.closed"]


# ── Configuration validation ─────────────────────────────────────────────


def test_invalid_failure_threshold_rejected() -> None:
    with pytest.raises(ValueError, match="failure_threshold must be >= 1"):
        CircuitBreaker(failure_threshold=0)


def test_invalid_open_duration_rejected() -> None:
    with pytest.raises(ValueError, match="open_duration_s must be > 0"):
        CircuitBreaker(open_duration_s=0)


def test_invalid_probe_count_rejected() -> None:
    with pytest.raises(ValueError, match="half_open_probe_count must be >= 1"):
        CircuitBreaker(half_open_probe_count=0)


@pytest.mark.asyncio
async def test_configurable_failure_threshold_respected() -> None:
    cb = CircuitBreaker(failure_threshold=5)
    for _ in range(4):
        await cb.record_failure()
    assert cb.state == "CLOSED"
    await cb.record_failure()
    assert cb.state == "OPEN"


@pytest.mark.asyncio
async def test_configurable_open_duration_respected() -> None:
    clock, now = _make_clock()
    cb = CircuitBreaker(failure_threshold=1, open_duration_s=5.0, time_source=now)
    await cb.record_failure()
    clock[0] = 4.9
    assert await cb.allow_request() is False
    clock[0] = 5.1
    assert await cb.allow_request() is True


# ── Defensive paths ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_default_time_source_is_monotonic() -> None:
    # Smoke — default time_source resolves to time.monotonic without crashing.
    cb = CircuitBreaker()
    assert await cb.allow_request() is True


# ── PR #126 review fixes ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_release_probe_refunds_half_open_slot() -> None:
    """release_probe() lets a subsequent caller acquire the probe slot."""
    clock, now = _make_clock()
    cb = CircuitBreaker(
        failure_threshold=3,
        open_duration_s=30.0,
        half_open_probe_count=1,
        time_source=now,
    )
    for _ in range(3):
        await cb.record_failure()
    clock[0] = 30.1
    assert await cb.allow_request() is True  # probe consumed
    assert await cb.allow_request() is False  # cap reached
    await cb.release_probe()
    assert await cb.allow_request() is True  # refunded


@pytest.mark.asyncio
async def test_release_probe_is_noop_when_not_half_open() -> None:
    cb = CircuitBreaker()
    await cb.release_probe()  # no exception, no state change
    assert cb.state == "CLOSED"


@pytest.mark.asyncio
async def test_record_failure_in_open_does_not_extend_timer() -> None:
    """The recovery clock is sacrosanct — duplicate failures in OPEN do not push it out."""
    clock, now = _make_clock()
    cb = CircuitBreaker(failure_threshold=3, open_duration_s=30.0, time_source=now)
    for _ in range(3):
        await cb.record_failure()
    assert cb.state == "OPEN"
    # A duplicate record_failure 20s in does NOT reset the 30s timer.
    clock[0] = 20.0
    await cb.record_failure()
    clock[0] = 30.1
    assert await cb.allow_request() is True  # would be False if timer had been reset
    assert cb.state == "HALF_OPEN"


@pytest.mark.asyncio
async def test_duplicate_failure_in_open_logs_warning() -> None:
    cb = CircuitBreaker(failure_threshold=3)
    for _ in range(3):
        await cb.record_failure()
    structlog.configure(processors=[structlog.processors.JSONRenderer()])
    with capture_logs() as logs:
        await cb.record_failure()
    warned = [log for log in logs if log.get("event") == "aidefense.cb.duplicate_failure_in_open"]
    assert len(warned) == 1
