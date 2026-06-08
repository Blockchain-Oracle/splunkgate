# Story — OTel `gen_ai.evaluation.result` event emitter

**ID:** story-core-02-otel-evaluation-event-emitter
**Epic:** EPIC-03 — Core domain types
**Depends on:** story-core-01-verdict-pydantic-types
**Estimate:** ~2h
**Status:** PENDING

---

## User story

**As a** coding agent emitting a `Verdict` from any surface (S1 middleware, S2 MCP server, S3 DefenseClaw shim, S4 Splunk app event ingest)
**I want to** call a single `emit_verdict_event(verdict, *, mcp_method_name=None, mcp_session_id=None)` from `splunkgate_core.otel` that emits a fully-OTel-GenAI-semantic-convention-compliant `gen_ai.evaluation.result` event
**So that** every surface lands events in OTel-compatible collectors (and Splunk via HEC) with the four required slots (`name`/`score.value`/`score.label`/`explanation`) plus the MCP sub-convention attrs (`mcp.method.name`, `mcp.session.id`) when the call originated from MCP

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `packages/splunkgate_core/src/splunkgate_core/otel.py` — NEW — `emit_verdict_event()` + `severity_to_score()` + `_build_attributes()` helpers. Wraps `opentelemetry.trace.get_current_span()` + `add_event()`. ≤ 280 LOC. mypy --strict clean.
- `packages/splunkgate_core/src/splunkgate_core/__init__.py` — UPDATE — re-export `emit_verdict_event`; update `__all__`
- `packages/splunkgate_core/tests/test_otel.py` — NEW — pytest cases using opentelemetry's `InMemorySpanExporter` to assert emitted event name/attrs match the OTel GenAI spec exactly. Includes both `mcp_method_name=None` (non-MCP origin) and the MCP-attrs-populated case.
- `packages/splunkgate_core/pyproject.toml` — UPDATE — add `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-util-genai` to `dependencies`

The coding agent must NOT modify files outside this map without re-checking CLAUDE.md.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given the OTel emitter module exists
When  `uv run python -c "from splunkgate_core.otel import emit_verdict_event; print('ok')"` runs
Then  exit code is 0
And   stdout contains "ok"

Given a Verdict is emitted to an in-memory OTel exporter (non-MCP origin)
When  the test runs end-to-end
Then  exactly one span event is captured
And   the event name is exactly "gen_ai.evaluation.result"

Given an emitted event for a BLOCK verdict
When  the event attributes are inspected
Then  `gen_ai.evaluation.name` is exactly "splunkgate.safety_verdict"
And   `gen_ai.evaluation.score.label` is exactly "block"
And   `gen_ai.evaluation.score.value` is a float
And   `gen_ai.evaluation.explanation` is the string from the Verdict (or absent if None)

Given the four score.label values are tested
When  Verdicts with verdict=ALLOW, BLOCK, MODIFY, REVIEW are each emitted
Then  the emitted `gen_ai.evaluation.score.label` values are exactly "allow", "block", "modify", "review" (lowercase)

Given a Verdict is emitted with mcp_method_name="tools/call" and mcp_session_id=<uuid>
When  the event attributes are inspected
Then  `mcp.method.name` is exactly "tools/call"
And   `mcp.session.id` equals the supplied UUID as a string

Given a Verdict is emitted without MCP context (mcp_method_name=None)
When  the event attributes are inspected
Then  neither `mcp.method.name` nor `mcp.session.id` appear in the attributes

Given a Verdict is emitted with splunkgate-custom attrs (surface + rules + trace_id)
When  the event attributes are inspected
Then  `splunkgate.surface` equals the Verdict.surface value
And   `splunkgate.trace_id` is the string form of Verdict.trace_id
And   `splunkgate.rules` is a list-of-strings matching [r.rule for r in verdict.rules]

Given severity_to_score is called
When  `uv run python -c "from splunkgate_core.otel import severity_to_score; from splunkgate_core.verdict import Severity; print(severity_to_score(Severity.NONE_SEVERITY), severity_to_score(Severity.LOW), severity_to_score(Severity.MEDIUM), severity_to_score(Severity.HIGH))"` runs
Then  stdout contains four ascending floats (0.0 ≤ NONE < LOW < MED < HIGH ≤ 1.0)

Given the test suite runs
When  `uv run pytest packages/splunkgate_core/tests/test_otel.py -q` runs
Then  exit code is 0
And   stdout contains a line matching at least "10 passed"

Given mypy strict mode is active
When  `uv run mypy packages/splunkgate_core/src` runs
Then  exit code is 0
And   stdout contains "Success: no issues found"

Given ruff is run against otel.py
When  `uv run ruff check packages/splunkgate_core/src/splunkgate_core/otel.py` runs
Then  exit code is 0

Given the 400-LOC rule
When  `uv run python .github/scripts/check_loc.py packages/splunkgate_core/src/splunkgate_core/otel.py` runs
Then  exit code is 0
```

Every criterion must be checkable by running a command. Prose-only criteria = blocked.

---

## Shell verification

The coding agent runs this to confirm the story is done before opening a PR:

```bash
# 1. Import resolves
uv run python -c "from splunkgate_core.otel import emit_verdict_event, severity_to_score; print('ok')"

