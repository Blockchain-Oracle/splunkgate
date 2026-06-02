# Story — Verdict pydantic v2 domain types

**ID:** story-core-01-verdict-pydantic-types
**Epic:** EPIC-03 — Core domain types
**Depends on:** story-skel-02-ruff-mypy-config
**Estimate:** ~2h
**Status:** PENDING

---

## User story

**As a** coding agent writing any Aegis surface (S1 middleware, S2 MCP server, S3 DefenseClaw config, S4 Splunk app event emission)
**I want to** import a single `Verdict` pydantic v2 BaseModel from `aegis_core.verdict` with the exact field shape locked in `docs/architecture.md` § "API schemas"
**So that** every surface emits structurally identical verdicts, the MCP `outputSchema` is derivable in one line via `Verdict.model_json_schema()`, and integration between surfaces does not require a refactor

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `packages/aegis_core/src/aegis_core/verdict.py` — NEW — `Severity`, `VerdictLabel`, `RuleHit`, `Verdict` pydantic v2 BaseModel + a `verdict_to_json_schema()` helper. ≤ 250 LOC. mypy --strict clean.
- `packages/aegis_core/src/aegis_core/__init__.py` — UPDATE — re-export `Severity`, `VerdictLabel`, `RuleHit`, `Verdict`; update `__all__`
- `packages/aegis_core/tests/test_verdict.py` — NEW — pytest + hypothesis property tests covering: enum membership, JSON Schema export contains all expected keys, round-trip serialization, severity ordering, NONE_SEVERITY accepted, rejected invalid `confidence` (out of [0,1])
- `packages/aegis_core/tests/conftest.py` — NEW — hypothesis profile registration for fast/CI runs
- `packages/aegis_core/pyproject.toml` — UPDATE — add `pydantic >= 2` to `dependencies`; add `hypothesis` to root `[dependency-groups].dev` (or workspace dev group — preserve existing entries)

The coding agent must NOT modify files outside this map without re-checking CLAUDE.md.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given the Verdict module exists
When  `uv run python -c "from aegis_core.verdict import Verdict, Severity, VerdictLabel, RuleHit; print('ok')"` runs
Then  exit code is 0
And   stdout contains "ok"

Given Severity enum is imported
When  `uv run python -c "from aegis_core.verdict import Severity; print(sorted(s.value for s in Severity))"` runs
Then  stdout contains "NONE_SEVERITY"
And   stdout contains "LOW"
And   stdout contains "MEDIUM"
And   stdout contains "HIGH"

Given VerdictLabel enum is imported
When  `uv run python -c "from aegis_core.verdict import VerdictLabel; print(sorted(v.value for v in VerdictLabel))"` runs
Then  stdout contains "ALLOW"
And   stdout contains "BLOCK"
And   stdout contains "MODIFY"
And   stdout contains "REVIEW"

Given a valid Verdict instance is constructed
When  `uv run python -c "from uuid import uuid4; from datetime import datetime, UTC; from aegis_core.verdict import Verdict, Severity, VerdictLabel, RuleHit; v = Verdict(trace_id=uuid4(), timestamp=datetime.now(UTC), verdict=VerdictLabel.BLOCK, severity=Severity.HIGH, rules=[RuleHit(rule='Prompt Injection', confidence=0.93, source='ai_defense')], surface='mcp_score', latency_ms=42.0); print(v.verdict.value)"` runs
Then  exit code is 0
And   stdout contains "BLOCK"

Given an invalid RuleHit confidence (> 1.0) is supplied
When  `uv run python -c "from aegis_core.verdict import RuleHit; RuleHit(rule='x', confidence=1.5, source='ai_defense')"` runs
Then  exit code is non-zero
And   stderr contains "ValidationError"

Given JSON Schema is exported
When  `uv run python -c "from aegis_core.verdict import Verdict; s=Verdict.model_json_schema(); assert 'trace_id' in s['properties']; assert 'rules' in s['properties']; assert 'classifications' in s['properties']; assert 'surface' in s['properties']; print('schema ok')"` runs
Then  stdout contains "schema ok"

Given the test suite runs
When  `uv run pytest packages/aegis_core/tests/test_verdict.py -q` runs
Then  exit code is 0
And   stdout contains a line matching at least "15 passed" (15+ behavioral cases including hypothesis property tests)

Given mypy strict mode is active for aegis_core
When  `uv run mypy packages/aegis_core/src` runs
Then  exit code is 0
And   stdout contains "Success: no issues found"

Given ruff is run against verdict.py
When  `uv run ruff check packages/aegis_core/src/aegis_core/verdict.py` runs
Then  exit code is 0

Given the 400-LOC rule is enforced
When  `uv run .pre-commit-hooks/check_loc.py packages/aegis_core/src/aegis_core/verdict.py` runs
Then  exit code is 0
```

Every criterion must be checkable by running a command. Prose-only criteria = blocked.

---

## Shell verification

The coding agent runs this to confirm the story is done before opening a PR:

```bash
# 1. Imports resolve
uv run python -c "from aegis_core.verdict import Verdict, Severity, VerdictLabel, RuleHit; print('imports ok')"

# 2. Severity enum has NONE_SEVERITY (matches Cisco AI Defense response enum)
uv run python -c "from aegis_core.verdict import Severity; assert 'NONE_SEVERITY' in [s.value for s in Severity]; print('NONE_SEVERITY ok')"

# 3. VerdictLabel has all four values (ALLOW/BLOCK/MODIFY/REVIEW)
uv run python -c "from aegis_core.verdict import VerdictLabel; assert set(v.value for v in VerdictLabel)=={'ALLOW','BLOCK','MODIFY','REVIEW'}; print('labels ok')"

