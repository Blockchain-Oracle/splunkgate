# Story — splunklib REST search client wrapper for Foundation-Sec invocation

**ID:** story-foundsec-01-splunk-rest-search-client
**Epic:** EPIC-05 — Foundation-Sec invocation via `| ai` SPL
**Depends on:** story-core-01-verdict-pydantic-types
**Estimate:** ~2h
**Status:** PENDING

---

## User story

**As a** Aegis judgment-layer developer
**I want to** issue arbitrary SPL search jobs against Splunk Cloud (specifically `| ai`-prefixed pipelines), poll for completion, and return the result rows as typed Python objects
**So that** EPIC-05's explanation-prompt logic can wrap a verdict context, dispatch it via SPL, and parse the Foundation-Sec model's text completion without re-implementing the SDK lifecycle

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `packages/aegis_judges/src/aegis_judges/foundation_sec.py` — NEW — `SplunkSearchClient` async wrapper class around `splunklib.client.connect` (run sync calls in a thread via `asyncio.to_thread`); methods `async def submit_search(spl: str, *, timeout_s: float = 30.0, earliest_time: str = "-1m", latest_time: str = "now") -> list[dict]`; constructor takes `host`, `port`, `token` (Splunk session token), `scheme: Literal["https"] = "https"`, `verify_tls: bool = True`; raises `FoundationSecSearchError` on any SDK exception; polls via `job.refresh()` until `is_done()` or `timeout_s` elapses
- `packages/aegis_judges/src/aegis_judges/_foundation_sec_errors.py` — NEW — `FoundationSecError`, `FoundationSecAuthError`, `FoundationSecSearchError`, `FoundationSecTimeoutError` (all subclass `aegis_core.errors.AegisError`)
- `packages/aegis_judges/tests/test_splunk_search_client.py` — NEW — ≥ 10 tests using `unittest.mock.patch` on `splunklib.client` (this is the ONE permitted carve-out from the §respx rule — splunklib's surface isn't HTTP-mockable directly): submit_search happy path returns parsed rows; timeout raises `FoundationSecTimeoutError`; bad token raises `FoundationSecAuthError`; SDK raises generic exception → `FoundationSecSearchError`; poll loop respects timeout; row parsing handles empty result; `verify_tls=False` warning logged once at construction; structured log events `foundsec.search.start`, `foundsec.search.success`, `foundsec.search.failure` fire with expected keys

The coding agent must NOT modify files outside this map without re-checking `CLAUDE.md`.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given splunklib.client.connect is patched to return a fake service whose jobs.create returns a job that finishes in 2 polls with one result row {"explanation":"foo"}
When  SplunkSearchClient.submit_search("| ai prompt=\"hi\"") is called
Then  the result is a list containing one dict {"explanation":"foo"}
And   structlog stream contains exactly 1 "foundsec.search.start" and 1 "foundsec.search.success" event

Given splunklib raises an AuthenticationError on connect
When  SplunkSearchClient is constructed with a bad token
Then  FoundationSecAuthError is raised

Given splunklib returns a job that never completes
When  submit_search is called with timeout_s=0.1
Then  FoundationSecTimeoutError is raised within 1 second

Given splunklib raises a generic exception during search
When  submit_search is called
Then  FoundationSecSearchError is raised
And   the original exception is chained via __cause__

Given SplunkSearchClient is constructed with verify_tls=False
When  __init__ completes
Then  exactly 1 structlog warning event "foundsec.tls.insecure" has been emitted

Given the test file
When  `uv run pytest packages/aegis_judges/tests/test_splunk_search_client.py -v` runs
Then  ≥ 10 tests pass and 0 fail

Given the new src files
When  `uv run mypy --strict packages/aegis_judges/src/aegis_judges/foundation_sec.py packages/aegis_judges/src/aegis_judges/_foundation_sec_errors.py` runs
Then  exit code is 0

Given each modified or new file
When  wc -l is run
Then  each file is ≤ 400 LOC

Given §14 grep on src
When  `grep -rE "(mock|fake|dummy|hardcoded|simulated)" packages/aegis_judges/src/aegis_judges/foundation_sec.py` runs
Then  the output is empty

Given the src file
When  `grep -nE "verify\s*=\s*False" packages/aegis_judges/src/aegis_judges/foundation_sec.py` runs
Then  output is empty OR every match is preceded within 3 lines by the comment "AEGIS_DEV_INSECURE_TLS" (per architecture.md hard rule 7)
```

---

## Shell verification

The coding agent runs this to confirm the story is done before opening a PR:

```bash
# Tests pass
uv run pytest packages/aegis_judges/tests/test_splunk_search_client.py -v 2>&1 | grep -cE "PASSED"
# Must output >= 10

