# Story — AI Defense client circuit breaker (open / half-open / closed)

**ID:** story-judges-03-ai-defense-circuit-breaker-tenacity
**Epic:** EPIC-04 — Cisco AI Defense Inspection API client
**Depends on:** story-judges-02-ai-defense-httpx-client-with-retries
**Estimate:** ~2h
**Status:** PENDING

---

## User story

**As a** SplunkGate operator running the judgment layer under load
**I want to** stop hammering the AI Defense endpoint after 3 consecutive failures and have the client trip open for 30 seconds before probing recovery
**So that** a regional outage cannot exhaust the per-app quota of 10 million queries/year or stack thousands of in-flight requests inside a single agent run

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `packages/splunkgate_judges/src/splunkgate_judges/_circuit_breaker.py` — NEW — `CircuitBreaker` class: states `CLOSED`/`OPEN`/`HALF_OPEN`, configurable `failure_threshold: int = 3`, `open_duration_s: float = 30.0`, `half_open_probe_count: int = 1`; methods `record_success()`, `record_failure()`, `allow_request() -> bool`, `state` property; emits structlog events `aidefense.cb.opened`, `aidefense.cb.half_open`, `aidefense.cb.closed`; asyncio-safe via `asyncio.Lock`
- `packages/splunkgate_judges/src/splunkgate_judges/ai_defense.py` — UPDATE — instantiate a `CircuitBreaker` on the client; wrap the tenacity retry loop; raise `AIDefenseCircuitOpenError` when `allow_request()` returns False; record success/failure after each upstream attempt
- `packages/splunkgate_judges/src/splunkgate_judges/_errors.py` — UPDATE — add `AIDefenseCircuitOpenError(AIDefenseError)`
- `packages/splunkgate_judges/tests/test_circuit_breaker.py` — NEW — ≥ 12 tests: closed→open after 3 consecutive failures; open→half_open after 30s elapsed; half_open success → closed; half_open failure → open (re-trips); successes reset the failure count while closed; concurrent failures are counted atomically; `allow_request()` returns False while open; structlog state-transition events fire in order; clock is faked via a deterministic `time_source` callable; open_duration_s respected; trip threshold is configurable; half_open_probe_count gates parallel probes
- `packages/splunkgate_judges/tests/test_ai_defense_client_circuit_breaker.py` — NEW — ≥ 6 respx tests showing client behavior end-to-end: 3 consecutive HTTP 503 trips the breaker; subsequent calls raise `AIDefenseCircuitOpenError` without hitting the wire; after 30s wall clock (faked), one probe is allowed; probe success closes the breaker; probe failure re-opens; reset behavior across regions is independent (one breaker per client instance)

The coding agent must NOT modify files outside this map without re-checking `CLAUDE.md`.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given a fresh CircuitBreaker(failure_threshold=3, open_duration_s=30.0)
When  record_failure() is called 3 times consecutively
Then  state == "OPEN"
And   allow_request() returns False
And   exactly 1 "aidefense.cb.opened" structlog event has been emitted

Given a CircuitBreaker in state OPEN with elapsed=30.1s on the injected time_source
When  allow_request() is called
Then  it returns True
And   state transitions to "HALF_OPEN"
And   exactly 1 "aidefense.cb.half_open" event has been emitted

Given a CircuitBreaker in state HALF_OPEN
When  record_success() is called
Then  state transitions to "CLOSED"
And   the internal failure counter is reset to 0
And   exactly 1 "aidefense.cb.closed" event has been emitted

Given a CircuitBreaker in state HALF_OPEN
When  record_failure() is called
Then  state transitions back to "OPEN"
And   the open-timer restarts

Given the AIDefenseClient with respx returning HTTP 503 indefinitely
When  inspect_chat is invoked 4 times sequentially
Then  the first call retries per tenacity rules and ultimately fails
And   the 4th call raises AIDefenseCircuitOpenError without any wire activity
And   the respx mock records no more than 3 HTTP attempts total (or as many as tenacity attempts for the first call before tripping)

Given test files for this story
When  `uv run pytest packages/splunkgate_judges/tests/test_circuit_breaker.py packages/splunkgate_judges/tests/test_ai_defense_client_circuit_breaker.py -v` runs
Then  ≥ 18 tests pass and 0 fail

Given `uv run mypy --strict packages/splunkgate_judges/src/splunkgate_judges/_circuit_breaker.py`
When  it runs
Then  exit code is 0

