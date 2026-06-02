# Story — SafetyModelMiddleware (post-inference PII/PHI/PCI scan, second half of model_middleware.py)

**ID:** story-mw-04-model-middleware-post-inference-pii-check
**Epic:** EPIC-06 — Surface 1 (aegis-mw middleware library for splunklib.ai)
**Depends on:** story-mw-03-model-middleware-pre-inference-scan, story-foundsec-03-foundation-sec-mock-and-integration-test
**Estimate:** ~2h
**Status:** PENDING

---

## User story

**As a** Splunk agent developer with a regulated-data exposure problem
**I want to** the LLM's output to be scanned for PII / PHI / PCI / Code Detection / data leakage AFTER inference but BEFORE it reaches the user (or downstream tool input), with a Foundation-Sec WHY-string attached when the verdict is non-ALLOW
**So that** regulated data accidentally surfaced by the model gets redacted (MODIFY) or blocked (BLOCK), and the dashboard shows a human-readable explanation for every non-ALLOW verdict

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `packages/aegis_mw/src/aegis_mw/model_middleware.py` — UPDATE — appends the **second half** of `SafetyModelMiddleware.model_middleware`: after `response = await handler(request)` (the `# --- POST-INFERENCE SCAN: see story-mw-04 ---` anchor planted by story-mw-03), insert the post-inference flow: (a) extract `response.message.content` (the AIMessage text); (b) call `aegis_judges.ai_defense.inspect(text, rules_enabled=["PII","PHI","PCI","Code Detection","Sensitive Data"])` — passing the rule subset configured by the active profile via `self._rules_post_inference`; (c) on non-ALLOW verdict, call `aegis_judges.foundation_sec.explain(verdict, text)` (subject to `config.foundation_sec_enabled`) and set `verdict.explanation`; (d) emit verdict via `aegis_core.otel.emit_evaluation_result` with `surface="mw_model"`; (e) BLOCK → raise `aegis_core.errors.ModelOutputBlockedByAegis(verdict)`; (f) MODIFY → return a new `ModelResponse(message=AIMessage(content=verdict.modifications["redacted_text"]), structured_output=response.structured_output)`; (g) ALLOW → return the original response unchanged
- `packages/aegis_mw/src/aegis_mw/_post_inference.py` — NEW — helper `async def post_inference_scan(text: str, profile: Profile, client, foundation_sec_client) -> Verdict` that owns the AI Defense + Foundation-Sec call sequence; isolated so future profile changes do not modify the middleware body
- `packages/aegis_core/src/aegis_core/errors.py` — UPDATE — add `ModelOutputBlockedByAegis(AegisError)` taking `verdict: Verdict`
- `packages/aegis_mw/tests/test_model_middleware_post.py` — NEW — ≥ 14 behavioral tests using `respx` (AI Defense + Foundation-Sec): benign AIMessage ALLOWs through (no Foundation-Sec call made); PII hit (e.g., `"contact me at john.doe@example.com"`) → MODIFY with redacted_text, Foundation-Sec called once, verdict.explanation populated; PHI hit (e.g., `"patient: HbA1c 7.2"`) → MODIFY with explanation; PCI hit (e.g., `"4111 1111 1111 1111"`) → BLOCK raises `ModelOutputBlockedByAegis`; `config.foundation_sec_enabled=False` skips Foundation-Sec call but still produces verdict; OTel event has `aegis.surface="mw_model"` AND `aegis.explanation` attribute populated on non-ALLOW verdicts; latency_ms captured; combined `model_middleware.py` is ≤ 400 LOC (the file-level cap)

The coding agent must NOT modify files outside this map without re-checking `CLAUDE.md`.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given SafetyModelMiddleware wraps an LLM call whose AIMessage output contains no regulated data
When  `uv run pytest packages/aegis_mw/tests/test_model_middleware_post.py::test_allow_passthrough -v` runs
Then  the test passes; the original ModelResponse is returned unchanged; no Foundation-Sec HTTP call is made

Given respx mocks AI Defense to return MEDIUM severity with rule "PII"
And   respx mocks Foundation-Sec to return a WHY-string
When  the middleware processes an AIMessage containing "john.doe@example.com"
Then  exactly one AI Defense call is made with rules_enabled including "PII"
And   exactly one Foundation-Sec call is made
And   the returned ModelResponse has its AIMessage content replaced with verdict.modifications["redacted_text"]
And   the emitted OTel event has aegis.surface="mw_model" and a non-empty gen_ai.evaluation.explanation attribute

Given respx mocks AI Defense to return HIGH severity with rule "PCI"
When  the middleware processes an AIMessage containing a 16-digit credit-card-shaped string
Then  aegis_core.errors.ModelOutputBlockedByAegis is raised
And   the verdict attached to the exception has severity="HIGH" and a populated explanation

Given config.foundation_sec_enabled is False
And   AI Defense returns a non-ALLOW verdict
When  the middleware runs
Then  no Foundation-Sec HTTP call is made
And   verdict.explanation is None
And   the verdict is still emitted via OTel

Given the test suite is run
When  `uv run pytest packages/aegis_mw/tests/test_model_middleware_post.py -v` runs
Then  ≥ 14 tests pass and 0 fail

