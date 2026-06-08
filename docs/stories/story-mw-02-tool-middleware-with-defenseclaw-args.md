# Story — SafetyToolMiddleware (tool-call interception with DefenseClaw + AI Defense escalation)

**ID:** story-mw-02-tool-middleware-with-defenseclaw-args
**Epic:** EPIC-06 — Surface 1 (splunkgate-mw middleware library for splunklib.ai)
**Depends on:** story-mw-01-package-skeleton-and-public-api, story-judges-05-ai-defense-end-to-end-integration-test
**Estimate:** ~2h
**Status:** PENDING

---

## User story

**As a** Splunk agent developer who wants high-severity tool calls intercepted before they execute
**I want to** `Agent(tool_middleware=[SafetyToolMiddleware(profile=...)])` and get a tool-call → DefenseClaw-rules → Cisco-AI-Defense escalation chain wired in automatically
**So that** dangerous tool calls are BLOCKed (raising) or MODIFIED (sanitized args returned) with a Verdict emitted to OTel — without me re-implementing the rule engine

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `packages/splunkgate_mw/src/splunkgate_mw/tool_middleware.py` — NEW — implements `SafetyToolMiddleware(AgentMiddleware)` with concrete `async def tool_middleware(self, request: ToolRequest, handler: ToolMiddlewareHandler) -> ToolResponse`; inspects `request.call.name` + `request.call.args`; runs DefenseClaw rule-pack (via `splunkgate_judges.defenseclaw_backend.evaluate_tool_call(name, args)`); if rule-pack hit is HIGH or above OR `config.escalate_on_first_pass_hit` is set, escalates to `splunkgate_judges.ai_defense.inspect(text=serialize(call))`; assembles a `Verdict` (`surface="mw_tool"`, `severity`, `rules`, `latency_ms`) and emits via `splunkgate_core.otel.emit_evaluation_result(verdict)`; behavior by verdict label: `BLOCK` → raises `splunkgate_core.errors.ToolBlockedBySplunkGate(verdict)` (a subclass of `SplunkGateError`); `MODIFY` → returns a `ToolMiddlewareHandler` call with sanitized args (`verdict.modifications["sanitized_args"]`); `ALLOW` → passes through to `await handler(request)`
- `packages/splunkgate_mw/src/splunkgate_mw/_serialization.py` — NEW — small helper `serialize_tool_call(call: ToolCall) -> str` that returns `f"{call.name}({json.dumps(call.args, sort_keys=True)})"`, used by both tool and model middleware
- `packages/splunkgate_mw/src/splunkgate_mw/__init__.py` — UPDATE — make sure `SafetyToolMiddleware` re-export still resolves to the new implementation in `tool_middleware.py` (replace the stub from story-mw-01)
- `packages/splunkgate_core/src/splunkgate_core/errors.py` — UPDATE — add `ToolBlockedBySplunkGate(SplunkGateError)` taking `verdict: Verdict` constructor arg
- `packages/splunkgate_mw/tests/test_tool_middleware.py` — NEW — ≥ 14 behavioral tests using `respx` to mock the AI Defense HTTP endpoint and a fake `ToolMiddlewareHandler`: ALLOW path passes through unchanged; BLOCK path raises `ToolBlockedBySplunkGate`; MODIFY path returns a `ToolResponse` whose underlying call used the sanitized args; OTel emission asserted via in-memory exporter; trace_id from `agent_middleware` (mocked) propagates onto the verdict; DefenseClaw-only hit (no AI Defense escalation) emits a verdict with `source="defenseclaw_regex"`; AI Defense-escalated hit emits a verdict with `source="ai_defense"`; profile="default" routes correctly; latency_ms is populated > 0
- `packages/splunkgate_mw/tests/conftest.py` — NEW or UPDATE — fixtures for in-memory OTel exporter, fake `ToolRequest`/`ToolMiddlewareHandler`, respx-mocked AI Defense client

The coding agent must NOT modify files outside this map without re-checking `CLAUDE.md`.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given SafetyToolMiddleware is imported and a benign ToolCall ("splunk_search", {"query": "index=main"}) is wrapped
When  `uv run pytest packages/splunkgate_mw/tests/test_tool_middleware.py::test_allow_passthrough -v` runs
Then  the test passes; the inner handler is invoked exactly once with the unchanged request

Given SafetyToolMiddleware wraps a high-severity ToolCall whose DefenseClaw rules + AI Defense response say BLOCK
When  `uv run pytest packages/splunkgate_mw/tests/test_tool_middleware.py::test_block_raises -v` runs
Then  the test passes; splunkgate_core.errors.ToolBlockedBySplunkGate is raised; the inner handler is NOT called

Given SafetyToolMiddleware wraps a ToolCall whose verdict is MODIFY with sanitized args
When  `uv run pytest packages/splunkgate_mw/tests/test_tool_middleware.py::test_modify_returns_sanitized -v` runs
Then  the test passes; the inner handler is invoked with verdict.modifications["sanitized_args"], not the original args

Given the in-memory OTel exporter is attached
When  any of the BLOCK/MODIFY/ALLOW tests runs
Then  exactly one `gen_ai.evaluation.result` event is emitted per invocation with `gen_ai.evaluation.name="splunkgate.safety_verdict"`, `splunkgate.surface="mw_tool"`, and a populated `splunkgate.trace_id`