Given each modified or new file
When  wc -l is run
Then  each file is ≤ 400 LOC
```

---

## Shell verification

The coding agent runs this to confirm the story is done before opening a PR:

```bash
# Tests pass
uv run pytest packages/splunkgate_judges/tests/test_circuit_breaker.py packages/splunkgate_judges/tests/test_ai_defense_client_circuit_breaker.py -v 2>&1 | grep -cE "PASSED"
# Must output >= 18

# State-transition sanity from a quick Python session
uv run python -c "
import asyncio
from splunkgate_judges._circuit_breaker import CircuitBreaker

async def main():
    t = [0.0]
    cb = CircuitBreaker(failure_threshold=3, open_duration_s=30.0, time_source=lambda: t[0])
    assert cb.state == 'CLOSED'
    for _ in range(3):
        await cb.record_failure()
    assert cb.state == 'OPEN'
    assert not await cb.allow_request()
    t[0] = 31.0
    assert await cb.allow_request()
    assert cb.state == 'HALF_OPEN'
    await cb.record_success()
    assert cb.state == 'CLOSED'
    print('OK')

asyncio.run(main())
"
# Must print 'OK'

# Strict typecheck
uv run mypy --strict packages/splunkgate_judges/src/splunkgate_judges/_circuit_breaker.py packages/splunkgate_judges/src/splunkgate_judges/ai_defense.py
# Must exit 0

# 400-LOC cap
for f in packages/splunkgate_judges/src/splunkgate_judges/_circuit_breaker.py packages/splunkgate_judges/src/splunkgate_judges/ai_defense.py packages/splunkgate_judges/src/splunkgate_judges/_errors.py; do
  lines=$(wc -l < "$f")
  [ "$lines" -gt 400 ] && { echo "FAIL: $f has $lines LOC"; exit 1; }
done
# Must exit 0

# §14 clean on production code
grep -rE "(mock|fake|dummy|hardcoded|simulated)" packages/splunkgate_judges/src/splunkgate_judges/_circuit_breaker.py
# Must output nothing
```

---

## Notes for coding agent

- **Per `../../../context/07-cisco-stack/01-ai-defense-deep.md` §8** and **per `../../../context/HALLUCINATION-AUDIT.md`, the 10M queries/AI-app/year quota is verified.** That is the budget the breaker exists to protect — burning even 0.1% of it during a regional outage during a demo would be a footgun.
- Use a pluggable `time_source: Callable[[], float] = time.monotonic` constructor parameter so tests can fake the 30-second wait without `asyncio.sleep`. Don't use `freezegun` — the time_source pattern is cleaner and keeps the breaker library-free except for `asyncio`.
- Use `asyncio.Lock` to serialize state transitions; the breaker can be hit concurrently from many in-flight inspect calls inside a single FastAPI worker.
- Tenacity already retries inside the client (story-judges-02). The breaker sits OUTSIDE the tenacity loop: tenacity exhausts attempts → final failure increments the breaker counter by 1, not by `tenacity.stop_after_attempt(3)` × N. Each user-visible `inspect_chat()` failure is one breaker tick.
- The breaker is per-`AIDefenseClient` instance. **Do not** make it module-level — the orchestrator may construct multiple clients (one per region for failover) and they need independent breakers.
- **Per `../../../context/07-cisco-stack/03-foundation-sec-models.md`, Foundation-Sec is positioned by Cisco as security copilot/generator, NOT as classifier. Used as EXPLAINER only.** When the breaker is open, SplunkGate surfaces fall back to the cheap `splunklib.ai.security.detect_injection` regex path and skip the Foundation-Sec explanation step — the explainer should not be called when there is no verdict to explain.
- HALF_OPEN probe gating: while one probe is in flight, additional `allow_request()` callers must return False to avoid a thundering-herd recovery. Use a counter (`_in_flight_probes`) compared to `half_open_probe_count`.
- Structlog event keys: `event`, `state_from`, `state_to`, `failure_count`, `since_open_s`. Keep them stable for downstream Splunk parsing.
- Cisco AI Defense Explorer Edition (`https://explorer.aidefense.cisco.com/`, March 23 2026 launch, free US-corp-email signup) is the demo-recording path — the demo script can deliberately trigger a 503-loop against a paused Explorer Edition tenant to show the breaker tripping live.
