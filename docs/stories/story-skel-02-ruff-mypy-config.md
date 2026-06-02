# Story — ruff + mypy config (strict-where-it-counts)

**ID:** story-skel-02-ruff-mypy-config
**Epic:** EPIC-02 — Repo skeleton + coding standards
**Depends on:** story-skel-01-uv-workspace-pyproject
**Estimate:** ~1.5h
**Status:** PENDING

---

## User story

**As a** coding agent writing code in any Aegis package
**I want to** have `.ruff.toml` and `mypy.ini` pre-tuned to the repo's standards (line-length 100, all ruff rules enabled except E501, mypy strict for `aegis_core`+`aegis_judges`, non-strict elsewhere)
**So that** running `uv run ruff check .` and `uv run mypy` against the skeleton tree returns exit 0 with no findings — and any future PR's failures will be substantive, not config-noise

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `.ruff.toml` — NEW — line-length=100, target-py=3.13, select="ALL", ignore=["E501","D203","D213","COM812","ISC001"] (formatter conflicts + line-length deferred to formatter), per-file-ignores for tests
- `mypy.ini` — NEW — global `python_version = 3.13`; non-strict baseline; per-module overrides flipping `strict = True` for `aegis_core.*` and `aegis_judges.*`
- `pyproject.toml` — UPDATE — add `[dependency-groups]` `dev = ["ruff", "mypy", ...]` (preserving existing dev group entries)
- `packages/aegis_core/src/aegis_core/__init__.py` — UPDATE — add `__all__: list[str] = []` so mypy strict has something typed to check against
- `packages/aegis_judges/src/aegis_judges/__init__.py` — UPDATE — add `__all__: list[str] = []` so mypy strict has something typed to check against
- `packages/aegis_core/tests/test_skeleton.py` — UPDATE — add a ruff-clean + mypy-clean assertion (typed test function with explicit return annotation)

The coding agent must NOT modify files outside this map without re-checking CLAUDE.md.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given .ruff.toml exists at repo root
When  `uv run ruff check .` runs
Then  exit code is 0
And   stdout contains "All checks passed!" (or equivalent zero-finding message)

Given mypy.ini exists at repo root
When  `uv run mypy packages/aegis_core/src packages/aegis_judges/src` runs
Then  exit code is 0
And   stdout contains "Success: no issues found"

Given mypy.ini per-module override sets strict = True for aegis_core
When  `uv run python -c "import configparser; c=configparser.ConfigParser(); c.read('mypy.ini'); print(c.get('mypy-aegis_core.*','strict'))"` runs
Then  stdout contains "True"

Given mypy.ini per-module override sets strict = True for aegis_judges
When  `uv run python -c "import configparser; c=configparser.ConfigParser(); c.read('mypy.ini'); print(c.get('mypy-aegis_judges.*','strict'))"` runs
Then  stdout contains "True"

Given .ruff.toml line-length is 100
When  `uv run python -c "import tomllib; d=tomllib.load(open('.ruff.toml','rb')); print(d.get('line-length'))"` runs
Then  stdout is "100"

Given .ruff.toml select rule is ALL
When  `uv run python -c "import tomllib; d=tomllib.load(open('.ruff.toml','rb')); print('ALL' in d['lint']['select'])"` runs
Then  stdout is "True"

Given .ruff.toml ignores E501 (line-length deferred to formatter)
When  `uv run python -c "import tomllib; d=tomllib.load(open('.ruff.toml','rb')); print('E501' in d['lint']['ignore'])"` runs
Then  stdout is "True"

Given a deliberately broken Python file is created at /tmp/aegis_ruff_probe.py with content `import os\n\n` (unused import)
When  `uv run ruff check /tmp/aegis_ruff_probe.py` runs
Then  exit code is non-zero
And   stdout contains "F401" (unused import rule fires)
```

Every criterion must be checkable by running a command. Prose-only criteria = blocked.

---

## Shell verification

The coding agent runs this to confirm the story is done before opening a PR:

```bash
# 1. ruff clean against the entire monorepo
uv run ruff check .
echo "ruff exit: $?"

