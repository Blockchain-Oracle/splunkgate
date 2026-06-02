# Story — 400-LOC check script + pre-commit wiring

**ID:** story-skel-04-loc-check-script-and-pre-commit
**Epic:** EPIC-02 — Repo skeleton + coding standards
**Depends on:** story-skel-02-ruff-mypy-config, story-cicd-04-pre-commit-hooks
**Estimate:** ~2h
**Status:** PENDING

---

## User story

**As a** coding agent about to commit
**I want to** have a `.pre-commit-hooks/check_loc.py` script wired into `.pre-commit-config.yaml` that rejects any Python source file > 400 LOC (excluding blank lines and pure-comment lines)
**So that** the hard rule from `docs/architecture.md` § "Coding standards" is enforced locally before push, mirroring the CI gate from story-cicd-03 — and any deliberately oversized file fails the hook with a clear "split this" message

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `.pre-commit-hooks/check_loc.py` — NEW — Python script: walks staged files, counts non-blank-non-comment lines per `.py` file, exits 1 with a clear error message if any file > 400 LOC. Single file, ≤ 150 LOC.
- `.pre-commit-hooks/__init__.py` — NEW — empty package marker so the script is importable from tests
- `.pre-commit-config.yaml` — UPDATE — add a `repo: local` block with a `check-loc-400` hook that calls `.pre-commit-hooks/check_loc.py` and is wired to run on `files: \.py$` (preserving existing ruff/mypy/yaml-lint entries from story-cicd-04)
- `tests/test_check_loc.py` — NEW — pytest module with at least 5 cases: (1) accepts a 399-LOC file, (2) accepts a file padded with 1000 blank lines bringing real LOC to 200, (3) accepts a file padded with 1000 comment-only lines, (4) rejects a 401-LOC file with non-zero exit, (5) reject-message includes the offending filename and LOC count
- `tests/__init__.py` — NEW — empty package marker

The coding agent must NOT modify files outside this map without re-checking CLAUDE.md.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given .pre-commit-hooks/check_loc.py exists and is executable
When  `test -x .pre-commit-hooks/check_loc.py` runs
Then  exit code is 0

Given a Python file with 399 lines of real code is created at /tmp/aegis_loc_ok.py
When  `uv run .pre-commit-hooks/check_loc.py /tmp/aegis_loc_ok.py` runs
Then  exit code is 0

Given a Python file with 200 lines of real code + 1000 blank lines is created at /tmp/aegis_loc_blanks.py
When  `uv run .pre-commit-hooks/check_loc.py /tmp/aegis_loc_blanks.py` runs
Then  exit code is 0

Given a Python file with 200 lines of real code + 1000 pure-comment lines is created at /tmp/aegis_loc_comments.py
When  `uv run .pre-commit-hooks/check_loc.py /tmp/aegis_loc_comments.py` runs
Then  exit code is 0

Given a Python file with 401 lines of real code is created at /tmp/aegis_loc_bad.py
When  `uv run .pre-commit-hooks/check_loc.py /tmp/aegis_loc_bad.py` runs
Then  exit code is non-zero
And   stderr (or stdout) contains the literal "/tmp/aegis_loc_bad.py"
And   stderr (or stdout) contains "401"

Given the pre-commit config has been updated
When  `grep -c 'check-loc-400' .pre-commit-config.yaml` runs
Then  stdout is ≥ "1"
And   `grep -c 'check_loc.py' .pre-commit-config.yaml` outputs ≥ "1"

Given a 401-LOC file is staged
When  `pre-commit run check-loc-400 --files /tmp/aegis_loc_bad.py` runs
Then  exit code is non-zero

Given the test suite for the hook
When  `uv run pytest tests/test_check_loc.py -q` runs
Then  exit code is 0
And   stdout contains "5 passed" (or more)

Given the hook script itself
When  `wc -l .pre-commit-hooks/check_loc.py | awk '{print $1}'` runs
Then  stdout is ≤ "150"
```

Every criterion must be checkable by running a command. Prose-only criteria = blocked.

---

## Shell verification

The coding agent runs this to confirm the story is done before opening a PR:

```bash
# 1. Hook script present + executable
test -x .pre-commit-hooks/check_loc.py && echo "hook executable"

# 2. Hook script itself stays under its own limit
SELF_LOC=$(wc -l < .pre-commit-hooks/check_loc.py | tr -d ' ')
test "$SELF_LOC" -le 150 && echo "hook self-LOC ok: $SELF_LOC"

# 3. Accepts a 399-LOC file
uv run python -c "open('/tmp/aegis_loc_ok.py','w').write('x = 1\n'*399)"
uv run .pre-commit-hooks/check_loc.py /tmp/aegis_loc_ok.py
echo "399-LOC accept exit: $?"