Given the combined model_middleware.py (story-mw-03 first half + this story's second half)
When  `wc -l packages/aegis_mw/src/aegis_mw/model_middleware.py` runs
Then  the line count is ≤ 400

Given the §14 grep is run on changed source (excluding test files)
When  `grep -rE "(mock|fake|dummy|hardcoded|simulated)" packages/aegis_mw/src/aegis_mw/model_middleware.py packages/aegis_mw/src/aegis_mw/_post_inference.py` runs
Then  the output is empty
```

---

## Shell verification

The coding agent runs this to confirm the story is done before opening a PR:

```bash
# Verify the second half is wired (post-inference seam now executes)
uv run python -c "
import inspect
from aegis_mw.model_middleware import SafetyModelMiddleware
src = inspect.getsource(SafetyModelMiddleware.model_middleware)
# Both halves present: pre-inference (handler call) AND post-inference (Foundation-Sec wiring)
assert 'response = await handler(request)' in src
assert 'foundation_sec' in src.lower() or 'explanation' in src.lower()
print('OK')
"
# Must print 'OK'

# Tests pass — full model middleware suite (pre + post)
uv run pytest packages/aegis_mw/tests/test_model_middleware_pre.py packages/aegis_mw/tests/test_model_middleware_post.py -v 2>&1 | grep -cE "PASSED"
# Must output >= 28 (14 from story-mw-03 + 14 from this story)

# Combined file is ≤ 400 LOC
wc -l packages/aegis_mw/src/aegis_mw/model_middleware.py | awk '{ if ($1 > 400) exit 1 }'
# Must exit 0

# §14 clean
grep -rE "(mock|fake|dummy|hardcoded|simulated)" packages/aegis_mw/src/aegis_mw/model_middleware.py packages/aegis_mw/src/aegis_mw/_post_inference.py
# Must output nothing

# Lint + typecheck
uv run ruff check packages/aegis_mw/
uv run mypy packages/aegis_mw/src/aegis_mw/model_middleware.py packages/aegis_mw/src/aegis_mw/_post_inference.py
# Both must exit 0
```

---

## Notes for coding agent

- **STORY SPLIT — second half of `model_middleware.py`.** Story-mw-03 wrote the pre-inference half and planted the anchor comment `# --- POST-INFERENCE SCAN: see story-mw-04 ---`. This story INSERTS the post-inference logic at exactly that anchor. The anchor stays in the file as a permanent inline citation. The combined file must remain ≤ 400 LOC. If the implementation approaches the cap, extract the rule-subset logic into `_post_inference.py` (already mapped) rather than splitting the middleware class.
- **Per `../../../context/02-agent-frameworks/06-splunklib-ai-deep-read.md` §"Request / response shapes", `model_middleware` returns `ModelResponse(message: AIMessage, structured_output: Any | None)`.** When MODIFY, construct a NEW `ModelResponse` with the redacted `AIMessage(content=...)` — preserve `structured_output` from the original response.
- **Per ADR-003 in `docs/architecture.md`, Foundation-Sec is the EXPLAINER, NOT the classifier.** Cisco AI Defense produces the binary verdict; Foundation-Sec generates the human-readable WHY-string. Do NOT use Foundation-Sec to make BLOCK/ALLOW decisions. If `config.foundation_sec_enabled` is False, skip the Foundation-Sec call entirely and emit the verdict with `explanation=None`.
- **Per `../../../context/07-cisco-stack/01-ai-defense-deep.md` §7, the rule-name spelling is verbatim:** `"PII"`, `"PHI"`, `"PCI"`, `"Code Detection"`. Include ampersands and exact casing.
- **Per the `Verdict` schema in `docs/architecture.md` §"API schemas", `Verdict.rules` is a list of `RuleHit(rule, confidence, source)` — NOT `triggered_rules`.** The audit (`../../../context/HALLUCINATION-AUDIT.md`) logs this historical hallucination. Use the field name `rules` only.
- **Per `../../../context/HALLUCINATION-AUDIT.md`, `AgentLimits` has a typo `max_structured_output_retires` (sic — "retires" not "retries"). Preserve it if touched.** This story does not touch `AgentLimits` directly, but if you read it for any reason, do not "fix" the typo — splunklib.ai 3.0.0 ships it that way and consumers depend on the name.
- The Foundation-Sec client (`aegis_judges.foundation_sec.explain`) was built in EPIC-05. Contract: `async def explain(verdict: Verdict, original_text: str) -> str` — returns a short (≤ 200 chars) WHY-string suitable for the dashboard. Set `verdict.explanation = await foundation_sec.explain(...)` only when verdict.verdict != ALLOW.
- The OTel emission for the post-inference half includes the `gen_ai.evaluation.explanation` attribute when `verdict.explanation` is set. The emitter in `aegis_core.otel` (built in EPIC-03) handles None → attribute omitted. Do not pass empty strings.
- The active profile's `rules_post_inference` list is the subset of AI Defense rule names enabled. Default profile: `["PII", "PHI", "PCI", "Code Detection"]`. Story-mw-07 introduces per-profile rule subsets (`financial_services` emphasizes PCI; `healthcare` emphasizes PHI; `public_sector` emphasizes Code Detection + Sensitive Data).
- The MODIFY path's `redacted_text` field is produced by AI Defense's response (when the rule supports redaction) OR by a deterministic post-processor in `_post_inference.py` that masks matched entities. If the AI Defense response does not carry a redacted variant, the post-processor must produce one — never let an un-redacted text fall through on a MODIFY verdict.
