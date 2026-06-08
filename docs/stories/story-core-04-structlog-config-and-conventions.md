# Story — structlog config + stable key conventions

**ID:** story-core-04-structlog-config-and-conventions
**Epic:** EPIC-03 — Core domain types
**Depends on:** story-skel-02-ruff-mypy-config
**Estimate:** ~2h
**Status:** PENDING

---

## User story

**As a** coding agent writing any SplunkGate surface
**I want to** call `from splunkgate_core.logging import get_logger` and get a pre-configured `structlog` BoundLogger that (a) renders JSON in prod and console-pretty in dev (env-toggled), (b) emits stable key names (`event`, `verdict`, `severity`, `trace_id`, ...), and (c) auto-injects the current `trace_id` (from `splunkgate_core.trace`) into every log record
**So that** the architecture's hard rule "All log lines use `structlog` with stable key names" is enforced by API shape (not by reviewer vigilance), and SOC analysts searching `cisco_ai_defense:splunkgate_verdict` events can join across log + Verdict + OTel event via a single key

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `packages/splunkgate_core/src/splunkgate_core/logging.py` — NEW — `configure_logging(*, dev_mode: bool | None = None)`, `get_logger(name: str)`, a `_trace_id_processor` that pulls `current_trace_id()` from `splunkgate_core.trace` into every record. ≤ 200 LOC. mypy --strict clean.
- `packages/splunkgate_core/src/splunkgate_core/__init__.py` — UPDATE — re-export `get_logger`, `configure_logging`; update `__all__`
- `packages/splunkgate_core/tests/test_logging.py` — NEW — pytest cases using `structlog.testing.capture_logs()` (or `LogCapture` processor) to assert key shape, JSON-vs-console toggling, auto-injected trace_id presence
- `packages/splunkgate_core/pyproject.toml` — UPDATE — add `structlog` to `dependencies`

The coding agent must NOT modify files outside this map without re-checking CLAUDE.md.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given the logging module exists
When  `uv run python -c "from splunkgate_core.logging import get_logger, configure_logging; print('ok')"` runs
Then  exit code is 0
And   stdout contains "ok"

Given configure_logging(dev_mode=False) was called
When  a log record is emitted via the BoundLogger
Then  the captured output line parses as valid JSON

Given configure_logging(dev_mode=True) was called
When  a log record is emitted via the BoundLogger
Then  the captured output line contains ANSI color codes OR contains the literal "event=" key=value style (console renderer)

Given the env var SPLUNKGATE_LOG_FORMAT=json is set
When  configure_logging() is called with dev_mode=None (auto-detect)
Then  the JSON renderer is selected (output parses as JSON)

Given the env var SPLUNKGATE_LOG_FORMAT=console is set
When  configure_logging() is called with dev_mode=None
Then  the console renderer is selected

Given a log record is emitted inside an active trace_context
When  the record is captured
Then  the record dict contains key "trace_id" with the value of current_trace_id() as a string

Given a log record is emitted OUTSIDE any trace_context
When  the record is captured
Then  the record dict either omits "trace_id" OR includes "trace_id" with value None

Given stable key conventions
When  a Verdict-related log call is made with bound keys (event, verdict, severity, trace_id)
Then  all four keys appear in the captured record

Given the test suite runs
When  `uv run pytest packages/splunkgate_core/tests/test_logging.py -q` runs
Then  exit code is 0
And   stdout contains a line matching at least "8 passed"

Given mypy strict mode is active
When  `uv run mypy packages/splunkgate_core/src` runs
Then  exit code is 0
And   stdout contains "Success: no issues found"

Given ruff is run against logging.py
When  `uv run ruff check packages/splunkgate_core/src/splunkgate_core/logging.py` runs
Then  exit code is 0

Given the 400-LOC rule
When  `uv run python .github/scripts/check_loc.py packages/splunkgate_core/src/splunkgate_core/logging.py` runs
Then  exit code is 0

Given the banned-pattern rule
When  `grep -nE '\bprint\(' packages/splunkgate_core/src/splunkgate_core/logging.py` runs
Then  stdout is empty (no print() in production code)
```

Every criterion must be checkable by running a command. Prose-only criteria = blocked.

---

## Shell verification

The coding agent runs this to confirm the story is done before opening a PR:

```bash
# 1. Imports resolve
uv run python -c "from splunkgate_core.logging import get_logger, configure_logging; print('ok')"

# 2. JSON renderer in prod mode
uv run python -c "
import json, io, sys
from splunkgate_core.logging import configure_logging, get_logger
buf = io.StringIO()
configure_logging(dev_mode=False)
import structlog
log = get_logger('test')
# capture via structlog.testing
from structlog.testing import capture_logs
with capture_logs() as cap:
    log.info('hello', verdict='BLOCK', severity='HIGH')
assert any(r.get('event') == 'hello' for r in cap)
print('json mode capture ok')
"

# 3. Console renderer in dev mode
SPLUNKGATE_LOG_FORMAT=console uv run python -c "
from splunkgate_core.logging import configure_logging
configure_logging()  # auto-detect
print('dev mode configure ok')
"