# 4. Accepts a file with lots of blanks
uv run python -c "open('/tmp/aegis_loc_blanks.py','w').write(('x = 1\n'*200) + ('\n'*1000))"
uv run .pre-commit-hooks/check_loc.py /tmp/aegis_loc_blanks.py
echo "blanks accept exit: $?"

# 5. Accepts a file with lots of comments
uv run python -c "open('/tmp/aegis_loc_comments.py','w').write(('x = 1\n'*200) + ('# comment\n'*1000))"
uv run .pre-commit-hooks/check_loc.py /tmp/aegis_loc_comments.py
echo "comments accept exit: $?"

# 6. Rejects a deliberately-too-big file
uv run python -c "open('/tmp/aegis_loc_bad.py','w').write('x = 1\n'*401)"
uv run .pre-commit-hooks/check_loc.py /tmp/aegis_loc_bad.py
RC=$?
test "$RC" -ne 0 && echo "401-LOC reject exit (expected non-zero): $RC"

# 7. Reject message names the file + the LOC count
uv run .pre-commit-hooks/check_loc.py /tmp/aegis_loc_bad.py 2>&1 | grep -E '/tmp/aegis_loc_bad\.py.*401|401.*/tmp/aegis_loc_bad\.py'

# 8. pre-commit config wired
grep -c 'check-loc-400' .pre-commit-config.yaml
grep -c 'check_loc.py' .pre-commit-config.yaml

# 9. Real pre-commit invocation reproduces the reject
pre-commit run check-loc-400 --files /tmp/aegis_loc_bad.py
RC=$?
test "$RC" -ne 0 && echo "pre-commit reject exit (expected non-zero): $RC"

# 10. Hook unit tests pass
uv run pytest tests/test_check_loc.py -q

# Cleanup
rm -f /tmp/aegis_loc_ok.py /tmp/aegis_loc_blanks.py /tmp/aegis_loc_comments.py /tmp/aegis_loc_bad.py
```

---

## Notes for coding agent

- Per `docs/architecture.md` § "Coding standards" hard rule 1: "Every source file ≤ 400 LOC (excluding blank lines + pure comments). Enforced by `.pre-commit-hooks/check_loc.py` and by CI fail-on-exceed." This story builds the local-pre-commit half; CI half belongs to story-cicd-03 (already merged before this story per `depends_on`).
- Per `docs/architecture.md` § "Coding standards" hard rule 1: "If a file approaches 400 LOC, split it via composition or extraction. No exceptions." The hook's reject message should say so explicitly — e.g., `error: <file> has 401 LOC (limit 400). Split via composition or extraction.`
- Per `docs/architecture.md` ADR-009: "Two layers — local pre-commit catches before push; CI catches if pre-commit is bypassed. Failure message points the contributor to the file + line count + suggested split." Match this exact failure-message shape.
- LOC counting algorithm: a line counts if, after `lstrip()`, it is non-empty AND does not start with `#`. Inline comments (e.g., `x = 1  # comment`) DO count as real code. Multi-line string literals count as real code (don't try to parse-out docstrings — too error-prone and inconsistent with what humans read).
- Pre-commit `repo: local` syntax (verify via `mcp__context7__resolve-library-id` for `pre-commit` then `mcp__context7__query-docs` if unsure):
  ```yaml
  - repo: local
    hooks:
      - id: check-loc-400
        name: Reject Python files > 400 LOC
        entry: .pre-commit-hooks/check_loc.py
        language: system
        types: [python]
        pass_filenames: true
  ```
- The hook script must be `chmod +x` so `entry:` can execute it directly. Add a shebang `#!/usr/bin/env python3`.
- The hook script must handle multiple file paths passed as argv (pre-commit batches files). Iterate, accumulate violations, print all violations, exit 1 if any.
- Do NOT exclude generated files in the hook itself — the `types: [python]` filter at the pre-commit layer already skips non-Python files. If specific paths (e.g., migrations) need exemption later, add them via the `exclude:` regex in `.pre-commit-config.yaml`, not via logic in the hook.
- Per `docs/architecture.md` § "Banned patterns", do not use `print()` for logs — but the hook's reject MESSAGE to stderr/stdout is a CLI tool output, not a log, so `print(..., file=sys.stderr)` is correct here. Do NOT pull in `structlog` for this script — it's an unnecessary dep for a 100-LOC hook.
- Per `docs/architecture.md` § "Banned patterns", do not use `try/except: pass`. If `open(...)` fails for a path (unreadable / missing), let the exception propagate — pre-commit will surface it; that is the correct UX.
- The unit tests in `tests/test_check_loc.py` should import the script as a module. Because `__init__.py` is in `.pre-commit-hooks/`, you can use `import importlib.util` to load it by file path, OR you can refactor the hook to expose a `count_loc(path: Path) -> int` function callable from both the CLI entrypoint and the tests.
