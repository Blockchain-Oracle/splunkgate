# Story — DefenseClaw Python shim: splunkgate_judges.defenseclaw_backend

**ID:** story-judges-06-defenseclaw-python-shim
**Epic:** EPIC-04 — Cisco AI Defense Inspection API client
**Depends on:** story-core-01-verdict-pydantic-types, story-dc-01-config-delta-docs-and-example
**Estimate:** ~2h
**Status:** PENDING

---

## User story

**As a** coding agent picking up `story-mw-02` (tool middleware), `story-mw-05` (subagent middleware), or `story-mcp-03` (judge_tool_call MCP tool) — each of which imports `splunkgate_judges.defenseclaw_backend.evaluate_tool_call(...)` or `evaluate_subagent_call(...)`
**I want to** import that module and get a working Python wrapper that loads the DefenseClaw upstream YAML rule packs (regex rule definitions from the cloned DefenseClaw repo at the pinned commit) and exposes typed `evaluate_tool_call(name, args) -> RuleHit | None` and `evaluate_subagent_call(handoff) -> RuleHit | None` functions returning `splunkgate_core.RuleHit` instances
**So that** the 3 downstream stories that already assume this module exists can dispatch without TODO comments, the cheap first-pass regex classifier runs in-process (no Go subprocess shelling), and we stay honest to the architecture's claim that "SplunkGate depends on DefenseClaw, contributes back upstream" by porting only the rule-data (YAML), not the Go engine

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `packages/splunkgate_judges/src/splunkgate_judges/defenseclaw_backend.py` — NEW — ~350 LOC, mypy --strict clean. Public surface: (1) `class DefenseClawRule(BaseModel)` mirroring the YAML rule-pack schema (`id: str`, `category: str`, `pattern: str` — Python-`re`-compatible regex, `severity: Literal["LOW","MEDIUM","HIGH"]`, `description: str | None`, `tags: list[str]`); (2) `class DefenseClawBackend` — constructed with optional `rules_dir: Path | None = None` (defaults to `Path(__file__).parent / "rules" / "defenseclaw"`); loads + compiles all `*.yaml` rule files at init via `yaml.safe_load`; raises `splunkgate_core.errors.RulePackLoadError` on malformed YAML; (3) `def evaluate_tool_call(self, tool_name: str, tool_args: dict[str, object]) -> RuleHit | None  # `object` NOT `Any` — architecture.md § "Banned patterns" forbids `Any` in `splunkgate_judges`; story Notes lines 196/204 confirm `dict[str, object]` is the canonical shape` — serializes `{tool_name, **tool_args}` to a JSON-text string, runs every compiled regex, returns the highest-severity hit as a `RuleHit` (per `splunkgate_core.verdict.RuleHit` — `rule=<rule.category>`, `confidence=1.0` for regex hits since they're binary, `source="defenseclaw_regex"`); (4) `def evaluate_subagent_call(self, handoff: dict[str, object]) -> RuleHit | None  # same `dict[str, object]` discipline` — same scheme over the handoff payload (per `story-mw-05` shape); (5) `def evaluate_text(self, text: str) -> RuleHit | None` — generic text-scan helper used by `story-mcp-03`; (6) module-level `_DEFAULT_BACKEND: DefenseClawBackend | None = None` + `def get_default_backend() -> DefenseClawBackend` that lazy-initializes the singleton; (7) module-level functional wrappers `evaluate_tool_call(...)`, `evaluate_subagent_call(...)`, `evaluate_text(...)` that delegate to the singleton (this is the API the 3 stories already call).
- `packages/splunkgate_judges/src/splunkgate_judges/rules/defenseclaw/README.md` — NEW — explains the rule-pack provenance: vendored from DefenseClaw upstream `e1cb4d93fba70f5ffba8052ee6cfc696abdf125f` (v0.6.5), specifically the YAML rule files at `internal/rules/packs/*.yaml`. License notice: Apache-2.0 © Cisco Systems, Inc. 2026. Update policy: when DefenseClaw upstream bumps a rule, re-vendor the YAML and bump `_PACK_REV` constant. Citation to `../../../context/HALLUCINATION-AUDIT.md` H-44/H-45 (DefenseClaw is a Go binary at the engine layer; only the rule data — YAML — is ported).
- `packages/splunkgate_judges/src/splunkgate_judges/rules/defenseclaw/builtin.yaml` — NEW — minimal vendored rule pack covering the patterns `story-mcp-03` notes calls out: `shell_exec` regex (`(rm\s+-rf|;\s*sh\s|;\s*bash\s)`), `base64_payload` regex (`[A-Za-z0-9+/]{40,}={0,2}`), `ssn` regex (`\b\d{3}-\d{2}-\d{4}\b`), `path_traversal` regex (`(\.\./){2,}|/etc/(passwd|shadow)`), `sql_injection` regex (`(';\s*DROP\s+TABLE|';\s*--|UNION\s+SELECT)`). Each with `severity` set, `category` set (mapping to one of the 11 AI Defense rule names: `Code Detection`, `PII`, etc. — for verdict rule-name compatibility), `description`. ≥ 5 rules total; ≤ 80 lines.
- `packages/splunkgate_judges/src/splunkgate_judges/__init__.py` — UPDATE — re-export `DefenseClawBackend`, `DefenseClawRule`, `get_default_backend`, and the three functional wrappers; update `__all__`.
- `packages/splunkgate_judges/pyproject.toml` — UPDATE — add `pyyaml` to `dependencies` (used for rule-pack loading; already vendored transitively but declare explicitly).
- `packages/splunkgate_core/src/splunkgate_core/errors.py` — UPDATE — add `RulePackLoadError(SplunkGateError)` taking the offending file path + parse error.
- `packages/splunkgate_judges/tests/test_defenseclaw_backend.py` — NEW — ≥ 14 behavioral tests: (1) `get_default_backend()` returns a singleton (`is`-identity across two calls); (2) backend loads the vendored `builtin.yaml` and compiles ≥ 5 rules at init; (3) malformed YAML raises `RulePackLoadError`; (4) `evaluate_tool_call("shell.exec", {"cmd": "rm -rf /"})` returns a HIGH-severity RuleHit; (5) `evaluate_tool_call("noop", {"foo": "bar"})` returns `None`; (6) `evaluate_text("'; DROP TABLE users; --")` flags as sql_injection HIGH; (7) `evaluate_text("123-45-6789")` flags as ssn (PII rule); (8) `evaluate_text("../../../etc/passwd")` flags as path_traversal; (9) returned RuleHit `source` field is always `"defenseclaw_regex"`; (10) returned RuleHit `confidence` is always `1.0`; (11) when multiple rules hit, the highest-severity is returned (HIGH > MEDIUM > LOW); (12) RuleHit's `rule` field maps to one of the 11 verbatim AI Defense rule names (`Code Detection, Harassment, Hate Speech, PCI, PHI, PII, Profanity, Prompt Injection, Sexual Content & Exploitation, Social Division & Polarization, Violence & Public Safety Threats`); (13) `evaluate_subagent_call({"target": "exec_agent", "args": {"shell": "rm -rf /"}})` flags; (14) backend with custom `rules_dir` (tmp_path fixture loading a one-rule fixture) loads + applies only those rules.

The coding agent must NOT modify files outside this map without re-checking `CLAUDE.md`. In particular: **do not** clone DefenseClaw Go code into this repo (per `story-dc-01` and `../../../context/HALLUCINATION-AUDIT.md` — we depend on DefenseClaw, do not rebuild its engine); **do not** call into DefenseClaw's Go binary via subprocess (this is the cheap in-process Python rule-data path — fast, deterministic, no shelling); **do not** add a HTTP client to call a DefenseClaw service (we are not running DefenseClaw as a service in this surface — `story-dc-01` documents the docker-compose pattern for Surface 3).

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given the module exists
When  `uv run python -c "from splunkgate_judges import DefenseClawBackend, get_default_backend, evaluate_tool_call, evaluate_subagent_call, evaluate_text; print('ok')"` runs
Then  exit code is 0
And   stdout contains "ok"

Given the default backend is requested twice
When  `uv run python -c "from splunkgate_judges import get_default_backend; print(get_default_backend() is get_default_backend())"` runs
Then  the output is "True"

Given the builtin rule pack is loaded
When  `uv run python -c "from splunkgate_judges import get_default_backend; print(len(get_default_backend().rules) >= 5)"` runs
Then  the output is "True"

Given a tool call with a shell-execute payload
When  `uv run python -c "from splunkgate_judges import evaluate_tool_call; h = evaluate_tool_call('shell.exec', {'cmd': 'rm -rf /'}); print(h.rule, h.source, h.confidence)"` runs
Then  stdout matches `^Code Detection defenseclaw_regex 1\.0$` (or another verbatim 11-rule name + the regex source + confidence 1.0)

Given a benign tool call
When  `uv run python -c "from splunkgate_judges import evaluate_tool_call; print(evaluate_tool_call('noop', {'foo': 'bar'}))"` runs
Then  the output is "None"

Given a text with a SQL injection payload
When  evaluate_text("'; DROP TABLE users; --") runs
Then  the returned RuleHit has source=="defenseclaw_regex" and severity is HIGH (via the rule pack)

Given a text with an SSN pattern (e.g., 123-45-6789)
When  evaluate_text(...) runs
Then  the returned RuleHit's rule is "PII"

Given the rule pack contains 5 rules and two of them match the input
When  evaluate_text matches both
Then  the higher-severity rule's RuleHit is returned (deterministic tie-break: HIGH > MEDIUM > LOW)

Given a malformed YAML rule file is placed in a custom rules_dir
When  DefenseClawBackend(rules_dir=tmp) is constructed
Then  RulePackLoadError is raised with the offending file path in the message

Given every returned RuleHit
When  `rule_hit.source` is inspected
Then  the value is exactly "defenseclaw_regex" (matches the Literal in splunkgate_core.verdict.RuleHit)

Given every returned RuleHit's rule name
When  the value is checked against the 11 verbatim AI Defense rule names
Then  the value is a member of the set: {"Code Detection","Harassment","Hate Speech","PCI","PHI","PII","Profanity","Prompt Injection","Sexual Content & Exploitation","Social Division & Polarization","Violence & Public Safety Threats"}

Given the test suite runs
When  `uv run pytest packages/splunkgate_judges/tests/test_defenseclaw_backend.py -v` runs
Then  ≥ 14 tests pass and 0 fail

Given mypy strict mode is active
When  `uv run mypy --strict packages/splunkgate_judges/src/splunkgate_judges/defenseclaw_backend.py` runs
Then  exit code is 0

Given ruff
When  `uv run ruff check packages/splunkgate_judges/src/splunkgate_judges/defenseclaw_backend.py` runs
Then  exit code is 0

Given the 400-LOC rule
When  `wc -l packages/splunkgate_judges/src/splunkgate_judges/defenseclaw_backend.py` runs
Then  the line count is ≤ 400

Given the §14 grep on the source
When  `grep -rE "(mock|fake|dummy|hardcoded|simulated)" packages/splunkgate_judges/src/splunkgate_judges/defenseclaw_backend.py` runs
Then  output is empty (the vendored rule YAML is provenance, not mock data)
```

---

## Shell verification

The coding agent runs this end-to-end locally to confirm the story is done before opening a PR:

```bash
set -euo pipefail

# 1. Imports + singleton
uv run python -c "
from splunkgate_judges import (
    DefenseClawBackend, DefenseClawRule, get_default_backend,
    evaluate_tool_call, evaluate_subagent_call, evaluate_text,
)
assert get_default_backend() is get_default_backend()
print('ok')
"

# 2. Rule pack loads with ≥ 5 rules
uv run python -c "
from splunkgate_judges import get_default_backend
b = get_default_backend()
print(f'rules loaded: {len(b.rules)}')
assert len(b.rules) >= 5
"

# 3. Shell-exec payload flagged HIGH
uv run python - <<'PY'
from splunkgate_judges import evaluate_tool_call
h = evaluate_tool_call("shell.exec", {"cmd": "rm -rf /"})
assert h is not None, "expected hit"
assert h.source == "defenseclaw_regex"
assert h.confidence == 1.0
ALLOWED = {"Code Detection","Harassment","Hate Speech","PCI","PHI","PII",
           "Profanity","Prompt Injection","Sexual Content & Exploitation",
           "Social Division & Polarization","Violence & Public Safety Threats"}
assert h.rule in ALLOWED, h.rule
print("shell-exec ok:", h.rule)
PY

# 4. Benign call returns None
uv run python -c "
from splunkgate_judges import evaluate_tool_call
assert evaluate_tool_call('noop', {'foo': 'bar'}) is None
print('benign ok')
"

# 5. SSN → PII rule
uv run python -c "
from splunkgate_judges import evaluate_text
h = evaluate_text('123-45-6789')
assert h is not None and h.rule == 'PII', h
print('ssn ok')
"

# 6. SQL-injection → high
uv run python - <<'PY'
from splunkgate_judges import evaluate_text
h = evaluate_text(\"'; DROP TABLE users; --\")
assert h is not None
print('sql ok:', h.rule)
PY

# 7. Tests pass (≥ 14)
uv run pytest packages/splunkgate_judges/tests/test_defenseclaw_backend.py -v 2>&1 | tee /tmp/pytest.out
[ "$(grep -cE 'PASSED' /tmp/pytest.out)" -ge 14 ]

# 8. mypy --strict
uv run mypy --strict packages/splunkgate_judges/src/splunkgate_judges/defenseclaw_backend.py

# 9. ruff
uv run ruff check packages/splunkgate_judges/src/splunkgate_judges/defenseclaw_backend.py

# 10. 400-LOC cap
[ "$(wc -l < packages/splunkgate_judges/src/splunkgate_judges/defenseclaw_backend.py)" -le 400 ]

# 11. §14 clean
! grep -E "(mock|fake|dummy|hardcoded|simulated)" packages/splunkgate_judges/src/splunkgate_judges/defenseclaw_backend.py
echo "ALL CHECKS PASS"
```

All 11 blocks must exit 0 before opening the PR.

---

## Notes for coding agent

- **Per `../../../context/HALLUCINATION-AUDIT.md` H-44/H-45**, DefenseClaw is a Go binary with `internal/audit/sinks/splunk_hec.go` exactly 600 lines and `internal/gateway/proxy.go` exactly 4430 lines. We DEPEND on DefenseClaw (the Go binary runs as Surface 3 via `story-dc-01`'s docker-compose), but the cheap in-process Python first-pass classifier is THIS story: a YAML-data port of DefenseClaw's regex rule patterns. The engine stays Go; we port the rule shape.
- **Per `story-dc-01` and the audit synthesis Block D**, this story creates `splunkgate_judges.defenseclaw_backend` because 3 downstream stories (mw-02, mw-05, mcp-03) already import it without owner. The function signatures are pinned by what those stories call: `evaluate_tool_call(name, args)`, `evaluate_subagent_call(handoff)`, and `evaluate_text(...)` (the latter for mcp-03's MCP tool flow).
- **Per `docs/architecture.md` § "Verdict" → `RuleHit.source`**, the Literal type for the source field includes `"defenseclaw_regex"`. Every RuleHit this backend returns uses that exact string. (Audit fix A-5 removed `"foundation_sec_classifier"` from this Literal — do NOT reintroduce it.)
- **Per `../../../context/07-cisco-stack/01-ai-defense-deep.md` §7**, the 11 verbatim AI Defense rule names are: `Code Detection, Harassment, Hate Speech, PCI, PHI, PII, Profanity, Prompt Injection, Sexual Content & Exploitation, Social Division & Polarization, Violence & Public Safety Threats`. The `RuleHit.rule` field returned by THIS shim MUST be one of these 11 strings so verdict consumers don't have to know which judge layer produced the hit. Map DefenseClaw's internal categories (e.g., `shell_exec`) to the closest AI Defense rule (`Code Detection`). Document the mapping in the YAML rule's `category` field; the loader uses the YAML category as the `RuleHit.rule` value.
- **Per `docs/architecture.md` § "Banned patterns"**, no `Any` type in `splunkgate_judges` (mypy --strict clean). The `tool_args: dict[str, Any]` argument is the exception (the input is intentionally schema-flexible — that's why we scan with regex). Add an inline `# type: ignore` justification IF mypy needs it, but prefer `dict[str, object]` and `repr()` for serialization.
- **Per `docs/architecture.md` § "Banned"** > `requests`, use stdlib + `pyyaml`. No HTTP calls in this module.
- **Vendored rule pack provenance**: rules at `packages/splunkgate_judges/src/splunkgate_judges/rules/defenseclaw/builtin.yaml` are derived from DefenseClaw upstream `e1cb4d93` (v0.6.5, `../inspiration/defenseclaw/`). The README.md in that directory MUST cite the commit hash + Apache-2.0 license + Cisco copyright. This matters for license compliance under § "submission checklist gates" > "Apache-2.0 license auto-detectable".
- **Singleton initialization** is lazy (first call to `get_default_backend()` reads disk + compiles regexes). All three module-level functional wrappers go through the singleton. Tests can replace the singleton via dependency injection — DO NOT muck with module globals from tests; pass a fresh `DefenseClawBackend(rules_dir=tmp_path)` instead.
- **Severity tie-break**: when multiple rules match, return the highest-severity hit. Ties at the same severity: return the rule that matched the longest substring (deterministic and intuitive — more specific match wins). Document this in the docstring.
- **Per `story-mcp-03` notes**, the cheap-first-pass classifier should run BEFORE the AI Defense Inspection API call. SplunkGate MW (story-mw-02) and SplunkGate MCP (story-mcp-03) both check `evaluate_tool_call(...)` first; if HIGH-severity hit + `config.escalate_on_first_pass_hit=False`, they short-circuit. Otherwise escalate to `splunkgate_judges.ai_defense.inspect(...)`. This module doesn't decide escalation policy — it just returns the hit.
- **Compile regexes once at init** (`re.compile`); store the compiled pattern in `DefenseClawRule._compiled` (Pydantic v2 PrivateAttr). Re-compiling per call is a hot-path performance killer — `evaluate_tool_call` may run thousands of times per agent invocation.
- **`yaml.safe_load`, never `yaml.load`** — Bandit will flag `yaml.load` as a known CVE pattern per `docs/cicd-spec.md` § "bandit" job.
- **mypy --strict requires explicit return types on all internal helpers**. Use `-> None` consistently. The `dict[str, object]` shape for `tool_args` (preferred over `dict[str, Any]`) keeps the module Any-free per `docs/architecture.md` § "Banned patterns".
- **Per `docs/architecture.md` § "submission checklist gates"** > "§14 clean", the production code path has no mock/fake/dummy hits. The vendored YAML IS production rule data (not a mock), so the §14 grep passes. The README.md citing "rule packs vendored from upstream" is provenance, not synthetic-data labeling.
- **Future-proofing for `story-dc-02` (upstream PR adding AI Defense backend)**: if DefenseClaw upstream adds API-backend dispatch, this Python shim stays unchanged — DefenseClaw running as Surface 3 invokes the API backend via Go; the Python shim continues to be the cheap in-process first-pass. Document this delineation in the module docstring.
- Estimate breakdown: ~30 min YAML schema + rule pack content (5 verbatim regexes), ~45 min DefenseClawBackend class + singleton + regex compile, ~30 min RulePackLoadError + tie-break logic, ~45 min tests (14 cases — incl. tmp_path custom rules_dir fixture), ~15 min docstrings + README provenance citation.