# 2. ruff format check clean
uv run ruff format --check .
echo "ruff-format exit: $?"

# 3. mypy strict clean for aegis_core + aegis_judges
uv run mypy packages/aegis_core/src packages/aegis_judges/src
echo "mypy strict exit: $?"

# 4. mypy non-strict clean for the rest
uv run mypy packages/aegis_mw/src packages/aegis_mcp/src eval/src
echo "mypy non-strict exit: $?"

# 5. Strict-mode actually gates aegis_core: drop an Any-typed function and confirm mypy fails
cat > /tmp/aegis_mypy_probe.py <<'EOF'
from typing import Any
def bad(x: Any) -> Any:
    return x
EOF
mkdir -p packages/aegis_core/src/aegis_core/_probe
cp /tmp/aegis_mypy_probe.py packages/aegis_core/src/aegis_core/_probe/__init__.py
uv run mypy packages/aegis_core/src/aegis_core/_probe
# expect non-zero — strict-mode catches no-any-explicit / no-any-return
echo "mypy probe exit (expected non-zero): $?"
rm -rf packages/aegis_core/src/aegis_core/_probe

# 6. Ruff actually fires: probe with unused import
echo "import os" > /tmp/aegis_ruff_probe.py
uv run ruff check /tmp/aegis_ruff_probe.py
echo "ruff probe exit (expected non-zero): $?"
rm /tmp/aegis_ruff_probe.py

# 7. Line-length is 100, E501 is ignored
uv run python -c "import tomllib; d=tomllib.load(open('.ruff.toml','rb')); assert d['line-length']==100; assert 'E501' in d['lint']['ignore']; assert 'ALL' in d['lint']['select']; print('ruff config ok')"
```

---

## Notes for coding agent

- Per `docs/architecture.md` § "Coding standards" hard rule 3, ruff config must be "line-length 100, all rules enabled except E501 deferred to formatter". Do not loosen the rule selection.
- Per `docs/architecture.md` § "Coding standards" hard rule 2, mypy must be `--strict` for `aegis_core` and `aegis_judges`. Per the same section, non-strict is acceptable for `aegis_mw`, `aegis_mcp`, and the Splunk app (constrained Python).
- Use mypy's `[mypy-aegis_core.*]` and `[mypy-aegis_judges.*]` per-module sections to flip `strict = True`, leaving the global `[mypy]` block non-strict. This is the simplest way to enforce the split without per-file overrides.
- Ruff's `select = ["ALL"]` will pull in `D` (pydocstyle), `ANN` (annotations), `COM` (commas), `ISC` (implicit-string-concat) etc. Per the architecture doc §"Coding standards" soft rules, public functions/classes need docstrings, so `D` rules are fine — but pick ONE docstring style and ignore the others (D203 vs D211, D213 vs D212 are conflicting pairs; per ADR-002 mention of numpy/Google style, ignore D203 and D213). Also ignore `COM812` and `ISC001` because ruff's own formatter conflicts with them.
- For test files, add `per-file-ignores` for `**/tests/**/*.py = ["D", "ANN", "S101", "PLR2004"]` — test files don't need docstrings on every function, and `assert` (S101) + magic numbers (PLR2004) are tester staples.
- DO NOT use `Any` in `aegis_core` or `aegis_judges` — this is a banned pattern per `docs/architecture.md` § "Banned patterns". The mypy-strict probe in the shell verification is there to enforce it.
- Per `docs/architecture.md` § "Banned patterns", `# type: ignore` requires an inline justification. Don't add any in the skeleton.
- If the project later adds runtime code, ruff/mypy must STAY clean. Keep this story's config aggressive — relaxing later is easy; tightening later is impossible.
