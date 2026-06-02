# Story — 400-LOC cap enforcement: check_loc.sh + loc-cap CI job

**ID:** story-cicd-03-loc-cap-enforcement
**Epic:** EPIC-01 — CI/CD foundation
**Depends on:** story-cicd-01-build-pipeline-python-wheels
**Estimate:** ~1h
**Status:** PENDING

---

## User story

**As a** coding agent who might write a 600-line file in a moment of weakness
**I want to** the CI pipeline + a future pre-commit hook reject any `*.py` file in `packages/`, `eval/`, or `splunk_apps/aegis_app/bin/` exceeding 400 LOC (excluding blank + pure-comment lines)
**So that** the codebase stays in the agent-friendly composition-over-monolith shape Abu's ADR-009 mandates, and `sahil-pr-audit` can rely on file-size as a first-pass complexity signal

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `.github/scripts/check_loc.sh` — NEW — verbatim copy of the bash script in `docs/cicd-spec.md` § "The 400-LOC gate script" lines 191-214. Uses `grep -cvE '^\s*(#|$)'` to count non-blank non-pure-comment lines. Scans `packages/`, `eval/`, `splunk_apps/aegis_app/bin/` for `*.py`. Skips `.venv/` and `__pycache__/`. Threshold constant `THRESHOLD=400`. Exits 1 on any violation; emits `::error file=$f::` annotation per violation so GitHub renders inline in PR diff view.
- `.github/workflows/ci.yml` — UPDATE — append the `loc-cap` job (independent, no `needs:`), copy verbatim from `docs/cicd-spec.md` § "Concrete YAML skeleton" lines 94-101. `runs-on: ubuntu-latest`, `timeout-minutes: 2`.
- `.github/scripts/check_loc.sh` permissions — UPDATE — `chmod +x` (committed via `git update-index --chmod=+x`)
- `tests/fixtures/loc_oversized.py.fixture` — NEW — a deliberately oversized file (425 non-blank-non-comment lines, content is `x = 1\n` repeated) used by the verification script to prove the gate actually rejects oversized files. Stored with `.fixture` extension so it does NOT get scanned by `check_loc.sh` itself (the find command only matches `*.py`).
- `tests/fixtures/loc_at_threshold.py.fixture` — NEW — file with exactly 400 LOC of non-blank-non-comment lines (proves boundary condition: <= 400 passes, > 400 fails)

The coding agent must NOT modify files outside this map without re-checking CLAUDE.md.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given `.github/scripts/check_loc.sh` exists and is executable
When  `bash .github/scripts/check_loc.sh` runs on a clean repo (only placeholder __init__.py files exist from cicd-01)
Then  exit code is 0
And   stdout contains `All files within 400 LOC cap.`

Given `tests/fixtures/loc_oversized.py.fixture` is renamed to `packages/aegis_core/src/aegis_core/_oversized_test.py` for the test
When  `bash .github/scripts/check_loc.sh` runs
Then  exit code is 1
And   stderr or stdout contains `::error file=packages/aegis_core/src/aegis_core/_oversized_test.py::File has 425 LOC (cap: 400)`
And   the file is renamed back to `.fixture` after the test

Given `tests/fixtures/loc_at_threshold.py.fixture` is renamed to `packages/aegis_core/src/aegis_core/_threshold_test.py`
When  `bash .github/scripts/check_loc.sh` runs
Then  exit code is 0 (exactly 400 LOC passes — strict greater-than per spec line 202)
And   the file is renamed back

Given the `loc-cap` job runs on GitHub Actions
When  the workflow completes on a clean PR
Then  the job is green
And   `gh run view --json jobs --jq '.jobs[] | select(.name == "400-LOC cap") | .conclusion'` outputs `success`

Given `grep -c "THRESHOLD=400" .github/scripts/check_loc.sh` runs
When  the output is checked
Then  it equals `1`

Given `grep -c "::error" .github/scripts/check_loc.sh` runs
When  the output is checked
Then  it >= 1 (GitHub annotation format used)

Given `stat -f "%Lp" .github/scripts/check_loc.sh` (macOS) or `stat -c "%a" .github/scripts/check_loc.sh` (Linux)
When  the output is checked
Then  it contains `7` in the user-execute position (file is executable)
```

---

## Shell verification

The coding agent runs this end-to-end locally before opening a PR:

```bash
set -euo pipefail

# 1. Script exists, executable, baseline-clean
test -x .github/scripts/check_loc.sh
bash .github/scripts/check_loc.sh | grep -q "All files within 400 LOC cap."

# 2. Oversized fixture is rejected
cp tests/fixtures/loc_oversized.py.fixture packages/aegis_core/src/aegis_core/_oversized_test.py
if bash .github/scripts/check_loc.sh; then
  echo "FAIL: oversized file slipped past the gate"; exit 1
fi
rm packages/aegis_core/src/aegis_core/_oversized_test.py

# 3. Exactly-400 LOC fixture passes (boundary)
cp tests/fixtures/loc_at_threshold.py.fixture packages/aegis_core/src/aegis_core/_threshold_test.py
bash .github/scripts/check_loc.sh
rm packages/aegis_core/src/aegis_core/_threshold_test.py

# 4. CI YAML wires the job
grep -q 'loc-cap' .github/workflows/ci.yml
grep -q 'bash .github/scripts/check_loc.sh' .github/workflows/ci.yml

# 5. Push and verify the `400-LOC cap` job is green on Actions
git push origin HEAD
gh run watch --exit-status
gh run view --json jobs --jq '.jobs[] | select(.name == "400-LOC cap") | .conclusion' | grep -q success
```

All blocks must exit 0.

---

## Notes for coding agent

- The script is reused VERBATIM by the pre-commit hook in `story-cicd-04-pre-commit-hooks.md`. Do NOT inline the logic in the workflow YAML — both layers must call `.github/scripts/check_loc.sh`. Per ADR-009 (`docs/architecture.md` § "Architecture decisions"), two layers of enforcement is the design.
- `grep -cvE '^\s*(#|$)'` matches Python comment style (`#`) only. Block-comment-style docstrings (triple-quoted at module level) ARE counted as LOC. This is intentional per the spec line 200's "non-blank, non-pure-comment lines" definition; module docstrings still cost LOC. Do not "improve" the regex to exempt docstrings.
- Per `docs/cicd-spec.md` § "Failure mode handling" line 495, there is NO `# noqa: loc-cap` escape hatch. The error message instructs `split it via composition or extraction`. Do not add a bypass mechanism even if a future story requests it.
- The `.fixture` extension trick avoids the chicken-and-egg problem (test fixtures themselves would otherwise trip the cap). The `find` command in the script matches `-name '*.py'` only, so `.fixture` files are invisible.
- Verify with `wc -l tests/fixtures/loc_oversized.py.fixture` that the fixture contains EXACTLY 425 non-blank non-comment lines. Use `python -c "print('x = 1\\n' * 425, end='')" > tests/fixtures/loc_oversized.py.fixture`.
- Per `../../../context/11-prior-art/01-build-a-thon-2025-deep-read.md`, the DNS Guard winner did not enforce a LOC cap publicly, but their python files trend <300 LOC; we adopt the explicit cap as a differentiator for agent-driven development.
- The `loc-cap` job is independent (no `needs:`) so it runs in parallel with lint/typecheck and provides fast feedback. Its 2-minute timeout is generous; typical runtime is <10 seconds.
- The script must be POSIX-compliant bash (no zsh-isms); `set -euo pipefail` is mandatory.
- The find command's `-print0` + `read -d ''` pattern handles filenames with spaces — preserve this even though Python conventions forbid spaces in module names (defensive).
