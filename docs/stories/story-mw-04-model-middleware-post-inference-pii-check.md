# Story — SafetyModelMiddleware (post-inference PII/PHI/PCI scan, second half of model_middleware.py)

**ID:** story-mw-04-model-middleware-post-inference-pii-check
**Epic:** EPIC-06 — Surface 1 (splunkgate-mw middleware library for splunklib.ai)
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

- `packages/splunkgate_mw/src/splunkgate_mw/model_middleware.py` — UPDATE — appends the wiring of `post_inference_scan` into the `model_middleware()` factory composed by story-mw-03. Semantics of the composed factory: pre-scan → BLOCK never invokes the model or the post-scan (raises `ModelInputBlockedBySplunkGate`); pre-scan → MODIFY rewrites the input message THEN calls the model THEN runs post-scan on the model's response; pre-scan → ALLOW calls the model THEN runs post-scan on the response. Wiring details for this story: (a) extract `response.message.content` (the AIMessage text); (b) call `post_inference_scan(response.message.content, profile, ai_defense_client, foundation_sec_client)`; (c) on non-ALLOW verdict, the helper has already populated `verdict.explanation` via the Foundation-Sec call (or left it `None` if `config.foundation_sec_enabled=False`); (d) emit verdict via `splunkgate_core.otel.emit_evaluation_result` with `surface="mw_model"`; (e) BLOCK → raise `splunkgate_core.errors.ModelOutputBlockedBySplunkGate(verdict)`; (f) MODIFY → return a new `ModelResponse(message=AIMessage(content=verdict.modifications["redacted_text"]), structured_output=response.structured_output)`; (g) ALLOW → return the original response unchanged
- `packages/splunkgate_mw/src/splunkgate_mw/_post_inference.py` — NEW — standalone helper `async def post_inference_scan(response: ModelResponse, profile: Profile) -> Verdict` (or equivalent signature taking the text directly). Internally: (1) extract text from `response.message.content`; (2) call `splunkgate_judges.ai_defense.inspect(text, rules_enabled=profile.rules_post_inference)` — default rules `["PII","PHI","PCI","Code Detection","Sensitive Data"]`; (3) on non-ALLOW verdict, build a `VerdictContext` (the Pydantic model defined in story-core-01) with `trace_id`, `agent_id`, `model_name`, `system_prompt_summary`, `recent_messages`, `surface="mw_model"` and call `FoundationSecExplainer.explain(ctx: VerdictContext) -> str` from `splunkgate_judges.foundation_sec` (the contract owned by EPIC-05 story-foundsec-02), subject to `config.foundation_sec_enabled`; (4) set `verdict.explanation = await explainer.explain(ctx)`; (5) return the verdict. Owns the AI Defense + Foundation-Sec call sequence so the middleware body stays a thin compose-via-helper-call
- `packages/splunkgate_core/src/splunkgate_core/errors.py` — UPDATE — add `ModelOutputBlockedBySplunkGate(SplunkGateError)` taking `verdict: Verdict`
- `packages/splunkgate_mw/tests/test_model_middleware_post.py` — NEW — ≥ 14 behavioral tests using `respx` (AI Defense + Foundation-Sec): benign AIMessage ALLOWs through (no Foundation-Sec call made); PII hit (e.g., `"contact me at john.doe@example.com"`) → MODIFY with redacted_text, Foundation-Sec called once, verdict.explanation populated; PHI hit (e.g., `"patient: HbA1c 7.2"`) → MODIFY with explanation; PCI hit (e.g., `"4111 1111 1111 1111"`) → BLOCK raises `ModelOutputBlockedBySplunkGate`; `config.foundation_sec_enabled=False` skips Foundation-Sec call but still produces verdict; OTel event has `splunkgate.surface="mw_model"` AND `splunkgate.explanation` attribute populated on non-ALLOW verdicts; latency_ms captured; combined `model_middleware.py` is ≤ 400 LOC (the file-level cap)

The coding agent must NOT modify files outside this map without re-checking `CLAUDE.md`.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given SafetyModelMiddleware wraps an LLM call whose AIMessage output contains no regulated data
When  `uv run pytest packages/splunkgate_mw/tests/test_model_middleware_post.py::test_allow_passthrough -v` runs
Then  the test passes; the original ModelResponse is returned unchanged; no Foundation-Sec HTTP call is made