# 4. trace_id auto-injected inside trace_context
uv run python -c "
from structlog.testing import capture_logs
from splunkgate_core.logging import configure_logging, get_logger
from splunkgate_core.trace import new_trace_id, trace_context
configure_logging(dev_mode=False)
log = get_logger('test')
tid = new_trace_id()
with capture_logs() as cap, trace_context(tid):
    log.info('inside', verdict='ALLOW')
assert any(str(tid) == str(r.get('trace_id')) for r in cap), f'trace_id missing in {cap}'
print('trace_id auto-injected ok')
"

# 5. Test suite passes
uv run pytest packages/splunkgate_core/tests/test_logging.py -q

# 6. mypy --strict clean
uv run mypy packages/splunkgate_core/src

# 7. ruff clean
uv run ruff check packages/splunkgate_core/src/splunkgate_core/logging.py

# 8. LOC under 400
uv run python .github/scripts/check_loc.py packages/splunkgate_core/src/splunkgate_core/logging.py

# 9. No print() in production code
grep -nE '\bprint\(' packages/splunkgate_core/src/splunkgate_core/logging.py
# Must output nothing

# 10. §14 clean
grep -E "(mock|fake|dummy|hardcoded|simulated)" packages/splunkgate_core/src/splunkgate_core/logging.py
# Must output nothing
```

---

## Notes for coding agent

- Per `docs/architecture.md` § "Coding standards" soft rules: "All log lines use `structlog` with stable key names (`event`, `verdict`, `severity`, `trace_id`, ...)." Encode the stable keys in the module's docstring + add a `LogKeys` Literal type listing them so type-checkers can flag misspellings downstream.
- Per `docs/architecture.md` § "Banned patterns", `print()` for logs is banned. The greppable check is in the acceptance criteria.
- Per `docs/architecture.md` § "Stack (locked)", structlog is the logging library. Do NOT add `logging.basicConfig` direct calls — use structlog's `configure()` API.
- Per `docs/architecture.md` § "ADR-005", SplunkGate events land in Splunk under the `cisco_ai_defense:splunkgate_verdict` sourcetype. JSON-renderer output is what Splunk's HEC ingest parses against `props.conf` (story-app-02). The JSON shape must be flat (one level deep) — structlog's `JSONRenderer` does this by default. Do not introduce nested dicts in log calls.
- Env var convention: `SPLUNKGATE_LOG_FORMAT={json|console}`. If unset, default to `console` when `sys.stderr.isatty()` returns True (developer terminal), else `json` (CI / prod). The `dev_mode` kwarg to `configure_logging()` overrides the env var; if both are unset, the isatty check is the tiebreaker. Per `docs/architecture.md` § "Banned patterns" "Hardcoded mock data in hot path", config toggles are env-var driven by convention — do not bake a hardcoded default at module-import time.
- The `_trace_id_processor` is a structlog processor that reads `current_trace_id()` from `splunkgate_core.trace`:
  ```python
  def _trace_id_processor(logger, method_name, event_dict):
      tid = current_trace_id()
      if tid is not None:
          event_dict["trace_id"] = str(tid)
      return event_dict
  ```
  Add it to the processor chain BEFORE the renderer.
- structlog processor chain (suggested):
  ```python
  processors = [
      structlog.contextvars.merge_contextvars,
      structlog.processors.add_log_level,
      structlog.processors.TimeStamper(fmt="iso", utc=True),
      _trace_id_processor,
      structlog.processors.StackInfoRenderer(),
      structlog.processors.format_exc_info,
      renderer,  # JSONRenderer() for prod, ConsoleRenderer() for dev
  ]
  ```
  Confirm exact processor names via `mcp__context7__resolve-library-id` for `structlog` then `mcp__context7__query-docs` for "processors".
- `get_logger(name: str) -> structlog.BoundLogger` — name is conventionally the module `__name__`. Calling `get_logger` before `configure_logging` should not crash; structlog handles a default config that gets overridden on first `configure_logging()` call.
- Tests: structlog ships `structlog.testing.capture_logs()` (context manager that captures records as list-of-dicts). Use it — do not use `caplog` (stdlib logging fixture; structlog records won't appear unless you wire `LoggerFactory` to stdlib's logger, which is overkill for these tests).
- Per `docs/architecture.md` § "Banned patterns", no `Any` in `splunkgate_core`. structlog's BoundLogger has `Any`-ish call signatures by design — use `cast(structlog.BoundLogger, ...)` where mypy --strict complains; document the cast inline (justification comment required by CLAUDE.md).
- Minimum 8 behavioral cases in `test_logging.py`:
  1. `get_logger` returns a BoundLogger
  2. `configure_logging(dev_mode=False)` selects JSON renderer (output parses as JSON when captured via a side-channel — easier: assert via env var probe)
  3. `configure_logging(dev_mode=True)` selects ConsoleRenderer
  4. `SPLUNKGATE_LOG_FORMAT=json` env var overrides dev_mode auto-detect to JSON
  5. `SPLUNKGATE_LOG_FORMAT=console` env var overrides dev_mode auto-detect to console
  6. Log record inside `trace_context(tid)` contains `trace_id` key equal to str(tid)
  7. Log record outside any trace_context does NOT contain a non-None `trace_id`
  8. Bound keys `event`, `verdict`, `severity` round-trip through capture
  9. (bonus) Nested `trace_context()` blocks: inner trace_id appears in inner-scope logs, outer trace_id resumes after exit
