# Story — SafetyAgentMiddleware (trace_id seeding + session-wide correlation)

**ID:** story-mw-06-agent-middleware-trace-correlation
**Epic:** EPIC-06 — Surface 1 (splunkgate-mw middleware library for splunklib.ai)
**Depends on:** story-mw-01-package-skeleton-and-public-api, story-core-03-error-model-and-trace-propagation
**Estimate:** ~1.5h
**Status:** PENDING

---

## User story

**As a** SOC analyst inspecting a verdict timeline in Splunk after the fact
**I want to** every verdict emitted during a single agent.invoke() session to share the same `trace_id`, regardless of which middleware layer (tool / model / subagent) emitted it
**So that** I can pivot from one verdict to the full session's verdict trail in one click in the `verdict_inspector.xml` dashboard

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `packages/splunkgate_mw/src/splunkgate_mw/agent_middleware.py` — NEW — implements `SafetyAgentMiddleware(AgentMiddleware)` with concrete `async def agent_middleware(self, request: AgentRequest, handler: AgentMiddlewareHandler) -> AgentResponse[Any | None]`; logic: (a) read or generate session `trace_id` (UUIDv4) — prefer `request.thread_id` if the operator wants thread-stable correlation, else generate fresh; (b) bind `trace_id`, `splunkgate.surface="mw_agent"`, `splunkgate.profile=self.profile.name` to structlog via `structlog.contextvars.bind_contextvars`; (c) bind same `trace_id` to OTel via `splunkgate_core.trace.bind_trace_id(trace_id)`; (d) `try: return await handler(request)` — the try/finally is critical; (e) `finally:` emit a session-summary verdict (`surface="mw_agent"`, `verdict=ALLOW` if no exception, `verdict=BLOCK` if an SplunkGateError propagated) and unbind contextvars; (f) re-raise on exception
- `packages/splunkgate_mw/src/splunkgate_mw/__init__.py` — UPDATE — `SafetyAgentMiddleware` re-export resolves to the new implementation
- `packages/splunkgate_mw/tests/test_agent_middleware.py` — NEW — ≥ 12 behavioral tests: trace_id is generated on entry if not already bound; same trace_id is observable in structlog contextvars during `handler(request)` execution; same trace_id appears on a stub Verdict emitted inside `handler(request)` by a child tool/model middleware; on exception, the contextvars are unbound (no leak across sessions); a session-summary verdict with `surface="mw_agent"` and `verdict="ALLOW"` is emitted exactly once on the happy path; a session-summary verdict with `verdict="BLOCK"` is emitted when a child middleware raises `splunkgate_core.errors.SplunkGateError`; non-SplunkGateError exceptions propagate without emitting a BLOCK verdict (we only own SplunkGateError outcomes); thread_id preference works (when `request.thread_id` is set, the session trace_id is derived deterministically from it for the same thread)
- `packages/splunkgate_core/src/splunkgate_core/trace.py` — UPDATE — if `bind_trace_id` / `current_trace_id` helpers do not already exist from story-core-03, add them: `def bind_trace_id(trace_id: UUID) -> None`, `def current_trace_id() -> UUID | None`, `def unbind_trace_id() -> None`; uses `contextvars.ContextVar` for asyncio-safe propagation

The coding agent must NOT modify files outside this map without re-checking `CLAUDE.md`.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given SafetyAgentMiddleware wraps an Agent.invoke() with no prior trace_id bound
When  `uv run pytest packages/splunkgate_mw/tests/test_agent_middleware.py::test_seeds_trace_id -v` runs
Then  the test passes; inside handler(request), splunkgate_core.trace.current_trace_id() returns a non-None UUID

Given SafetyAgentMiddleware is wrapping the agent
And   a child middleware emits a Verdict inside the handler call
When  the verdict is inspected
Then  verdict.trace_id equals the trace_id bound by SafetyAgentMiddleware

Given the happy path completes
When  the session ends
Then  exactly one OTel event with splunkgate.surface="mw_agent" and gen_ai.evaluation.score.label="allow" is emitted
And   splunkgate_core.trace.current_trace_id() returns None (contextvars unbound)

Given a child middleware raises splunkgate_core.errors.SplunkGateError mid-session
When  SafetyAgentMiddleware's finally clause runs
Then  exactly one OTel event with splunkgate.surface="mw_agent" and gen_ai.evaluation.score.label="block" is emitted
And   the original SplunkGateError propagates to the caller

Given the agent is invoked with request.thread_id="thread-xyz"
And   it is invoked twice in a row with the same thread_id
When  the trace_ids of the two sessions are compared
Then  they are equal (deterministic from thread_id) — assertion in test_thread_id_stable_trace_id

Given the test suite is run
When  `uv run pytest packages/splunkgate_mw/tests/test_agent_middleware.py -v` runs
Then  ≥ 12 tests pass and 0 fail