# Constructor + error hierarchy sanity
uv run python -c "
from aegis_judges._foundation_sec_errors import (
    FoundationSecError, FoundationSecAuthError,
    FoundationSecSearchError, FoundationSecTimeoutError
)
from aegis_core.errors import AegisError
for cls in (FoundationSecError, FoundationSecAuthError, FoundationSecSearchError, FoundationSecTimeoutError):
    assert issubclass(cls, AegisError), cls
print('OK')
"
# Must print 'OK'

# Strict typecheck
uv run mypy --strict packages/aegis_judges/src/aegis_judges/foundation_sec.py packages/aegis_judges/src/aegis_judges/_foundation_sec_errors.py
# Must exit 0

# 400-LOC cap
for f in packages/aegis_judges/src/aegis_judges/foundation_sec.py packages/aegis_judges/src/aegis_judges/_foundation_sec_errors.py; do
  lines=$(wc -l < "$f")
  [ "$lines" -gt 400 ] && { echo "FAIL: $f has $lines LOC"; exit 1; }
done
# Must exit 0

# §14 clean (no hardcoded explanations etc in production code)
grep -rE "(mock|fake|dummy|hardcoded|simulated)" packages/aegis_judges/src/aegis_judges/foundation_sec.py
# Must output nothing
```

---

## Notes for coding agent

- **Per `../../../context/07-cisco-stack/03-foundation-sec-models.md`, Foundation-Sec is positioned by Cisco as security copilot/generator, NOT as classifier. Used as EXPLAINER only.** This client is the transport layer that downstream code uses to invoke Foundation-Sec as an explanation generator. Do NOT design any API in this story that treats Foundation-Sec output as a classification — that would be off-label per the model card.
- **Per `../../../context/06-splunk-ai-stack/07-foundation-sec-on-splunk.md`**, Foundation-Sec on Splunk Cloud is invoked via the native `| ai` SPL command. This story does NOT prescribe SPL — it just shells out arbitrary SPL. The `| ai prompt=...` SPL is built in story-foundsec-02.
- Splunk SDK lifecycle: `service = splunklib.client.connect(host=host, port=port, token=token, scheme="https", verify=verify_tls)`; `job = service.jobs.create(spl, earliest_time=..., latest_time=...)`; loop `while not job.is_done(): time.sleep(poll_interval_s); job.refresh()`; iterate `splunklib.results.JSONResultsReader(job.results(output_mode="json"))`. All sync — wrap in `asyncio.to_thread`.
- **Architecture.md hard rule 7** bans `verify=False` in production code paths. Honor the `AEGIS_DEV_INSECURE_TLS=1` env-var carve-out: read it inside `__init__`; if set AND `verify_tls=False` was passed explicitly, allow it but emit a single WARNING-level structlog event `foundsec.tls.insecure` referencing the env var.
- `splunklib/ai/tools.py:308` has `verify=False` hard-coded for Splunk's own MCP loopback — that is splunklib's bug, not a template. Do not replicate.
- The token here is a Splunk **session token** (the `Authorization: Splunk <token>` header type), NOT an HEC token. HEC tokens are separate and used elsewhere (Surface 4). Document this clearly in the constructor docstring.
- Splunk Cloud target verified: version 10.4.2604.5 on Abu's instance (`../../../context/sources/docs-saved/splunk-cloud-live-verification-2026-06-02.md`).
- **Per `../../../context/HALLUCINATION-AUDIT.md`, the 10M queries/AI-app/year quota is verified** — that quota applies to AI Defense, not to Foundation-Sec via `| ai`. Foundation-Sec via Splunk Hosted Models has its own pricing (`../../../context/06-splunk-ai-stack/07-foundation-sec-on-splunk.md` §"Accessibility" — unverified whether developer license includes Hosted Models). Add a debug log at startup noting the unverified billing path.
- splunklib stub typing is incomplete; expect to add `# type: ignore[attr-defined]` on `service.jobs.create` and similar calls with inline justification. mypy --strict will require it.
- Cisco AI Defense Explorer Edition (`https://explorer.aidefense.cisco.com/`, March 23 2026 launch, free US-corp-email signup) is the demo-recording path for the AI Defense half of the system — for Foundation-Sec the demo uses Abu's Splunk Cloud tenant with `| ai` enabled.
