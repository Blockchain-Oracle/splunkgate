# Story — SafetySubagentMiddleware (subagent-invocation interception with trace_id propagation)

**ID:** story-mw-05-subagent-middleware
**Epic:** EPIC-06 — Surface 1 (aegis-mw middleware library for splunklib.ai)
**Depends on:** story-mw-01-package-skeleton-and-public-api
**Estimate:** ~1.5h
**Status:** PENDING

---

## User story

**As a** Splunk agent developer building multi-agent workflows where a parent agent delegates to subagents
**I want to** subagent invocations to be intercepted with their own (possibly stricter) safety profile and the parent's `trace_id` propagated onto every emitted Verdict
**So that** subagent boundaries are auditable end-to-end and stricter sub-profiles (e.g., a "draft-only" subagent restricted to read-only tools) can be enforced without the parent agent inheriting the strictness

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `packages/aegis_mw/src/aegis_mw/subagent_middleware.py` — NEW — implements `SafetySubagentMiddleware(AgentMiddleware)` with concrete `async def subagent_middleware(self, request: SubagentRequest, handler: SubagentMiddlewareHandler) -> SubagentResponse`; constructor accepts `profile: str | Profile` AND optional `per_subagent_profile: dict[str, str | Profile] = None` (key = subagent name, value = profile override); inspects `request.call.name` (subagent name) + `request.call` input; resolves effective profile via `per_subagent_profile.get(request.call.name, self.profile)`; runs a lightweight DefenseClaw-rules check on the subagent input (same path as tool middleware but scoped to subagent inputs); BLOCK → raises `aegis_core.errors.SubagentBlockedByAegis(verdict)`; MODIFY → calls `await handler(request_with_modified_input)`; ALLOW → `await handler(request)`. Every emitted verdict has `surface="mw_subagent"` and `trace_id` taken from `request.state` (or the parent's structlog-bound trace_id) — not freshly generated.
- `packages/aegis_mw/src/aegis_mw/__init__.py` — UPDATE — `SafetySubagentMiddleware` re-export resolves to the new implementation
- `packages/aegis_core/src/aegis_core/errors.py` — UPDATE — add `SubagentBlockedByAegis(AegisError)` taking `verdict: Verdict`
- `packages/aegis_mw/tests/test_subagent_middleware.py` — NEW — ≥ 12 behavioral tests: benign subagent call ALLOWs through; BLOCK raises `SubagentBlockedByAegis`; MODIFY rewrites subagent input; per-subagent profile override applies (a "draft" subagent uses `financial_services` while parent uses `default`); trace_id from a parent-supplied `agent_state` is preserved on the emitted verdict (NOT regenerated); two parallel subagent calls in the same parent trace share the same `trace_id` on their verdicts; OTel events emit with `aegis.surface="mw_subagent"`; verdict latency_ms > 0

The coding agent must NOT modify files outside this map without re-checking `CLAUDE.md`.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given SafetySubagentMiddleware wraps a benign subagent call
When  `uv run pytest packages/aegis_mw/tests/test_subagent_middleware.py::test_allow_passthrough -v` runs
Then  the test passes; the inner handler is invoked exactly once

Given SafetySubagentMiddleware is constructed with per_subagent_profile={"summarizer": "financial_services"}
And   the parent profile is "default"
When  the middleware intercepts a SubagentRequest where call.name == "summarizer"
Then  the verdict emitted reflects the financial_services profile rule subset (assert via verdict.rules sources)
And   when call.name == "other", the verdict reflects the default profile

Given the parent agent has set trace_id="abc123..." in the agent_state (via the structlog bind from story-mw-06)
When  SafetySubagentMiddleware emits a verdict
Then  the verdict's trace_id field equals "abc123..." (NOT a fresh UUID)

Given two concurrent subagent invocations under the same parent trace
When  both complete and both emit verdicts
Then  both verdicts share the same trace_id (assertion in test_trace_propagation_concurrent)

Given the subagent BLOCK verdict path
When  the wrap is invoked
Then  aegis_core.errors.SubagentBlockedByAegis is raised; the inner handler is NOT called

Given the test suite is run
When  `uv run pytest packages/aegis_mw/tests/test_subagent_middleware.py -v` runs
Then  ≥ 12 tests pass and 0 fail

Given the subagent_middleware.py file
When  `wc -l packages/aegis_mw/src/aegis_mw/subagent_middleware.py` runs
Then  the line count is ≤ 400

Given the §14 grep is run on changed source (excluding test files)
When  `grep -rE "(mock|fake|dummy|hardcoded|simulated)" packages/aegis_mw/src/aegis_mw/subagent_middleware.py` runs
Then  the output is empty
```

---

## Shell verification

The coding agent runs this to confirm the story is done before opening a PR:

```bash
# Public class is the real implementation (not the story-mw-01 stub)
uv run python -c "
import inspect
from aegis_mw import SafetySubagentMiddleware
src = inspect.getsource(SafetySubagentMiddleware.subagent_middleware)
assert 'handler(request' in src
assert 'mw_subagent' in src or 'surface' in src
print('OK')
"
# Must print 'OK'

# Tests pass
uv run pytest packages/aegis_mw/tests/test_subagent_middleware.py -v 2>&1 | grep -cE "PASSED"
# Must output >= 12

# 400-LOC cap
wc -l packages/aegis_mw/src/aegis_mw/subagent_middleware.py | awk '{ if ($1 > 400) exit 1 }'
# Must exit 0

# §14 clean
grep -rE "(mock|fake|dummy|hardcoded|simulated)" packages/aegis_mw/src/aegis_mw/subagent_middleware.py
# Must output nothing

# Lint + typecheck
uv run ruff check packages/aegis_mw/
uv run mypy packages/aegis_mw/src/aegis_mw/subagent_middleware.py
# Both must exit 0
```

---

## Notes for coding agent

- **Per `../../../context/02-agent-frameworks/06-splunklib-ai-deep-read.md` §"Middleware system" + §"Request / response shapes", `subagent_middleware` receives `SubagentRequest(call: SubagentCall, state: AgentState)` and returns `SubagentResponse(result: SubagentStructuredResult | SubagentTextResult | SubagentFailureResult)`.** The result-type union is wider than tool middleware — preserve the result type when returning ALLOW; when MODIFY rewrites the result on the way back, default to `SubagentTextResult` unless the original was structured.
- **Per `../../../context/02-agent-frameworks/06-splunklib-ai-deep-read.md`, splunklib.ai's `Agent` constructor accepts `agents: Sequence[BaseAgent[BaseModel | None]] | None = None` — subagents.** Each subagent has its own `name` and `description` (used internally by the parent's tool-call wiring) — the subagent's `name` is what `SubagentCall.name` will hold and is the key for `per_subagent_profile`.
- **Per `../../../context/02-agent-frameworks/06-splunklib-ai-deep-read.md` §"`trace_id`", each Agent auto-generates a 32-hex-char `trace_id` at construction (`base_agent.py:79`).** Subagents have their OWN trace_id. The Aegis convention: every Verdict emitted in a single parent invocation (parent + all subagent calls) shares the parent's trace_id, NOT the subagent's auto-generated one. Pull trace_id from `request.state` (the `AgentState` is propagated by the parent's `agent_middleware` per story-mw-06) — fall back to structlog's contextvar binding if `request.state` does not carry it.
- The `per_subagent_profile` kwarg is the discriminating feature versus `model_middleware` / `tool_middleware` — it lets users say "the draft-writer subagent runs with financial_services strictness while the parent stays on default." Resolution order: `per_subagent_profile[call.name]` → `self.profile` → "default".
- The DefenseClaw rules pack for subagents reuses the same `aegis_judges.defenseclaw_backend.evaluate_subagent_call(name, input)` contract (if EPIC-08 has shipped it). If not, mirror the same shape as tool middleware uses and mark with TODO + issue link to EPIC-08.
- The `state.messages[-1]` may be either a `HumanMessage` (subagent input is a message) or a `SubagentMessage` echoing the call — handle both.
- Reuse `_serialization.py` from story-mw-02 if the same `name(args)` serialization shape works for subagent calls; otherwise add `serialize_subagent_call` to that file.
- DO NOT modify the `trace_id` generation in `base_agent.py:79` — that is splunklib.ai upstream and we override at the verdict level only.