Given respx mocks AI Defense to return MEDIUM severity with rule "PII"
And   respx mocks Foundation-Sec to return a WHY-string
When  the middleware processes an AIMessage containing "john.doe@example.com"
Then  exactly one AI Defense call is made with rules_enabled including "PII"
And   exactly one Foundation-Sec call is made
And   the returned ModelResponse has its AIMessage content replaced with verdict.modifications["redacted_text"]
And   the emitted OTel event has splunkgate.surface="mw_model" and a non-empty gen_ai.evaluation.explanation attribute

Given respx mocks AI Defense to return HIGH severity with rule "PCI"
When  the middleware processes an AIMessage containing a 16-digit credit-card-shaped string
Then  splunkgate_core.errors.ModelOutputBlockedBySplunkGate is raised
And   the verdict attached to the exception has severity="HIGH" and a populated explanation

Given config.foundation_sec_enabled is False
And   AI Defense returns a non-ALLOW verdict
When  the middleware runs
Then  no Foundation-Sec HTTP call is made
And   verdict.explanation is None
And   the verdict is still emitted via OTel

Given the test suite is run
When  `uv run pytest packages/splunkgate_mw/tests/test_model_middleware_post.py -v` runs
Then  ≥ 14 tests pass and 0 fail

Given the combined model_middleware.py (story-mw-03 first half + this story's second half)
When  `wc -l packages/splunkgate_mw/src/splunkgate_mw/model_middleware.py` runs
Then  the line count is ≤ 400

Given the §14 grep is run on changed source (excluding test files)
When  `grep -rE "(mock|fake|dummy|hardcoded|simulated)" packages/splunkgate_mw/src/splunkgate_mw/model_middleware.py packages/splunkgate_mw/src/splunkgate_mw/_post_inference.py` runs
Then  the output is empty
```

---

## Shell verification

The coding agent runs this to confirm the story is done before opening a PR:

```bash
# Verify the second half is wired (post-inference seam now executes)
uv run python -c "
import inspect
from splunkgate_mw.model_middleware import SafetyModelMiddleware
src = inspect.getsource(SafetyModelMiddleware.model_middleware)
# Both halves present: pre-inference (handler call) AND post-inference (Foundation-Sec wiring)
assert 'response = await handler(request)' in src
assert 'foundation_sec' in src.lower() or 'explanation' in src.lower()
print('OK')
"
# Must print 'OK'

# Tests pass — full model middleware suite (pre + post)
uv run pytest packages/splunkgate_mw/tests/test_model_middleware_pre.py packages/splunkgate_mw/tests/test_model_middleware_post.py -v 2>&1 | grep -cE "PASSED"
# Must output >= 28 (14 from story-mw-03 + 14 from this story)

# Combined file is ≤ 400 LOC
wc -l packages/splunkgate_mw/src/splunkgate_mw/model_middleware.py | awk '{ if ($1 > 400) exit 1 }'
# Must exit 0

# §14 clean
grep -rE "(mock|fake|dummy|hardcoded|simulated)" packages/splunkgate_mw/src/splunkgate_mw/model_middleware.py packages/splunkgate_mw/src/splunkgate_mw/_post_inference.py
# Must output nothing

# Lint + typecheck
uv run ruff check packages/splunkgate_mw/
uv run mypy packages/splunkgate_mw/src/splunkgate_mw/model_middleware.py packages/splunkgate_mw/src/splunkgate_mw/_post_inference.py
# Both must exit 0
```

---

## Notes for coding agent

- **STORY SPLIT — second half of `model_middleware.py`.** Story-mw-03 wrote the pre-inference half plus the composing factory and planted TWO `# --- POST-INFERENCE SCAN: see story-mw-04 ---` anchor comments — one in the MODIFY branch (after `handler(new_request)`) and one in the ALLOW branch (after `handler(request)`). This story INSERTS the post-inference helper call at BOTH anchors. Both anchors stay in the file as permanent inline citations (do NOT delete them). The combined file must remain ≤ 400 LOC. If the implementation approaches the cap, extract the rule-subset logic into `_post_inference.py` (already mapped) rather than splitting the middleware class.
- **Seam semantics (verify against story-mw-03 Notes section).** BLOCK from pre-scan → never call model, never call post-scan, raise `ModelInputBlockedBySplunkGate`. MODIFY from pre-scan → modify input, call model, post-scan runs on the rewritten path's response. ALLOW from pre-scan → call model on original input, post-scan runs on the original-path's response. Post-scan in turn produces its own verdict; BLOCK from post-scan → raise `ModelOutputBlockedBySplunkGate`; MODIFY from post-scan → return `ModelResponse` with redacted content; ALLOW from post-scan → return the original response unchanged.
- **Per `../../../context/02-agent-frameworks/06-splunklib-ai-deep-read.md` §"Request / response shapes", `model_middleware` returns `ModelResponse(message: AIMessage, structured_output: Any | None)`.** When MODIFY, construct a NEW `ModelResponse` with the redacted `AIMessage(content=...)` — preserve `structured_output` from the original response.
- **Per ADR-003 in `docs/architecture.md`, Foundation-Sec is the EXPLAINER, NOT the classifier.** Cisco AI Defense produces the binary verdict; Foundation-Sec generates the human-readable WHY-string. Do NOT use Foundation-Sec to make BLOCK/ALLOW decisions. If `config.foundation_sec_enabled` is False, skip the Foundation-Sec call entirely and emit the verdict with `explanation=None`.
- **Foundation-Sec contract (canonical, owned by EPIC-05 story-foundsec-02):** `FoundationSecExplainer.explain(ctx: VerdictContext) -> str`. The `VerdictContext` Pydantic model lives in `splunkgate_core/verdict_context.py` (story-core-01 ships it alongside `Verdict`). Do NOT call `splunkgate_judges.foundation_sec.explain(verdict, text)` — that signature was an earlier draft and is wrong. The post-inference helper constructs a `VerdictContext` from the live request + response state and passes it to the explainer.
- **Per `../../../context/07-cisco-stack/01-ai-defense-deep.md` §7, the rule-name spelling is verbatim:** `"PII"`, `"PHI"`, `"PCI"`, `"Code Detection"`. Include ampersands and exact casing.
- **Per the `Verdict` schema in `docs/architecture.md` §"API schemas", `Verdict.rules` is a list of `RuleHit(rule, confidence, source)` — NOT `triggered_rules`.** The audit (`../../../context/HALLUCINATION-AUDIT.md`) logs this historical hallucination. Use the field name `rules` only.
- **Per `../../../context/HALLUCINATION-AUDIT.md`, `AgentLimits` has a typo `max_structured_output_retires` (sic — "retires" not "retries"). Preserve it if touched.** This story does not touch `AgentLimits` directly, but if you read it for any reason, do not "fix" the typo — splunklib.ai 3.0.0 ships it that way and consumers depend on the name.
- The Foundation-Sec explainer (`splunkgate_judges.foundation_sec.FoundationSecExplainer`) was built in EPIC-05 story-foundsec-02. Contract: `async def explain(ctx: VerdictContext) -> str` — returns a short (≤ 200 chars) WHY-string suitable for the dashboard. Set `verdict.explanation = await explainer.explain(ctx)` only when `verdict.verdict != ALLOW`. The `VerdictContext` Pydantic model is imported from `splunkgate_core.verdict_context` (story-core-01).
- The OTel emission for the post-inference half includes the `gen_ai.evaluation.explanation` attribute when `verdict.explanation` is set. The emitter in `splunkgate_core.otel` (built in EPIC-03) handles None → attribute omitted. Do not pass empty strings.
- The active profile's `rules_post_inference` list is the subset of AI Defense rule names enabled. Default profile: `["PII", "PHI", "PCI", "Code Detection"]`. Story-mw-07 introduces per-profile rule subsets (`financial_services` emphasizes PCI; `healthcare` emphasizes PHI; `public_sector` emphasizes Code Detection + Sensitive Data).
- The MODIFY path's `redacted_text` field is produced by AI Defense's response (when the rule supports redaction) OR by a deterministic post-processor in `_post_inference.py` that masks matched entities. If the AI Defense response does not carry a redacted variant, the post-processor must produce one — never let an un-redacted text fall through on a MODIFY verdict.
