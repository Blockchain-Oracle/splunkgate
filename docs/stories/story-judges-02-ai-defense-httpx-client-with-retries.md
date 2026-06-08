# Story — AI Defense async httpx client with retries

**ID:** story-judges-02-ai-defense-httpx-client-with-retries
**Epic:** EPIC-04 — Cisco AI Defense Inspection API client
**Depends on:** story-judges-01-ai-defense-request-response-models
**Estimate:** ~2h
**Status:** PENDING

---

## User story

**As a** judgment-layer developer
**I want to** call the Cisco AI Defense Inspection API over an async httpx client with structured logging, regional endpoint routing, and tenacity-driven retries
**So that** every SplunkGate surface can submit prompts/responses for inspection without each surface re-implementing auth, region selection, retry, or log shape

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `packages/splunkgate_judges/src/splunkgate_judges/ai_defense.py` — NEW — `AIDefenseClient` async class: constructor takes `api_key: str | None`, `region: Literal["us","eu","ap","fed"]`, `timeout_s: float = 10.0`; exposes `async def inspect_chat(req: InspectRequest) -> InspectResponse`; sets `X-Cisco-AI-Defense-API-Key` header; uses `httpx.AsyncClient`; emits structlog events `aidefense.request.start`, `aidefense.request.success`, `aidefense.request.failure` with `trace_id`, `region`, `rules_count`, `latency_ms`
- `packages/splunkgate_judges/src/splunkgate_judges/_regions.py` — NEW — `REGION_BASE_URLS: dict[str, str]` mapping `"us"` → `https://us.api.inspect.aidefense.security.cisco.com`, `"eu"` → `https://eu.api.inspect.aidefense.security.cisco.com`, `"ap"` → `https://ap.api.inspect.aidefense.security.cisco.com`, `"fed"` → `https://fed.api.inspect.aidefense.security.cisco.com` (FedRAMP path); `INSPECT_CHAT_PATH = "/api/v1/inspect/chat"`
- `packages/splunkgate_judges/tests/test_ai_defense_client.py` — NEW — ≥ 10 respx-mocked tests covering: happy path returns parsed `InspectResponse`; auth header is set; regional routing routes to correct base URL; HTTP 5xx triggers retry; HTTP 4xx does NOT retry; timeout raises `AIDefenseTimeoutError`; structlog events fire with expected keys; trace_id propagates; `mock_url` regex covers all 4 regions; latency_ms is recorded
- `packages/splunkgate_judges/src/splunkgate_judges/_errors.py` — NEW — `AIDefenseError`, `AIDefenseAuthError`, `AIDefenseTimeoutError`, `AIDefenseUpstreamError` (all subclass `splunkgate_core.errors.SplunkGateError`)

The coding agent must NOT modify files outside this map without re-checking `CLAUDE.md`.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given AIDefenseClient is constructed with region="us"
When  inspect_chat is called and respx mocks a 200 response with the documented JSON shape
Then  the result parses as InspectResponse with severity=HIGH and rules[0].rule_name=="PII"
And   the request URL hostname is "us.api.inspect.aidefense.security.cisco.com"
And   the request header "X-Cisco-AI-Defense-API-Key" equals the configured api_key

Given AIDefenseClient is constructed with region="eu"
When  inspect_chat is called with respx mocking a 200 response
Then  the request URL hostname is "eu.api.inspect.aidefense.security.cisco.com"

Given AIDefenseClient is constructed with region="ap"
When  inspect_chat is called with respx mocking a 200 response
Then  the request URL hostname is "ap.api.inspect.aidefense.security.cisco.com"

Given AIDefenseClient is constructed with region="fed"
When  inspect_chat is called with respx mocking a 200 response
Then  the request URL hostname is "fed.api.inspect.aidefense.security.cisco.com"

Given respx returns HTTP 503 twice and then HTTP 200
When  inspect_chat is called
Then  it retries and returns an InspectResponse
And   the structlog stream contains exactly 2 "aidefense.request.failure" events and 1 "aidefense.request.success" event

Given respx returns HTTP 401
When  inspect_chat is called
Then  AIDefenseAuthError is raised
And   no retries are attempted (4xx is non-retryable)

Given the AIDefenseClient is constructed with timeout_s=0.001 and respx never responds
When  inspect_chat is called
Then  AIDefenseTimeoutError is raised within 1 second

Given the test file packages/splunkgate_judges/tests/test_ai_defense_client.py exists
When  `uv run pytest packages/splunkgate_judges/tests/test_ai_defense_client.py -v` runs
Then  ≥ 10 tests pass and 0 fail

Given the src files for this story
When  `uv run mypy --strict packages/splunkgate_judges/src/splunkgate_judges/ai_defense.py packages/splunkgate_judges/src/splunkgate_judges/_regions.py packages/splunkgate_judges/src/splunkgate_judges/_errors.py` runs
Then  exit code is 0

