# Story — Foundation-Sec mock + live integration test (Splunk-gated)

**Status:** ⚠ **DEFERRED** (2026-06-05 per ADR-013). Superseded by `story-explainer-01-template-based-verdict-explainer.md`. The template explainer is deterministic so it needs no mock/integration test pair — story-explainer-01's behavioral tests cover the same surface.

**ID:** story-foundsec-03-foundation-sec-mock-and-integration-test
**Epic:** EPIC-05 — Foundation-Sec invocation via `| ai` SPL
**Depends on:** story-foundsec-02-ai-spl-explanation-prompt
**Estimate:** ~1.5h
**Status:** PENDING

---

## User story

**As a** Aegis developer running the full test suite without a Splunk Cloud tenant
**I want to** flip a mock toggle and have `FoundationSecExplainer.explain()` return a deterministic security-domain explanation string, and have a separate live integration test that runs only when `AEGIS_SPLUNK_HEC_TOKEN` (or equivalent Splunk auth env vars) is set
**So that** CI can validate the explainer end-to-end on every push, and the live test reproduces the demo path against the real Splunk Cloud tenant when credentials are available

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `packages/aegis_judges/src/aegis_judges/foundation_sec_mock.py` — NEW — `MockFoundationSecExplainer` class implementing the same `async def explain(ctx: VerdictContext) -> str` interface; deterministic explanation generation that combines the verdict context fields into a security-domain-vocabulary explanation (must mention at minimum: severity, the rule names, an interpretive sentence) — vocabulary set MUST include at least 8 of: `analyst`, `verdict`, `risk`, `policy`, `prompt`, `injection`, `exfiltration`, `safeguard`, `mitigation`, `triage`, `detection`, `classification`, `evidence`, `compliance`
- `packages/aegis_judges/src/aegis_judges/foundation_sec.py` — UPDATE — add `FoundationSecExplainer.from_env()` factory: if `AEGIS_FOUNDATION_SEC_MOCK=1`, returns `MockFoundationSecExplainer`; if `AEGIS_FOUNDATION_SEC_DISABLED=1`, returns a `NullExplainer` that always returns `""`; else constructs the live explainer using `SplunkSearchClient.from_env()` which reads `AEGIS_SPLUNK_HOST`, `AEGIS_SPLUNK_PORT` (default 8089), `AEGIS_SPLUNK_HEC_TOKEN` OR `AEGIS_SPLUNK_TOKEN` (session token — preferred for search-job REST), and raises `FoundationSecAuthError` if neither token env var is set
- `packages/aegis_judges/tests/test_foundation_sec_mock.py` — NEW — ≥ 10 tests: explain returns a non-empty string; explain returns identical output for identical input (deterministic); explain output mentions the severity; explain output mentions each rule name verbatim; explain output contains ≥ 4 security-domain vocabulary terms from the required set; output length is between 80 and 800 chars; concurrent invocations are independent; `from_env()` with `AEGIS_FOUNDATION_SEC_MOCK=1` returns the mock; `from_env()` with `AEGIS_FOUNDATION_SEC_DISABLED=1` returns the null explainer and `explain()` returns `""`; `from_env()` with neither flag and missing Splunk env vars raises `FoundationSecAuthError`
- `packages/aegis_judges/tests/integration/test_foundation_sec_live.py` — NEW — gated on `AEGIS_SPLUNK_HEC_TOKEN` AND `AEGIS_SPLUNK_HOST`; skipped when either is unset; when set, builds a `VerdictContext` with severity HIGH + PII rule + offending text containing an SSN-like pattern, dispatches via the live explainer, asserts the returned explanation: is non-empty, has length ≥ 60, contains at least 3 security-domain vocabulary terms from the same set the mock uses; runs exactly ONE search per CI invocation (quota-respectful)

The coding agent must NOT modify files outside this map without re-checking `CLAUDE.md`.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given the MockFoundationSecExplainer is constructed
When  explain(ctx_A) is awaited twice with the same ctx_A
Then  both calls return the byte-identical string (deterministic)

Given the MockFoundationSecExplainer
When  explain(ctx) is awaited with severity="HIGH", rules=["PII","Prompt Injection"]
Then  the returned string contains "HIGH"
And   contains "PII"
And   contains "Prompt Injection"
And   contains at least 4 distinct strings from the set {"analyst","verdict","risk","policy","prompt","injection","exfiltration","safeguard","mitigation","triage","detection","classification","evidence","compliance"} (case-insensitive)
And   the returned string length is between 80 and 800 characters

