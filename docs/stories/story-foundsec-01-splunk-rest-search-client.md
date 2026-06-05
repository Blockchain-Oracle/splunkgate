# Story — splunklib REST search client wrapper for Foundation-Sec invocation

**ID:** story-foundsec-01-splunk-rest-search-client
**Epic:** EPIC-05 — Foundation-Sec invocation via `| ai` SPL
**Depends on:** story-core-01-verdict-pydantic-types, story-app-01 (the Splunk app holding the saved search + summary index — new dependency added 2026-06-05)
**Estimate:** ~2h (assumes Transport A path below; +1h if we fall back to Transport B)
**Status:** DEFERRED — pending live verification

---

## ⚠ DEFERRED — read this first (added 2026-06-05)

Live Playwright probe of Abu's Splunk Cloud tenant on 2026-06-05 found three constraints that change this story's design (see ADR-003a in `docs/architecture.md`):

1. **Splunk Cloud Platform 10.4 does NOT bundle `| ai` natively.** "Unknown search command 'ai'" — confirmed via in-tenant SPL run. Requires the **Splunk AI Toolkit** (Splunkbase app 2890) to be installed. AITK install is gated on Splunkbase login credentials Abu is still resetting as of 2026-06-05.
2. **Splunk Cloud REST API on port 8089 is closed** without a Splunk Support ticket. The original story's `splunklib.client.connect(host=..., port=8089, token=session_token, ...)` pattern is **not viable** for Splunk Cloud tenants out of the box. Splunk Cloud does expose the management API on port 443 via the standard tenant URL, but only with a **Splunk Cloud API token** (different from a session token); this requires verification once AITK is installed.
3. **The `| ai` provider= value for Splunk Hosted Models is undocumented in public docs.** Until we run `| ai` against AITK in the live tenant we don't know whether the provider keyword is `splunk_hosted`, `hosted_models`, or something else.

Because of (1), (2), and (3), this story's design needs to **pivot from "direct REST submit" to "saved-search trigger via HEC + summary-index poll"** — see the new design below. Do NOT implement the original `SplunkSearchClient` against port 8089; it will not connect.

### Revised transport (Transport A per ADR-003a)

```
┌────────────┐   1. POST event   ┌──────────────┐
│ middleware │ ───── (HEC) ────▶ │ Splunk Cloud │
│  (Aegis)   │                   │  index=trig  │
└────────────┘                   └──────┬───────┘
       ▲                                │ 2. real-time saved
       │                                │    search triggered
       │ 4. read result row             ▼
       │   (REST search jobs           ┌──────────────┐
       │   on 443 OR re-poll           │ saved search │
       │   via index=results)          │ runs `| ai ` │
       │                               │ pipeline     │
       │                               └──────┬───────┘
       │                                      │ 3. result written
       │                                      │    to summary index
       │                                      ▼
       │                              ┌──────────────┐
       └──────────────────────────────│ index=results│
                                      │ (summary)    │
                                      └──────────────┘
```

The two unknowns that gate which "step 4" we use:
- **U1:** Does Splunk Cloud's tenant URL expose `/services/search/jobs` on port 443 with a Cloud API token? (Testable in 5 minutes once we have a Cloud API token — separate from sc_admin login.)
- **U2:** Does HEC have any "trigger saved search on event" hook, or do we need a 1-second-scheduled saved search polling its own input index? (Latter is the safe default; not real-time but bounded latency.)

### What this story becomes after deferral resolves

If both Transports A1 (REST on 443) and A2 (poll summary index via REST on 443) are viable: rename this story to `story-foundsec-01-search-jobs-cloud-rest-client`, keep most of the code shape from the original spec, but target `host=<tenant>.splunkcloud.com`, `port=443`, `scheme=https`, and the token type becomes "Splunk Cloud API token" (documented in `docs/ops/secrets.md` once story-ops-02 lands).

If REST on 443 also fails: switch to **Transport B** — direct HuggingFace inference from middleware (`fdtn-ai/Foundation-Sec-8B-Instruct`). Story-foundsec-01 then becomes a stub and `story-foundsec-02` carries the full implementation as an HF Inference client. The $1K "Best Use of Splunk Hosted Models" bonus prize is forfeit but the Foundation-Sec demo still works.

### Resume gate

This story un-defers when **all three** are true:
- [ ] AITK installed in Abu's tenant (task #69).
- [ ] `| ai` SPL runs in Search & Reporting without "Unknown search command" — provider keyword + Foundation-Sec model name both known.
- [ ] Either: (a) Splunk Cloud API token obtained AND `/services/search/jobs` on port 443 returns 200 for a trivial `| makeresults` POST, OR (b) decision to drop Transport A and ship Transport B is recorded in a new ADR-003b.

**Until then, do NOT begin implementation** of `foundation_sec.py`, `_foundation_sec_errors.py`, or `test_splunk_search_client.py`. The acceptance criteria below describe the **pre-deferral** design and are kept for reference; they will be rewritten before this story re-enters the sprint queue.

---

## Original spec (pre-2026-06-05, kept for reference — DO NOT IMPLEMENT)

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
