# Story — Error model + UUID trace propagation

**ID:** story-core-03-error-model-and-trace-propagation
**Epic:** EPIC-03 — Core domain types
**Depends on:** story-core-01-verdict-pydantic-types
**Estimate:** ~2h
**Status:** PENDING

---

## User story

**As a** coding agent writing any SplunkGate surface (S1 middleware, S2 MCP server, S3 DefenseClaw shim, S4 Splunk app)
**I want to** raise typed errors from a single `splunkgate_core.errors` hierarchy (`SplunkGateError` → `JudgmentError | ConfigError | NetworkError`) and propagate a single UUID `trace_id` across sync and async call paths via a context-var-based helper in `splunkgate_core.trace`
**So that** the architecture's hard rule "all errors raised are subclasses of `splunkgate_core.errors.SplunkGateError`" is enforceable, and every Verdict + log line + OTel event in one logical request shares the same `trace_id` automatically (no manual plumbing)

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `packages/splunkgate_core/src/splunkgate_core/errors.py` — NEW — `SplunkGateError(Exception)` base + `JudgmentError`, `ConfigError`, `NetworkError` subclasses. Each takes a `trace_id: UUID | None = None`. ≤ 150 LOC. mypy --strict clean.
- `packages/splunkgate_core/src/splunkgate_core/trace.py` — NEW — `trace_id_var: ContextVar[UUID | None]`, `new_trace_id()`, `current_trace_id()`, `set_trace_id(...)`, and an async-safe `trace_context()` context manager. ≤ 150 LOC. mypy --strict clean.
- `packages/splunkgate_core/src/splunkgate_core/__init__.py` — UPDATE — re-export `SplunkGateError`, `JudgmentError`, `ConfigError`, `NetworkError`, `new_trace_id`, `current_trace_id`, `trace_context`; update `__all__`
- `packages/splunkgate_core/tests/test_errors.py` — NEW — pytest cases: hierarchy (every subclass is-a SplunkGateError), trace_id round-trip, error message format
- `packages/splunkgate_core/tests/test_trace.py` — NEW — pytest cases including pytest-asyncio: ContextVar isolation between async tasks, propagation across `await`, `trace_context()` enter/exit, nested contexts, default-None state

The coding agent must NOT modify files outside this map without re-checking CLAUDE.md.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given the errors module exists
When  `uv run python -c "from splunkgate_core.errors import SplunkGateError, JudgmentError, ConfigError, NetworkError; print('ok')"` runs
Then  exit code is 0
And   stdout contains "ok"

Given each subclass extends SplunkGateError
When  `uv run python -c "from splunkgate_core.errors import SplunkGateError, JudgmentError, ConfigError, NetworkError; assert issubclass(JudgmentError, SplunkGateError); assert issubclass(ConfigError, SplunkGateError); assert issubclass(NetworkError, SplunkGateError); print('hierarchy ok')"` runs
Then  exit code is 0
And   stdout contains "hierarchy ok"

Given an SplunkGateError instance is constructed with a trace_id
When  the instance is inspected
Then  `err.trace_id` matches the passed-in UUID

Given the trace module exists
When  `uv run python -c "from splunkgate_core.trace import new_trace_id, current_trace_id, trace_context; print('ok')"` runs
Then  exit code is 0
And   stdout contains "ok"

Given current_trace_id() is called with no enclosing trace_context
When  the call returns
Then  return value is None

Given `trace_context()` is entered with a fresh UUID
When  `current_trace_id()` is called inside the block
Then  return value equals the entered UUID

Given `trace_context()` is exited
When  `current_trace_id()` is called after
Then  return value is None (no leak)

Given two concurrent asyncio tasks each enter their own trace_context
When  each task calls current_trace_id()
Then  each task sees its own UUID (no cross-task contamination)

Given the test suite runs
When  `uv run pytest packages/splunkgate_core/tests/test_errors.py packages/splunkgate_core/tests/test_trace.py -q` runs
Then  exit code is 0
And   stdout contains a line matching at least "12 passed"

Given mypy strict mode is active
When  `uv run mypy packages/splunkgate_core/src` runs
Then  exit code is 0
And   stdout contains "Success: no issues found"

Given ruff is run against errors.py and trace.py
When  `uv run ruff check packages/splunkgate_core/src/splunkgate_core/errors.py packages/splunkgate_core/src/splunkgate_core/trace.py` runs
Then  exit code is 0

Given the 400-LOC rule
When  `uv run python .github/scripts/check_loc.py packages/splunkgate_core/src/splunkgate_core/errors.py packages/splunkgate_core/src/splunkgate_core/trace.py` runs
Then  exit code is 0
```

Every criterion must be checkable by running a command. Prose-only criteria = blocked.

---

## Shell verification

The coding agent runs this to confirm the story is done before opening a PR:

```bash
# 1. Imports resolve
uv run python -c "from splunkgate_core.errors import SplunkGateError, JudgmentError, ConfigError, NetworkError; from splunkgate_core.trace import new_trace_id, current_trace_id, trace_context; print('imports ok')"

# 2. Error hierarchy correct
uv run python -c "
from splunkgate_core.errors import SplunkGateError, JudgmentError, ConfigError, NetworkError
for sub in (JudgmentError, ConfigError, NetworkError):
    assert issubclass(sub, SplunkGateError), f'{sub.__name__} is not SplunkGateError'
print('hierarchy ok')
"

