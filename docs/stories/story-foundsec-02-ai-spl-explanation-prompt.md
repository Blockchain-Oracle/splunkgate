# Story — `| ai` SPL explanation-prompt builder + result parser

**ID:** story-foundsec-02-ai-spl-explanation-prompt
**Epic:** EPIC-05 — Foundation-Sec invocation via `| ai` SPL
**Depends on:** story-foundsec-01-splunk-rest-search-client
**Estimate:** ~2h
**Status:** PENDING

---

## User story

**As a** Aegis judgment-layer developer
**I want to** wrap a verdict context (rules fired + severity + offending text) into a `| ai prompt="..." provider=<env> model=foundation-sec-1.1-8b-instruct` SPL query, dispatch it via `SplunkSearchClient`, and parse the model's text completion into a clean explanation string
**So that** every blocked or flagged event in Aegis has a human-readable WHY-string that the SOC analyst and the regulator see on the dashboard — without Foundation-Sec being used as a classifier (which the model card forbids)

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `packages/aegis_judges/src/aegis_judges/foundation_sec.py` — UPDATE — add `FoundationSecExplainer` class taking a `SplunkSearchClient`; method `async def explain(verdict_context: VerdictContext) -> str` returning the explanation text; reads `AEGIS_FOUNDATION_SEC_PROVIDER` env var for the `provider=...` value (defaults to the literal string `"splunk_hosted"` with a single startup WARNING `foundsec.provider.unverified` documenting that the provider name is not confirmed in public docs); reads `AEGIS_FOUNDATION_SEC_MODEL` env var (default `"foundation-sec-1.1-8b-instruct"`)
- `packages/aegis_judges/src/aegis_judges/_explanation_prompt.py` — NEW — pure functions `build_explanation_spl(ctx: VerdictContext, provider: str, model: str) -> str` (returns the SPL string); `parse_explanation_rows(rows: list[dict]) -> str` (extracts and concatenates the `ai_output` / `_raw` field from the result rows); SPL escaping helper `escape_spl_double_quotes(s: str) -> str`; `VerdictContext` Pydantic model with fields `severity`, `rules: list[str]`, `classifications: list[str]`, `offending_text: str`, `trace_id: UUID`
- `packages/aegis_judges/tests/test_explanation_prompt.py` — NEW — ≥ 14 tests: SPL output starts with `| makeresults` or `| inputlookup`-style stub; SPL contains `| ai prompt="..."`; SPL contains `provider=` and `model=foundation-sec-1.1-8b-instruct`; the prompt embeds severity, rule names, classifications; double-quotes in offending text are escaped; SPL injection attempts in offending text (e.g., `" | delete`) are escaped; parse_explanation_rows handles empty list → `""`; parse handles 1 row with `ai_output` field; parse handles `_raw` fallback; missing both fields raises `FoundationSecExplanationParseError`; `AEGIS_FOUNDATION_SEC_PROVIDER` env override is honored; default provider triggers the unverified warning exactly once across multiple instantiations; explainer integration test against mocked SplunkSearchClient
- `packages/aegis_judges/src/aegis_judges/_foundation_sec_errors.py` — UPDATE — add `FoundationSecExplanationParseError(FoundationSecError)`

The coding agent must NOT modify files outside this map without re-checking `CLAUDE.md`.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given a VerdictContext with severity="HIGH", rules=["PII","Prompt Injection"], classifications=["PRIVACY_VIOLATION","SECURITY_VIOLATION"], offending_text="my ssn is 123-45-6789"
When  build_explanation_spl(ctx, provider="splunk_hosted", model="foundation-sec-1.1-8b-instruct") runs
Then  the returned SPL string contains the literal substring `| ai prompt="`
And   contains `provider=splunk_hosted`
And   contains `model=foundation-sec-1.1-8b-instruct`
And   the prompt body references "PII", "Prompt Injection", "PRIVACY_VIOLATION", "SECURITY_VIOLATION", "HIGH"

Given offending_text contains a double-quote: `she said "hi" | delete`
When  build_explanation_spl is called
Then  the resulting SPL has the double-quote escaped (no unescaped `"` that would break the prompt string)
And   the resulting SPL does NOT contain an unintended pipe-delete sequence outside the prompt= argument value

Given parse_explanation_rows is called with [{"ai_output":"Because the message includes a US SSN."}]
When  the function runs
Then  it returns "Because the message includes a US SSN."

Given parse_explanation_rows is called with [{"_raw":"fallback text"}]
When  no ai_output field is present
Then  it returns "fallback text"

Given parse_explanation_rows is called with [{"other":"x"}] (no ai_output, no _raw)
When  the function runs
Then  FoundationSecExplanationParseError is raised

Given AEGIS_FOUNDATION_SEC_PROVIDER=custom_provider is set
When  FoundationSecExplainer is constructed
Then  the SPL built by explain() contains "provider=custom_provider"

Given AEGIS_FOUNDATION_SEC_PROVIDER is unset (default)
When  FoundationSecExplainer is constructed
Then  exactly 1 structlog warning event "foundsec.provider.unverified" is emitted per process (deduped via module-level flag)

Given a mocked SplunkSearchClient whose submit_search returns [{"ai_output":"X"}]
When  explainer.explain(ctx) is awaited
Then  the result is the string "X"
And   submit_search was called with an SPL string containing `provider=` and `model=foundation-sec-1.1-8b-instruct`

Given `uv run pytest packages/aegis_judges/tests/test_explanation_prompt.py -v`
When  it runs
Then  ≥ 14 tests pass and 0 fail

Given strict mypy on the new src files
When  `uv run mypy --strict packages/aegis_judges/src/aegis_judges/_explanation_prompt.py packages/aegis_judges/src/aegis_judges/foundation_sec.py` runs
Then  exit code is 0