Given respx mocks the AI Defense endpoint to return an empty rules list
When  the tool middleware runs against a payload that does NOT trigger any DefenseClaw rule
Then  no AI Defense HTTP request is made (assert respx.routes were not called)

Given respx mocks the AI Defense endpoint to return a HIGH severity Prompt Injection hit
When  the tool middleware runs against a payload that triggers a DefenseClaw rule
Then  exactly one AI Defense HTTP request is made and the emitted verdict has `severity == "HIGH"` and `rules[0].source == "ai_defense"`

Given the test suite is run
When  `uv run pytest packages/splunkgate_mw/tests/test_tool_middleware.py -v` runs
Then  ≥ 14 tests pass and 0 fail

Given each source file in packages/splunkgate_mw/src/splunkgate_mw/
When  `find packages/splunkgate_mw/src/splunkgate_mw -name '*.py' -exec wc -l {} +` runs
Then  every file reports ≤ 400 lines

Given the §14 grep is run on changed source (excluding test files)
When  `grep -rE "(mock|fake|dummy|hardcoded|simulated)" packages/splunkgate_mw/src/splunkgate_mw/tool_middleware.py packages/splunkgate_mw/src/splunkgate_mw/_serialization.py` runs
Then  the output is empty
```

---

## Shell verification

The coding agent runs this to confirm the story is done before opening a PR:

```bash
# Public class is the real implementation (not the story-mw-01 stub)
uv run python -c "
import inspect
from splunkgate_mw import SafetyToolMiddleware
src = inspect.getsource(SafetyToolMiddleware.tool_middleware)
assert 'handler(request)' in src
assert 'emit' in src or 'Verdict' in src
print('OK')
"
# Must print 'OK'

# Tests pass
uv run pytest packages/splunkgate_mw/tests/test_tool_middleware.py -v 2>&1 | grep -cE "PASSED"
# Must output >= 14

# Tool middleware module is ≤ 400 LOC
wc -l packages/splunkgate_mw/src/splunkgate_mw/tool_middleware.py | awk '{ if ($1 > 400) exit 1 }'
# Must exit 0

# §14 clean
grep -rE "(mock|fake|dummy|hardcoded|simulated)" packages/splunkgate_mw/src/splunkgate_mw/tool_middleware.py packages/splunkgate_mw/src/splunkgate_mw/_serialization.py
# Must output nothing

# Lint + typecheck
uv run ruff check packages/splunkgate_mw/
uv run mypy packages/splunkgate_mw/src/splunkgate_mw/tool_middleware.py
# Both must exit 0
```

---

## Notes for coding agent

- **Per `../../../context/02-agent-frameworks/06-splunklib-ai-deep-read.md` §"Request / response shapes", `tool_middleware` receives `ToolRequest(call: ToolCall, state: AgentState)` and returns `ToolResponse(result: ToolResult | ToolFailureResult)`.** The wrap pattern is `async def tool_middleware(self, request, handler) -> ToolResponse: return await handler(request)`. To BLOCK, raise an exception. To MODIFY, construct a new `ToolRequest` with sanitized args and call `await handler(new_request)`.
- **Per `../../../context/02-agent-frameworks/06-splunklib-ai-deep-read.md` §"Convenience hooks", a hook can stop the agent loop by raising any exception inside the user function.** Raising `ToolBlockedBySplunkGate(verdict)` is the BLOCK semantic. The agent loop unwinds with our typed exception — downstream callers can inspect `e.verdict`.
- **Per `../../../context/02-agent-frameworks/06-splunklib-ai-deep-read.md`, splunklib.ai ships exactly 9 prompt-injection regex patterns at `splunklib/ai/security.py` (verified in `../../../context/sources/code-snippets/splunklib-ai-security-top60.py`).** This middleware does NOT call `detect_injection()` on tool args directly — tool args are evaluated by DefenseClaw rules + AI Defense; `detect_injection()` runs in the **model** middleware (story-mw-03). Keep responsibility split: tool middleware = tool-call shape; model middleware = message text.
- DefenseClaw is a Go binary — we call into its rule engine via the wrapper `splunkgate_judges.defenseclaw_backend.evaluate_tool_call(name: str, args: dict) -> RuleHit | None` shipped by EPIC-08. For this story, treat that import as the contract; respx fixture can stand in if EPIC-08 hasn't landed yet (mark with TODO + issue link).
- The AI Defense client (`splunkgate_judges.ai_defense.inspect`) defaults to mock=True per ADR-006; tests run without credentials. The respx fixtures from `story-judges-04-ai-defense-mock-respx-fixtures.md` are the canonical mock shape.
- The Verdict OTel emission shape comes from `docs/architecture.md` §"OTel emission shape". `surface="mw_tool"` is the literal value to set.
- For the BLOCK path: do NOT swallow downstream Splunk-level exceptions. Only catch + repackage rule-engine errors. Anything from `handler(request)` propagates.
- For the MODIFY path: `verdict.modifications` is a `dict | None`. When MODIFY, the contract is `verdict.modifications["sanitized_args"]: dict` — the agent re-runs the tool with these args. If `sanitized_args` is missing, raise `SplunkGateError` rather than silently passing through original args.
- Measure `latency_ms` with `time.perf_counter()` deltas around the rule-pack + AI Defense calls; populate `verdict.latency_ms` with the value in milliseconds (float).
- structlog: bind `trace_id` from `request.state` (LangChain v1 surfaces it via `state.messages[-1].extras` or via the `splunkgate_mw.agent_middleware` from story-mw-06) and log the verdict label at INFO.
