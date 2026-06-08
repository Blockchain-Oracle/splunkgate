# Story — 400-LOC check script + pre-commit wiring

**ID:** story-skel-04-loc-check-script-and-pre-commit
**Epic:** EPIC-02 — Repo skeleton + coding standards
**Depends on:** story-skel-02-ruff-mypy-config, story-cicd-04-pre-commit-hooks
**Estimate:** ~1h (scope reduced per audit synthesis Block C — see Notes)
**Status:** PENDING

---

## User story

**As a** coding agent about to commit
**I want to** have the canonical `.github/scripts/check_loc.py` (shipped by cicd-03) wired into `.pre-commit-config.yaml` (the file shipped by cicd-04) so `git commit` rejects any Python source file > 400 LOC (excluding blank lines and pure-comment lines)
**So that** the hard rule from `docs/architecture.md` § "Coding standards" is enforced locally before push, mirroring the CI gate from story-cicd-03 — and any deliberately oversized file fails the hook with a clear "split this" message

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `.pre-commit-config.yaml` — UPDATE — **scope reduced per audit synthesis Block C**. story-cicd-04 is the SOLE NEW owner of this file AND of the `check-loc-400` hook (which calls `.github/scripts/check_loc.py` from story-cicd-03). This story does NOT add a `check-loc-400` hook (already present from cicd-04). Instead, this story VERIFIES that `pre-commit install` works against the file shipped by cicd-04, and optionally appends minor language-specific hooks (e.g., a yaml-lint hook for `*.yml`/`*.yaml` files) if they were not in cicd-04. The `.pre-commit-hooks/check_loc.py` duplicate script is REMOVED from this story's scope — `.github/scripts/check_loc.py` (cicd-03's Python script) is the single canonical loc-cap script reused by both the CI gate AND the pre-commit hook.
- `tests/test_pre_commit_install.py` — NEW — pytest module with at least 3 cases verifying: (1) `pre-commit install` exits 0 against the cicd-04-shipped config; (2) `pre-commit run --all-files` on a clean repo exits 0; (3) the `check-loc-400` hook id is registered (greppable from `.pre-commit-config.yaml`).
- `tests/__init__.py` — NEW — empty package marker (if not already present from another story)

The coding agent must NOT modify files outside this map without re-checking CLAUDE.md.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given .pre-commit-config.yaml exists (shipped NEW by story-cicd-04)
When  `test -f .pre-commit-config.yaml` runs
Then  exit code is 0

Given the canonical loc-cap script lives at .github/scripts/check_loc.py (shipped by story-cicd-03)
When  `test -x .github/scripts/check_loc.py` runs
Then  exit code is 0

Given pre-commit hook install
When  `uv run pre-commit install` runs
Then  exit code is 0
And   `.git/hooks/pre-commit` exists and is executable

Given the canonical check-loc-400 hook id is registered (by cicd-04)
When  `grep -c 'check-loc-400' .pre-commit-config.yaml` runs
Then  stdout is ≥ "1"

Given the canonical check-loc-400 hook calls the .py script from cicd-03
When  `grep -c '.github/scripts/check_loc.py' .pre-commit-config.yaml` runs
Then  stdout is ≥ "1"

Given a 401-LOC file is staged at /tmp/splunkgate_loc_bad.py
When  `pre-commit run check-loc-400 --files /tmp/splunkgate_loc_bad.py` runs
Then  exit code is non-zero

Given the test suite for pre-commit install verification
When  `uv run pytest tests/test_pre_commit_install.py -q` runs
Then  exit code is 0
And   stdout contains "3 passed" (or more)
```

Every criterion must be checkable by running a command. Prose-only criteria = blocked.

---

## Shell verification

The coding agent runs this to confirm the story is done before opening a PR:

```bash
# 1. Canonical loc-cap script present (owned by cicd-03)
test -x .github/scripts/check_loc.py && echo "canonical script present"

# 2. .pre-commit-config.yaml present (owned by cicd-04)
test -f .pre-commit-config.yaml && echo "config present"