# 3. trace_id round-trip via error constructor
uv run python -c "
from uuid import uuid4
from splunkgate_core.errors import JudgmentError
tid = uuid4()
err = JudgmentError('judgment failed', trace_id=tid)
assert err.trace_id == tid, 'trace_id did not round-trip'
print('error trace_id ok')
"

# 4. trace_context propagates and isolates
uv run python -c "
import asyncio
from splunkgate_core.trace import new_trace_id, current_trace_id, trace_context
async def task(tid):
    with trace_context(tid):
        await asyncio.sleep(0)
        assert current_trace_id() == tid
async def main():
    a, b = new_trace_id(), new_trace_id()
    await asyncio.gather(task(a), task(b))
    assert current_trace_id() is None
asyncio.run(main())
print('async isolation ok')
"

# 5. Test suite passes
uv run pytest packages/splunkgate_core/tests/test_errors.py packages/splunkgate_core/tests/test_trace.py -q

# 6. mypy --strict clean
uv run mypy packages/splunkgate_core/src

# 7. ruff clean
uv run ruff check packages/splunkgate_core/src/splunkgate_core/errors.py packages/splunkgate_core/src/splunkgate_core/trace.py

# 8. LOC under 400 for both files
uv run python .github/scripts/check_loc.py packages/splunkgate_core/src/splunkgate_core/errors.py packages/splunkgate_core/src/splunkgate_core/trace.py

# 9. §14 clean
grep -E "(mock|fake|dummy|hardcoded|simulated)" packages/splunkgate_core/src/splunkgate_core/errors.py packages/splunkgate_core/src/splunkgate_core/trace.py
# Must output nothing
```

---

## Notes for coding agent

- Per `docs/architecture.md` § "Coding standards" soft rules: "All errors raised are subclasses of `splunkgate_core.errors.SplunkGateError`." This story establishes the hierarchy; downstream stories enforce it by always raising one of these four classes.
- Per `docs/architecture.md` § "Banned patterns": `try/except: pass` is banned — always re-raise as an `SplunkGateError` subclass. The error classes must accept a chained `cause` (use Python's built-in `__cause__` via `raise NewErr(...) from old_err`); do not add a custom `cause` constructor arg.
- Per `docs/architecture.md` § "API schemas" → "Verdict (the type every surface emits)": `Verdict.trace_id` is a `UUID`. The trace module's `new_trace_id()` returns `uuid.uuid4()`. The same UUID must thread through Verdict, OTel event (`splunkgate.trace_id` attr from story-core-02), errors (`SplunkGateError.trace_id`), and logs (story-core-04 will key on it).
- Per `docs/architecture.md` § "Coding standards" soft rules: "Async by default for I/O". The trace propagation MUST use `contextvars.ContextVar`, NOT threading.local, because asyncio tasks each get their own copy of the contextvars context on creation — which is exactly what we want for per-request trace isolation. Reference: Python stdlib `contextvars` docs; query via `mcp__context7__resolve-library-id` if unfamiliar.
- `trace_context(trace_id)` context manager pattern (synchronous + async-safe):
  ```python
  @contextmanager
  def trace_context(trace_id: UUID) -> Iterator[None]:
      token = trace_id_var.set(trace_id)
      try:
          yield
      finally:
          trace_id_var.reset(token)
  ```
  The same context manager works for sync `with` and inside `async def` functions (because asyncio preserves ContextVar values across `await`).
- Subclass error class skeletons (minimal — let docstring + class name carry meaning):
  ```python
  class SplunkGateError(Exception):
      """Base for all SplunkGate errors."""
      def __init__(self, message: str, *, trace_id: UUID | None = None) -> None:
          super().__init__(message)
          self.trace_id = trace_id

  class JudgmentError(SplunkGateError): """Raised when a judgment-layer client fails."""
  class ConfigError(SplunkGateError): """Raised on invalid SplunkGate config."""
  class NetworkError(SplunkGateError): """Raised on HTTP/network failure (wraps httpx exceptions)."""
  ```
- Per `docs/architecture.md` § "Banned patterns", no `Any` in `splunkgate_core`. Type-annotate everything. mypy --strict will catch slip-ups.
- For pytest-asyncio cases, add `pytest_plugins = ("pytest_asyncio",)` to `conftest.py` (or use the marker per test). Confirm via `uv run pytest --markers | grep asyncio` that the plugin is registered. story-skel-01 already added pytest-asyncio to dev deps per the architecture stack list; if missing, add to root `[dependency-groups].dev`.
- Minimum 12 behavioral cases (errors + trace combined):
  - errors:
    1. `SplunkGateError` subclass `JudgmentError`
    2. `SplunkGateError` subclass `ConfigError`
    3. `SplunkGateError` subclass `NetworkError`
    4. `SplunkGateError` accepts trace_id kwarg
    5. `SplunkGateError` raised without trace_id → trace_id is None
    6. `raise JudgmentError(...) from e` preserves `__cause__`
  - trace:
    7. `new_trace_id()` returns a `UUID` instance
    8. `current_trace_id()` returns `None` outside any context
    9. Sync `trace_context()` sets + resets
    10. Async — propagation across single `await`
    11. Async — two concurrent tasks remain isolated
    12. Nested `trace_context()` blocks restore the outer trace_id on exit
- Do not implement OTel trace integration here (that's covered by the SDK's own `trace.get_current_span()` in story-core-02). SplunkGate's `trace_id` is a separate logical identifier from OTel's 128-bit `trace_id` — both can coexist; surface stories will set `splunkgate.trace_id` as an event attribute (story-core-02), independent of OTel's span trace_id.