Given AEGIS_FOUNDATION_SEC_MOCK=1 is set
When  FoundationSecExplainer.from_env() is called
Then  the returned object's class.__name__ is "MockFoundationSecExplainer"

Given AEGIS_FOUNDATION_SEC_DISABLED=1 is set
When  from_env() is called and explain(ctx) is awaited
Then  the returned string is exactly ""

Given AEGIS_FOUNDATION_SEC_MOCK is unset, AEGIS_FOUNDATION_SEC_DISABLED is unset, AEGIS_SPLUNK_HEC_TOKEN is unset, AEGIS_SPLUNK_TOKEN is unset
When  from_env() is called
Then  FoundationSecAuthError is raised mentioning at least one of "AEGIS_SPLUNK_HEC_TOKEN" or "AEGIS_SPLUNK_TOKEN"

Given AEGIS_SPLUNK_HEC_TOKEN is unset OR AEGIS_SPLUNK_HOST is unset
When  `uv run pytest packages/aegis_judges/tests/integration/test_foundation_sec_live.py -v` runs
Then  every test is skipped and exit code is 0

Given both AEGIS_SPLUNK_HEC_TOKEN and AEGIS_SPLUNK_HOST are set
When  the live integration test runs
Then  the explanation length is ≥ 60 chars
And   the explanation contains ≥ 3 security-domain vocabulary terms (case-insensitive)

Given `uv run pytest packages/aegis_judges/tests/test_foundation_sec_mock.py -v`
When  it runs
Then  ≥ 10 tests pass and 0 fail

Given strict mypy on the new src files
When  `uv run mypy --strict packages/aegis_judges/src/aegis_judges/foundation_sec_mock.py packages/aegis_judges/src/aegis_judges/foundation_sec.py` runs
Then  exit code is 0

Given each new or modified file
When  wc -l is run
Then  each file is ≤ 400 LOC
```

---

## Shell verification

The coding agent runs this to confirm the story is done before opening a PR:

```bash
# Mock tests pass
uv run pytest packages/aegis_judges/tests/test_foundation_sec_mock.py -v 2>&1 | grep -cE "PASSED"
# Must output >= 10

# Live test gates correctly (no env → all skipped, exit 0)
env -u AEGIS_SPLUNK_HEC_TOKEN -u AEGIS_SPLUNK_TOKEN uv run pytest packages/aegis_judges/tests/integration/test_foundation_sec_live.py -v 2>&1 | grep -E "(SKIPPED|skipped)"
# Must show at least one SKIPPED
env -u AEGIS_SPLUNK_HEC_TOKEN -u AEGIS_SPLUNK_TOKEN uv run pytest packages/aegis_judges/tests/integration/test_foundation_sec_live.py
# Must exit 0

# Mock determinism + vocabulary sanity
AEGIS_FOUNDATION_SEC_MOCK=1 uv run python -c "
import asyncio
from uuid import UUID
from aegis_judges._explanation_prompt import VerdictContext
from aegis_judges.foundation_sec import FoundationSecExplainer

async def main():
    ex = FoundationSecExplainer.from_env()
    assert type(ex).__name__ == 'MockFoundationSecExplainer'
    ctx = VerdictContext(
        severity='HIGH', rules=['PII','Prompt Injection'],
        classifications=['PRIVACY_VIOLATION','SECURITY_VIOLATION'],
        offending_text='ssn 123-45-6789', trace_id=UUID(int=1),
    )
    a = await ex.explain(ctx)
    b = await ex.explain(ctx)
    assert a == b, 'non-deterministic mock'
    assert 'HIGH' in a and 'PII' in a and 'Prompt Injection' in a
    vocab = {'analyst','verdict','risk','policy','prompt','injection','exfiltration',
             'safeguard','mitigation','triage','detection','classification','evidence','compliance'}
    hits = sum(1 for v in vocab if v.lower() in a.lower())
    assert hits >= 4, f'only {hits} vocab terms hit'
    assert 80 <= len(a) <= 800, f'length {len(a)} out of bounds'
    print('OK')

asyncio.run(main())
"
# Must print 'OK'