Given the agent_middleware.py file
When  `wc -l packages/splunkgate_mw/src/splunkgate_mw/agent_middleware.py` runs
Then  the line count is ≤ 400

Given the §14 grep is run on changed source (excluding test files)
When  `grep -rE "(mock|fake|dummy|hardcoded|simulated)" packages/splunkgate_mw/src/splunkgate_mw/agent_middleware.py` runs
Then  the output is empty
```

---

## Shell verification

The coding agent runs this to confirm the story is done before opening a PR:

```bash
# trace_id propagation works end-to-end
uv run python <<'PY'
import asyncio
from splunkgate_core.trace import current_trace_id
from splunkgate_mw.agent_middleware import SafetyAgentMiddleware

async def fake_handler(request):
    assert current_trace_id() is not None, "trace_id not bound inside handler"
    class R: pass
    return R()

mw = SafetyAgentMiddleware(profile="default")

class FakeRequest:
    messages = []
    thread_id = "t1"

assert current_trace_id() is None, "trace_id leaked before invoke"
asyncio.run(mw.agent_middleware(FakeRequest(), fake_handler))
assert current_trace_id() is None, "trace_id leaked after invoke"
print('OK')
PY
# Must print 'OK'

# Tests pass
uv run pytest packages/splunkgate_mw/tests/test_agent_middleware.py -v 2>&1 | grep -cE "PASSED"
# Must output >= 12

# 400-LOC cap
wc -l packages/splunkgate_mw/src/splunkgate_mw/agent_middleware.py | awk '{ if ($1 > 400) exit 1 }'
# Must exit 0

# §14 clean
grep -rE "(mock|fake|dummy|hardcoded|simulated)" packages/splunkgate_mw/src/splunkgate_mw/agent_middleware.py
# Must output nothing

# Lint + typecheck
uv run ruff check packages/splunkgate_mw/
uv run mypy packages/splunkgate_mw/src/splunkgate_mw/agent_middleware.py
# Both must exit 0
```

---

## Notes for coding agent

- **Per `../../../context/02-agent-frameworks/06-splunklib-ai-deep-read.md` §"Middleware system" + §"Request / response shapes", `agent_middleware` receives `AgentRequest(messages: Sequence[BaseMessage], thread_id: str)` and returns `AgentResponse[Any | None]`.** The wrap is at the OUTERMOST layer of the agent invocation — it sees the messages going in and the response coming out, wrapping every model_middleware, tool_middleware, and subagent_middleware call that occurs in between.
- **Per `../../../context/02-agent-frameworks/06-splunklib-ai-deep-read.md`, splunklib.ai's `Agent` auto-generates a 32-hex-char trace_id at construction (`base_agent.py:79`).** SplunkGate's session trace_id is INDEPENDENT of this — we use a UUIDv4 because the rest of the OTel pipeline expects UUIDs (the `Verdict.trace_id` field is `UUID`). If the operator wants stable correlation between SplunkGate verdicts and splunklib.ai's own trace_id, that's a future enhancement — log both into the structlog binding for now and the SOC analyst can pivot on either.
- **Per `../../../context/02-agent-frameworks/06-splunklib-ai-deep-read.md`, the README warns at `agent.py:139-140` to never invoke an Agent concurrently with the same `thread_id`.** The deterministic `thread_id → trace_id` derivation (UUIDv5 from a fixed namespace, with `thread_id` as the name) makes the trace_id stable across re-invocations of the same thread, which is what dashboards expect.
- The `structlog.contextvars` API is used so async tasks under the same `asyncio.Task` see the bound trace_id without needing to thread it through every function argument. Pair with `contextvars.ContextVar` in `splunkgate_core.trace` for non-structlog consumers (OTel emitter reads from `current_trace_id()`).
- The session-summary verdict in the `finally` clause is the operator's "session boundary" — useful for SOC dashboards that want a "verdict per session" count. It is NOT a duplicate of the per-call verdicts; the score is the aggregate session outcome (ALLOW if no SplunkGateError, BLOCK if one propagated).
- Only `SplunkGateError` subclasses trigger the BLOCK session-summary verdict. A `TimeoutExceededException` (from splunklib.ai's `AgentLimits`) is NOT our concern — let it propagate. `KeyboardInterrupt` / `SystemExit` propagate untouched.
- **Per `../../../context/HALLUCINATION-AUDIT.md`, splunklib.ai's `AgentLimits` has the typo `max_structured_output_retires` (sic).** This story does not touch `AgentLimits` directly, but if you import its exceptions to filter what to re-raise vs. summarize, do not "fix" the field name elsewhere — preserve it exactly.
- Re-binding behavior: if the parent process has already bound a `trace_id` (e.g., a unit test fixture or an outer Splunk modular-input contextvar), DO NOT overwrite it — read it, reuse it, and skip re-binding. The unbinding in the `finally` clause then becomes a no-op for the borrowed trace_id (track with a local boolean `i_bound_it = True/False`).