# 2. Severity → score is monotonic
uv run python -c "
from splunkgate_core.otel import severity_to_score
from splunkgate_core.verdict import Severity
n,l,m,h = (severity_to_score(s) for s in (Severity.NONE_SEVERITY, Severity.LOW, Severity.MEDIUM, Severity.HIGH))
assert 0.0 <= n < l < m < h <= 1.0, f'non-monotonic: {n},{l},{m},{h}'
print('score monotonic ok')
"

# 3. Test suite passes (10+ behavioral cases)
uv run pytest packages/splunkgate_core/tests/test_otel.py -q

# 4. mypy --strict clean
uv run mypy packages/splunkgate_core/src

# 5. ruff clean
uv run ruff check packages/splunkgate_core/src/splunkgate_core/otel.py

# 6. LOC under 400
uv run python .github/scripts/check_loc.py packages/splunkgate_core/src/splunkgate_core/otel.py

# 7. §14 clean — no mock/fake/dummy hits in production code (test_otel.py uses InMemorySpanExporter which is real, not a mock)
grep -E "(mock|fake|dummy|hardcoded|simulated)" packages/splunkgate_core/src/splunkgate_core/otel.py
# Must output nothing
```

---

## Notes for coding agent

- Per `../../../context/10-standards/02-otel-genai-semantic-conventions.md`, the OTel GenAI semantic convention's `gen_ai.evaluation.result` event has exactly four standardized slots: `gen_ai.evaluation.name`, `gen_ai.evaluation.score.value`, `gen_ai.evaluation.score.label`, `gen_ai.evaluation.explanation`. Match these names exactly — they are the spec, not free-form attrs.
- Per `../../../context/10-standards/02-otel-genai-semantic-conventions.md`, the convention enumerates 55 `gen_ai.*` attributes (0 deprecated as of spec read date). This story only uses the four `gen_ai.evaluation.*` slots — other `gen_ai.*` attrs (e.g., `gen_ai.system`, `gen_ai.request.model`) are emitted by the calling surface's own model-invocation instrumentation, NOT by SplunkGate's verdict emitter. Do not pad attributes.
- Per `docs/architecture.md` § "OTel emission shape", the `score.label` values SplunkGate emits are the lowercased Verdict.value: `"block"`, `"allow"`, `"modify"`, `"review"`. These are CUSTOM enum extensions — the upstream OTel spec does not yet enumerate them. Per `docs/architecture.md` § "Open architectural questions" item 3, we propose this upstream post-hackathon. Do not change the casing.
- Per `../../../context/10-standards/01-mcp-spec-deep.md`, when a verdict originates from an MCP tool invocation, the OTel MCP sub-convention requires `mcp.method.name` and `mcp.session.id` attributes. Populate these only when supplied; do not synthesize defaults — absence is meaningful (signals non-MCP origin).
- Per `docs/architecture.md` § "OTel emission shape", the splunkgate-custom attrs are `splunkgate.surface`, `splunkgate.rules` (list-of-strings of rule names), and `splunkgate.trace_id` (string-cast UUID). These are intentionally namespaced under `splunkgate.*` so they don't collide with any future upstream `gen_ai.*` additions.
- `severity_to_score` mapping suggested values (monotonic, 0..1, evenly spaced):
  - `NONE_SEVERITY` → 0.0
  - `LOW` → 0.33
  - `MEDIUM` → 0.66
  - `HIGH` → 1.0
  Any monotonic mapping over [0,1] is correct; the suggested values match the four-quartile intuition. Cite this choice in your PR.
- Use `opentelemetry.trace.get_current_span().add_event(name, attributes=...)` — this attaches the event to the active span. If no active span exists (no enclosing trace context), emit to a NoopTracer span without raising; downstream collectors handle no-op events correctly. Do not `try/except: pass` — wrap in a check, not silent swallow.
- For tests, use `opentelemetry.sdk.trace.export.in_memory_span_exporter.InMemorySpanExporter` + `SimpleSpanProcessor` to capture emitted events. Reset the exporter between cases. Reference: query via `mcp__context7__resolve-library-id` for `opentelemetry-sdk` if unfamiliar with the test pattern.
- Per `docs/architecture.md` § "Banned patterns", no `Any` in `splunkgate_core`. Attribute dicts should be typed `dict[str, str | int | float | bool | list[str]]` (the OTel attribute value union per spec).
- Per `docs/architecture.md` § "Stack (locked)", the dep names are exactly `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-util-genai`. Add all three. Do not pin versions in this story — uv's lockfile handles it.
- The `explanation` slot is `str | None` in the Verdict. If None, OMIT the attribute (don't emit a literal `"None"` string).
- mypy --strict will require explicit return types on all functions — including the test functions. Use `-> None` consistently.
- Minimum 10 behavioral cases in `test_otel.py`:
  1. Event name is `gen_ai.evaluation.result`
  2. `gen_ai.evaluation.name` equals `splunkgate.safety_verdict`
  3. `score.label` lowercases for ALLOW, BLOCK, MODIFY, REVIEW (4 parameterized cases)
  4. `score.value` is a float in [0.0, 1.0]
  5. `explanation` attr absent when Verdict.explanation is None
  6. `explanation` attr matches Verdict.explanation when non-None
  7. MCP attrs populated when args supplied
  8. MCP attrs absent when args None
  9. `splunkgate.surface` matches Verdict.surface
  10. `splunkgate.rules` is a list of rule-name strings
  11. `splunkgate.trace_id` is the string UUID