# 4. JSON Schema export has every field from the architecture spec
uv run python -c "
from aegis_core.verdict import Verdict
s = Verdict.model_json_schema()
required = {'trace_id','timestamp','verdict','severity','rules','classifications','surface','latency_ms'}
missing = required - set(s['properties'].keys())
assert not missing, f'missing fields: {missing}'
print('schema fields ok')
"

# 5. Property tests (hypothesis) + structural tests pass
uv run pytest packages/aegis_core/tests/test_verdict.py -q

# 6. mypy --strict clean
uv run mypy packages/aegis_core/src

# 7. ruff clean
uv run ruff check packages/aegis_core/src/aegis_core/verdict.py

# 8. LOC under 400
uv run .pre-commit-hooks/check_loc.py packages/aegis_core/src/aegis_core/verdict.py

# 9. §14 clean — no mock/fake/dummy hits in production code
grep -rE "(mock|fake|dummy|hardcoded|simulated)" packages/aegis_core/src/ --include="*.py"
# Must output nothing
```

---

## Notes for coding agent

- Per `docs/architecture.md` § "API schemas" → "Verdict (the type every surface emits)", the exact field shape is:
  ```python
  class Severity(str, Enum):
      NONE_SEVERITY = "NONE_SEVERITY"   # matches Cisco AI Defense response enum
      LOW = "LOW"
      MEDIUM = "MEDIUM"
      HIGH = "HIGH"

  class VerdictLabel(str, Enum):
      ALLOW = "ALLOW"
      BLOCK = "BLOCK"
      MODIFY = "MODIFY"
      REVIEW = "REVIEW"

  class RuleHit(BaseModel):
      rule: str
      confidence: float = Field(ge=0.0, le=1.0)
      source: Literal["ai_defense", "defenseclaw_regex", "splunklib_security", "foundation_sec_classifier"]

  class Verdict(BaseModel):
      trace_id: UUID
      timestamp: datetime
      verdict: VerdictLabel
      severity: Severity
      rules: list[RuleHit]                              # NOT triggered_rules
      explanation: str | None = None
      classifications: list[str] = Field(default_factory=list)
      modifications: dict | None = None
      surface: Literal["mw_model","mw_tool","mw_subagent","mcp_score","mcp_judge_tool","mcp_check_output","mcp_audit","defenseclaw"]
      latency_ms: float
  ```
  Match it field-for-field. Do not rename `rules` to `triggered_rules` — the field name MUST match Cisco AI Defense's response shape so the AI Defense client can populate it directly.
- Per `../../../context/07-cisco-stack/01-ai-defense-deep.md`, Cisco AI Defense Inspection API response enum for `severity` includes the literal value `NONE_SEVERITY` alongside `LOW`/`MEDIUM`/`HIGH`. This story's `Severity` enum must include `NONE_SEVERITY` for direct interop. Without it the AI Defense client (story-judges-01) cannot round-trip safely.
- Per `../../../context/10-standards/02-otel-genai-semantic-conventions.md`, the `gen_ai.evaluation.result` event has a `score.label` slot which Aegis populates with `verdict.value.lower()` — so VerdictLabel values must round-trip through `.value.lower()` cleanly. `ALLOW`/`BLOCK`/`MODIFY`/`REVIEW` all do.
- Per `docs/architecture.md` § "Stack (locked)", pydantic version is v2. Use `BaseModel`, `Field`, `model_json_schema()`, and `model_validate()` — NOT v1 APIs.
- Per `docs/architecture.md` § "Banned patterns", no `Any` in `aegis_core`. `modifications: dict | None` is acceptable because it's a structured nullable; if mypy strict complains about `dict` lacking type params, use `dict[str, object]` (NOT `dict[str, Any]`).
- Per `docs/architecture.md` § "Coding standards" soft rules, all public classes get docstrings. Add a short numpy/Google-style docstring for `Verdict`, `RuleHit`, `Severity`, `VerdictLabel`.
- For the hypothesis property tests, register a `ci` profile in `conftest.py` with `max_examples=50` so test runs are fast in CI but exhaustive enough to catch enum-edge bugs. Reference: `hypothesis.settings.register_profile("ci", max_examples=50)`.
- Minimum 15 behavioral cases in `test_verdict.py`:
  1. `Verdict` round-trips through `model_dump_json()` + `model_validate_json()`
  2. All 4 Severity enum values import
  3. All 4 VerdictLabel values import
  4. `NONE_SEVERITY` round-trips through JSON
  5. `RuleHit` accepts `confidence=0.0`
  6. `RuleHit` accepts `confidence=1.0`
  7. `RuleHit` rejects `confidence=-0.01` (ValidationError)
  8. `RuleHit` rejects `confidence=1.01` (ValidationError)
  9. `RuleHit` rejects unknown `source` literal (ValidationError)
  10. `Verdict.model_json_schema()` returns dict with all 9 documented top-level properties
  11. `Verdict` rejects unknown `surface` literal (ValidationError)
  12. `Verdict` rejects non-UUID `trace_id` (ValidationError)
  13. `Verdict` accepts empty `rules` list
  14. `Verdict` accepts `explanation=None`
  15. `Verdict` accepts `modifications=None`
  16. (hypothesis) for any well-typed input, round-trip serialization preserves all fields
- The JSON schema export is load-bearing for story-mcp-01 (MCP `outputSchema`). Verify the schema is valid JSON Schema 2020-12 or draft-07 (whichever pydantic v2 emits by default — confirm via `mcp__context7__query-docs` for `pydantic`).