Given each new or modified file
When  wc -l is run
Then  each file is ≤ 400 LOC
```

---

## Shell verification

The coding agent runs this to confirm the story is done before opening a PR:

```bash
# Tests pass
uv run pytest packages/aegis_judges/tests/test_explanation_prompt.py -v 2>&1 | grep -cE "PASSED"
# Must output >= 14

# SPL shape sanity
uv run python -c "
from uuid import uuid4
from aegis_judges._explanation_prompt import build_explanation_spl, VerdictContext
ctx = VerdictContext(
    severity='HIGH',
    rules=['PII','Prompt Injection'],
    classifications=['PRIVACY_VIOLATION','SECURITY_VIOLATION'],
    offending_text='my ssn is 123-45-6789',
    trace_id=uuid4(),
)
spl = build_explanation_spl(ctx, provider='splunk_hosted', model='foundation-sec-1.1-8b-instruct')
assert '| ai prompt=\"' in spl
assert 'provider=splunk_hosted' in spl
assert 'model=foundation-sec-1.1-8b-instruct' in spl
for token in ['PII','Prompt Injection','PRIVACY_VIOLATION','SECURITY_VIOLATION','HIGH']:
    assert token in spl, f'missing {token}'
print('OK')
"
# Must print 'OK'

# Injection escape sanity
uv run python -c "
from uuid import uuid4
from aegis_judges._explanation_prompt import build_explanation_spl, VerdictContext
ctx = VerdictContext(
    severity='LOW', rules=[], classifications=[],
    offending_text='she said \"hi\" | delete', trace_id=uuid4(),
)
spl = build_explanation_spl(ctx, provider='splunk_hosted', model='foundation-sec-1.1-8b-instruct')
# the prompt= value must terminate exactly once: at the close of our intended string
between_prompt_and_provider = spl.split('prompt=\"', 1)[1].rsplit(' provider=', 1)[0]
# raw unescaped \" inside the prompt body would cause SPL to mis-parse
assert '\\\\\"' in between_prompt_and_provider or chr(92)+chr(34) in between_prompt_and_provider
print('OK')
"
# Must print 'OK'

# Strict typecheck
uv run mypy --strict packages/aegis_judges/src/aegis_judges/_explanation_prompt.py packages/aegis_judges/src/aegis_judges/foundation_sec.py
# Must exit 0

# 400-LOC cap
for f in packages/aegis_judges/src/aegis_judges/_explanation_prompt.py packages/aegis_judges/src/aegis_judges/foundation_sec.py; do
  lines=$(wc -l < "$f")
  [ "$lines" -gt 400 ] && { echo "FAIL: $f has $lines LOC"; exit 1; }
done
# Must exit 0
```

---

## Notes for coding agent

- **Per `../../../context/07-cisco-stack/03-foundation-sec-models.md`, Foundation-Sec is positioned by Cisco as security copilot/generator, NOT as classifier. Used as EXPLAINER only.** The prompt template MUST ask for a natural-language explanation, NOT a yes/no/severity decision. The verdict has already been decided by AI Defense before this code runs. The prompt should be shaped like: `"Given this Cisco AI Defense verdict (severity={sev}, rules={rules}, classifications={cls}) on the text shown below, explain in 2–3 sentences for a SOC analyst WHY this content fired the listed rules. Do NOT change the verdict; only explain it. Text:\n\n{text}"`. This wording aligns with the model card's "SOC Acceleration" intended use ("summarization, case note generation, and evidence collection").
- **Per `../../../context/06-splunk-ai-stack/07-foundation-sec-on-splunk.md` §"Invocation"**, the `| ai` command exists and accepts `provider=` and `model=` keyword args, but the exact value for `provider=` when invoking Splunk-hosted Foundation-Sec is NOT explicitly documented in the publicly fetched sources — the doc says "Most likely something like `provider=splunk_hosted model=foundation-sec-1.1-8b-instruct` but unverified." Therefore the provider value MUST be env-overridable and the default must emit a single warning at startup. Do not hardcode an undocumented provider name without an opt-out.
- **Per `../../../context/HALLUCINATION-AUDIT.md`, the 10M queries/AI-app/year quota is verified** — that is the AI Defense quota, not Foundation-Sec. Foundation-Sec on Splunk Hosted Models has its own (unverified) pricing. Log a debug startup event noting the explanation step is the optional WHY-string and can be disabled via `AEGIS_FOUNDATION_SEC_DISABLED=1` to keep cost predictable during eval.
- The `| ai` command syntax via `splunklib.ai` runs entirely on LangChain v1 (`backend_registry.py:18-24` hardcodes `langchain_backend_factory`) per `architecture.md` § "Stack". This is informational — this story dispatches the SPL through the standard search REST API, not through `splunklib.ai` directly.
- SPL injection escaping: SPL string literals use double-quote delimiters with backslash escaping. The escape function should at minimum escape `"` → `\"` and `\` → `\\` inside the prompt value. Test against `" | delete` style payloads (analogous to SQL injection) since `offending_text` is attacker-controlled by definition.
- The explanation parse step looks for `ai_output` first (most likely field name based on Splunk `| ai` patterns), falls back to `_raw`, fails loudly otherwise. The exact result-row field name is also unverified — leave a TODO with a link to `../../../context/06-splunk-ai-stack/07-foundation-sec-on-splunk.md` and verify on first live run against Abu's tenant.
- Cisco AI Defense Explorer Edition (`https://explorer.aidefense.cisco.com/`, March 23 2026 launch, free US-corp-email signup) is the AI Defense demo-recording path. For Foundation-Sec the demo uses Abu's Splunk Cloud tenant — the demo script SHOULD show the produced SPL string on-screen so judges see the actual `| ai` invocation.
