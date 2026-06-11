"""Async circuit breaker for the Cisco AI Defense client.

State machine: CLOSED -> OPEN (after N consecutive failures) -> HALF_OPEN
(after `open_duration_s` elapsed) -> CLOSED (on probe success) or back to
OPEN (on probe failure).

The breaker sits OUTSIDE the tenacity retry loop in `AIDefenseClient`. Each
user-visible `inspect_chat()` failure (after tenacity has exhausted its 3
attempts) is one breaker tick — NOT 3. This matches the operator's mental
model: "the endpoint is down" is one signal, not three.

Per `../../../../context/07-cisco-stack/01-ai-defense-deep.md` § 8, the
Cisco AI Defense free-tier quota is 10M queries / AI-application / year.
Burning even 0.1% of that during a regional outage during a demo would be
a footgun. The breaker exists to protect that quota AND to prevent
in-flight-request stacking inside a busy worker.

Design choices:
- Pluggable `time_source: Callable[[], float] = time.monotonic` lets tests
  advance the 30-second wait without `asyncio.sleep` or `freezegun`. Cleaner
  than monkeypatching globals.
- `asyncio.Lock` serializes state transitions; the breaker may be hit
  concurrently from many in-flight inspect calls inside a single FastAPI
  worker.
- `_in_flight_probes` counter caps simultaneous HALF_OPEN probes so we
  don't stampede a recovering endpoint (thundering-herd).
- Per-`AIDefenseClient` instance, NOT module-level — orchestrators may
  construct multiple clients (one per region for failover) and they need
  independent breakers.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Final, Literal

import structlog

if TYPE_CHECKING:
    from collections.abc import Callable

CircuitState = Literal["CLOSED", "OPEN", "HALF_OPEN"]

_logger = structlog.get_logger(__name__)

_DEFAULT_FAILURE_THRESHOLD: Final[int] = 3
_DEFAULT_OPEN_DURATION_S: Final[float] = 30.0
_DEFAULT_HALF_OPEN_PROBE_COUNT: Final[int] = 1


class CircuitBreaker:
    """Async circuit breaker around an upstream dependency."""

    def __init__(
        self,
        *,
        failure_threshold: int = _DEFAULT_FAILURE_THRESHOLD,
        open_duration_s: float = _DEFAULT_OPEN_DURATION_S,
        half_open_probe_count: int = _DEFAULT_HALF_OPEN_PROBE_COUNT,
        time_source: Callable[[], float] | None = None,
    ) -> None:
        """Configure thresholds and inject a clock source.

        `time_source` defaults to `time.monotonic`. Pass a lambda for tests
        so the 30-second open window can be advanced without sleeping. The
        deterministic clock pattern keeps the breaker library-free except
        for `asyncio`.
        """
        if failure_threshold < 1:
            msg = "failure_threshold must be >= 1"
            raise ValueError(msg)
        if open_duration_s <= 0:
            msg = "open_duration_s must be > 0"
            raise ValueError(msg)
        if half_open_probe_count < 1:
            msg = "half_open_probe_count must be >= 1"
            raise ValueError(msg)
        self._failure_threshold = failure_threshold
        self._open_duration_s = open_duration_s
        self._half_open_probe_count = half_open_probe_count
        self._time_source: Callable[[], float] = time_source or time.monotonic
        self._state: CircuitState = "CLOSED"
        self._failure_count: int = 0
        self._opened_at: float | None = None
        self._in_flight_probes: int = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """Return the current state. Snapshot; may be stale by the time the caller acts."""
        return self._state

    async def allow_request(self) -> bool:
        """Return True if a request may proceed.

        Side-effect: transitions OPEN -> HALF_OPEN when the open window has
        elapsed. HALF_OPEN allows at most `half_open_probe_count` parallel
        probes; additional callers see False to avoid thundering-herd
        recovery.
        """
        async with self._lock:
            if self._state == "CLOSED":
                return True
            if self._state == "OPEN":
                if self._opened_at is None:
                    # Defensive: OPEN with no opened_at is a programmer error.
                    return False
                elapsed = self._time_source() - self._opened_at
                if elapsed >= self._open_duration_s:
                    self._transition_to("HALF_OPEN")
                    self._in_flight_probes = 1
                    return True
                return False
            # HALF_OPEN
            if self._in_flight_probes < self._half_open_probe_count:
                self._in_flight_probes += 1
                return True
            return False

    async def record_success(self) -> None:
        """Record an upstream success.

        From CLOSED: reset the failure counter (the breaker has been pacing
        successes and intermittent failures; success resets the run).
        From HALF_OPEN: close the breaker — the probe survived.
        From OPEN: ignored. A success while OPEN means a caller bypassed
        `allow_request()` — log it but don't change state.
        """
        async with self._lock:
            if self._state == "CLOSED":
                self._failure_count = 0
                return
            if self._state == "HALF_OPEN":
                self._in_flight_probes = max(0, self._in_flight_probes - 1)
                self._transition_to("CLOSED")
                return
            # OPEN: success without an allow_request() probe.
            _logger.warning(
                "aidefense.cb.unexpected_success",
                state=self._state,
                failure_count=self._failure_count,
            )

    async def record_failure(self) -> None:
        """Record an upstream failure.

        From CLOSED: increment the failure counter; trip OPEN at threshold.
        From HALF_OPEN: re-open (the probe failed); restart the open timer.
        From OPEN: log + no-op. We deliberately do NOT touch _opened_at —
        the recovery clock is sacrosanct so it's predictable in the Splunk
        dashboard. (PR #126 review: silent timer extension here was an
        observability footgun.)
        """
        async with self._lock:
            if self._state == "CLOSED":
                self._failure_count += 1
                if self._failure_count >= self._failure_threshold:
                    self._transition_to("OPEN")
                return
            if self._state == "HALF_OPEN":
                self._in_flight_probes = max(0, self._in_flight_probes - 1)
                self._transition_to("OPEN")
                return
            # OPEN: caller bypassed allow_request(). Log so the next
            # operator can find the buggy integration; do not touch state.
            _logger.warning(
                "aidefense.cb.duplicate_failure_in_open",
                state=self._state,
                failure_count=self._failure_count,
            )

    async def release_probe(self) -> None:
        """Refund a HALF_OPEN probe slot without recording success or failure.

        Called from `AIDefenseClient.inspect_chat` in `finally` when the
        request raised an exception path that does NOT semantically belong
        to the breaker's failure model (auth errors, malformed-body parse
        errors, asyncio.CancelledError, etc.). Without this, those paths
        leak `_in_flight_probes` and the breaker is stuck in HALF_OPEN
        with all slots consumed.

        No-op when not in HALF_OPEN.
        """
        async with self._lock:
            if self._state == "HALF_OPEN" and self._in_flight_probes > 0:
                self._in_flight_probes -= 1
                _logger.debug(
                    "aidefense.cb.probe_released",
                    in_flight=self._in_flight_probes,
                )

    def _transition_to(self, new_state: CircuitState) -> None:
        """Emit a structlog event for every state change + maintain invariants.

        Sets `_opened_at` on entry to OPEN and clears it on entry to CLOSED.
        Keeping all state-related side-effects here makes future state-change
        additions safer — callers don't have to remember to also set
        `_opened_at` after calling this method.

        Event keys are stable for downstream Splunk parsing:
        `event`, `state_from`, `state_to`, `failure_count`, `since_open_s`.
        """
        if new_state == self._state:
            return
        since_open_s: float | None = None
        if self._opened_at is not None:
            since_open_s = round(self._time_source() - self._opened_at, 3)
        event_name = {
            "OPEN": "aidefense.cb.opened",
            "HALF_OPEN": "aidefense.cb.half_open",
            "CLOSED": "aidefense.cb.closed",
        }[new_state]
        _logger.info(
            event_name,
            state_from=self._state,
            state_to=new_state,
            failure_count=self._failure_count,
            since_open_s=since_open_s,
        )
        self._state = new_state
        if new_state == "CLOSED":
            self._failure_count = 0
            self._opened_at = None
            self._in_flight_probes = 0
        elif new_state == "OPEN":
            # The recovery clock starts here. Set unconditionally so the
            # CLOSED->OPEN and HALF_OPEN->OPEN paths both behave correctly
            # without each caller remembering to set _opened_at.
            self._opened_at = self._time_source()
            self._in_flight_probes = 0