Given each modified source file
When  wc -l is run on each
Then  each file is ≤ 400 LOC

Given §14 grep on src
When  `grep -rE "(mock|fake|dummy|hardcoded|simulated)" packages/splunkgate_judges/src/splunkgate_judges/ai_defense.py` runs
Then  the output is empty (mock toggle lives in a separate ai_defense_mock.py file per story-judges-04)
```

---

## Shell verification

The coding agent runs this to confirm the story is done before opening a PR:

```bash
# Tests pass
uv run pytest packages/splunkgate_judges/tests/test_ai_defense_client.py -v 2>&1 | grep -cE "PASSED"
# Must output >= 10

# Region routing sanity
uv run python -c "
from splunkgate_judges._regions import REGION_BASE_URLS, INSPECT_CHAT_PATH
assert REGION_BASE_URLS['us'] == 'https://us.api.inspect.aidefense.security.cisco.com'
assert REGION_BASE_URLS['eu'] == 'https://eu.api.inspect.aidefense.security.cisco.com'
assert REGION_BASE_URLS['ap'] == 'https://ap.api.inspect.aidefense.security.cisco.com'
assert REGION_BASE_URLS['fed'] == 'https://fed.api.inspect.aidefense.security.cisco.com'
assert INSPECT_CHAT_PATH == '/api/v1/inspect/chat'
print('OK')
"
# Must print 'OK'

# Strict typecheck
uv run mypy --strict packages/splunkgate_judges/src/splunkgate_judges/ai_defense.py packages/splunkgate_judges/src/splunkgate_judges/_regions.py packages/splunkgate_judges/src/splunkgate_judges/_errors.py
# Must exit 0

# 400-LOC cap on each new file
for f in packages/splunkgate_judges/src/splunkgate_judges/ai_defense.py packages/splunkgate_judges/src/splunkgate_judges/_regions.py packages/splunkgate_judges/src/splunkgate_judges/_errors.py; do
  lines=$(wc -l < "$f")
  [ "$lines" -gt 400 ] && { echo "FAIL: $f has $lines LOC"; exit 1; }
done
# Must exit 0

# §14 clean on production code
grep -rE "(mock|fake|dummy|hardcoded|simulated)" packages/splunkgate_judges/src/splunkgate_judges/ai_defense.py
# Must output nothing

# No verify=False slipped in
grep -nE "verify\s*=\s*False" packages/splunkgate_judges/src/splunkgate_judges/ai_defense.py
# Must output nothing (banned per architecture.md hard rule 7)
```

---

## Notes for coding agent

- **Per `../../../context/07-cisco-stack/01-ai-defense-deep.md` §2**, authentication is the header `X-Cisco-AI-Defense-API-Key: <generated api key>` — verbatim. Do not invent a different header name.
- **Per `../../../context/07-cisco-stack/01-ai-defense-deep.md` §3**, the publicly documented regional endpoints are US, EU, AP. The `fed.` FedRAMP variant is NOT in the public docs (logged as open question in §10) — include it as a documented opt-in, with a clear docstring noting it is unverified-public but follows the documented hostname pattern.
- **Per `../../../context/07-cisco-stack/01-ai-defense-deep.md` §4**, the request path is `/api/v1/inspect/chat`.
- **Per `../../../context/07-cisco-stack/01-ai-defense-deep.md` §6, Cisco AI Defense Inspection API response field is `rules`, NOT `triggered_rules`** — the client deserializes into the `InspectResponse` model from story-judges-01 which already enforces this.
- **Per `../../../context/HALLUCINATION-AUDIT.md`, the 10M queries/AI-app/year quota is verified** — log a debug-level structlog event `aidefense.quota.note` once per process startup with `quota_per_app_per_year=10_000_000` so operators see it during demo recordings.
- Use `httpx.AsyncClient(timeout=httpx.Timeout(timeout_s))`. **Never set `verify=False`.** `splunklib/ai/tools.py:308` has `verify=False` for Splunk MCP — this is a documented anti-pattern, not a template.
- Retries: just basic tenacity wiring here (exponential backoff with jitter, 3 attempts) — the open/half-open/closed circuit breaker is a separate story (story-judges-03). Use `tenacity.AsyncRetrying` with `retry=retry_if_exception_type((AIDefenseUpstreamError, httpx.TimeoutException))` and `stop=stop_after_attempt(3)`.
- Structlog keys: `event`, `trace_id`, `region`, `rules_count`, `latency_ms`, `severity`, `is_safe`. Stable names matter for downstream Splunk parsing (`cisco_ai_defense:splunkgate_verdict` sourcetype).
- Cisco AI Defense Explorer Edition (`https://explorer.aidefense.cisco.com/`, March 23 2026, free signup with US-corp email) is the demo-recording target — the Explorer Edition exposes the same Inspection API endpoint shape and an integration-test smoke run against Explorer Edition validates the regional client end-to-end.