# 3. pre-commit install works
uv run pre-commit install
test -x .git/hooks/pre-commit && echo "pre-commit installed"

# 4. canonical hook wired
grep -c 'check-loc-400' .pre-commit-config.yaml
grep -c '.github/scripts/check_loc.py' .pre-commit-config.yaml

# 5. Real pre-commit invocation rejects an oversized file
uv run python -c "open('/tmp/splunkgate_loc_bad.py','w').write('x = 1\n'*401)"
pre-commit run check-loc-400 --files /tmp/splunkgate_loc_bad.py
RC=$?
test "$RC" -ne 0 && echo "pre-commit reject exit (expected non-zero): $RC"
rm -f /tmp/splunkgate_loc_bad.py

# 6. Pre-commit install verification tests pass
uv run pytest tests/test_pre_commit_install.py -q
```

---

## Notes for coding agent

- **SCOPE REDUCED — audit synthesis Block C consolidation.** Per the Block C ownership table, story-cicd-04 owns `.pre-commit-config.yaml` NEW (sole owner) including the canonical `check-loc-400` hook id, and story-cicd-03 owns the canonical `.github/scripts/check_loc.py` Python script (single source of truth, called from both the CI gate AND the pre-commit hook). This story used to duplicate the check_loc script at `.pre-commit-hooks/check_loc.py` and re-define the hook — that's the duplication the audit kills. This story now ONLY verifies install + extends with minor language hooks (yaml-lint, etc.) if they were not already added by cicd-04. Do NOT create a duplicate check_loc.py.
- Per `docs/architecture.md` § "Coding standards" hard rule 1: "Every source file ≤ 400 LOC (excluding blank lines + pure comments). Enforced by `.github/scripts/check_loc.py` (the canonical Python script) and by CI fail-on-exceed." Pre-commit + CI both invoke this same script per ADR-009.
- Per `docs/architecture.md` § "Coding standards" hard rule 1: "If a file approaches 400 LOC, split it via composition or extraction. No exceptions." The hook's reject message should say so explicitly — e.g., `error: <file> has 401 LOC (limit 400). Split via composition or extraction.`
- Per `docs/architecture.md` ADR-009: "Two layers — local pre-commit catches before push; CI catches if pre-commit is bypassed. Failure message points the contributor to the file + line count + suggested split." Match this exact failure-message shape.
- LOC counting algorithm: a line counts if, after `lstrip()`, it is non-empty AND does not start with `#`. Inline comments (e.g., `x = 1  # comment`) DO count as real code. Multi-line string literals count as real code (don't try to parse-out docstrings — too error-prone and inconsistent with what humans read).
- Pre-commit `repo: local` syntax for the canonical check-loc-400 hook (defined in cicd-04 — informational here):
  ```yaml
  - repo: local
    hooks:
      - id: check-loc-400
        name: Reject Python files > 400 LOC
        entry: .github/scripts/check_loc.py
        language: system
        types: [python]
        pass_filenames: true
  ```
- The canonical script is `.github/scripts/check_loc.py` (cicd-03). Per ADR-009 + audit synthesis Block C, there is exactly one loc-cap script in the repo. This story does NOT add a duplicate.
- Per `docs/architecture.md` § "Banned patterns", do not use `print()` for logs — but the hook's reject MESSAGE to stderr/stdout is a CLI tool output, not a log, so `print(..., file=sys.stderr)` is correct here. Do NOT pull in `structlog` for this script — it's an unnecessary dep for a 100-LOC hook.
- Per `docs/architecture.md` § "Banned patterns", do not use `try/except: pass`. If `open(...)` fails for a path (unreadable / missing), let the exception propagate — pre-commit will surface it; that is the correct UX.
- The unit tests in `tests/test_check_loc.py` should import the script as a module. Because `__init__.py` is in `.pre-commit-hooks/`, you can use `import importlib.util` to load it by file path, OR you can refactor the hook to expose a `count_loc(path: Path) -> int` function callable from both the CLI entrypoint and the tests.