# Disabled mode returns empty string
AEGIS_FOUNDATION_SEC_DISABLED=1 uv run python -c "
import asyncio
from uuid import UUID
from aegis_judges._explanation_prompt import VerdictContext
from aegis_judges.foundation_sec import FoundationSecExplainer

async def main():
    ex = FoundationSecExplainer.from_env()
    ctx = VerdictContext(severity='LOW', rules=[], classifications=[], offending_text='x', trace_id=UUID(int=1))
    assert await ex.explain(ctx) == ''
    print('OK')

asyncio.run(main())
"
# Must print 'OK'

# Strict typecheck
uv run mypy --strict packages/aegis_judges/src/aegis_judges/foundation_sec_mock.py packages/aegis_judges/src/aegis_judges/foundation_sec.py
# Must exit 0

# 400-LOC cap
for f in packages/aegis_judges/src/aegis_judges/foundation_sec_mock.py packages/aegis_judges/src/aegis_judges/foundation_sec.py; do
  lines=$(wc -l < "$f")
  [ "$lines" -gt 400 ] && { echo "FAIL: $f has $lines LOC"; exit 1; }
done
# Must exit 0
```

---

## Notes for coding agent

- **Per `../../../context/07-cisco-stack/03-foundation-sec-models.md`, Foundation-Sec is positioned by Cisco as security copilot/generator, NOT as classifier. Used as EXPLAINER only.** The mock MUST produce explanations, not verdicts. If the mock starts to feel like it's deciding ALLOW/BLOCK, the test contract is wrong — re-read the model card.
- **Per `../../../context/07-cisco-stack/03-foundation-sec-models.md` §1 "Intended use"**, the three documented use case categories are SOC Acceleration ("Automating triage, summarization, case note generation, and evidence collection"), Proactive Threat Defense, Engineering Enablement. The vocabulary set in the acceptance criteria is drawn from these documented intended-use phrases — `triage`, `evidence`, `mitigation`, `detection`, `verdict`, `risk`, `analyst`, `policy`, `compliance` all align with the model's documented purpose.
- **Per `../../../context/HALLUCINATION-AUDIT.md`, the 10M queries/AI-app/year quota is verified** — that quota applies to AI Defense, not Foundation-Sec. The live test runs exactly ONE search invocation per CI run; the integration test must not loop.
- The `AEGIS_FOUNDATION_SEC_DISABLED` env var is the operator's kill switch. When the breaker is engaged or budget is at risk, an operator can set this to suppress all Foundation-Sec calls — the verdict still flows (AI Defense already decided), it just lacks the WHY-string. Architecture-wise this aligns with the explainer-only positioning: explanations are sugar, not a gate.
- The mock explanation must be **deterministic** for the same input — use no `random` calls. A simple template like `f"[SEV={ctx.severity}] The Cisco AI Defense verdict fired on rules: {', '.join(ctx.rules)}. The analyst should triage as {classification_phrase} risk; recommended safeguard: review the policy, isolate the prompt for injection analysis, and capture evidence for compliance."` satisfies the vocabulary and length constraints deterministically.
- Splunk auth env var preference: `AEGIS_SPLUNK_TOKEN` (session token) is preferred for issuing search jobs via REST; `AEGIS_SPLUNK_HEC_TOKEN` is the HEC-write token used by Surface 4. The live test accepts either as a presence signal but the `SplunkSearchClient.from_env()` should prefer `AEGIS_SPLUNK_TOKEN` if both are set, and document this in its docstring with a citation to `../../../context/06-splunk-ai-stack/07-foundation-sec-on-splunk.md`.
- `foundation_sec_mock.py` is a §14 carve-out per `architecture.md` § "Submission checklist gates" (file name signals intent). The grep rule excludes `*_mock.py`.
- Splunk Cloud target verified live at 10.4.2604.5 on Abu's instance — `../../../context/sources/docs-saved/splunk-cloud-live-verification-2026-06-02.md`.
- Cisco AI Defense Explorer Edition (`https://explorer.aidefense.cisco.com/`, March 23 2026 launch, free US-corp-email signup) is the AI Defense demo path. For Foundation-Sec the demo path is Abu's Splunk Cloud tenant — the demo screencast can deliberately flip `AEGIS_FOUNDATION_SEC_MOCK=1` mid-flow to demonstrate that the explainer is replaceable without touching verdict logic.
