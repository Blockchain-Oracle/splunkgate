# Story — Pre-commit hooks: ruff + mypy + check_loc + no-print + gitleaks

**ID:** story-cicd-04-pre-commit-hooks
**Epic:** EPIC-01 — CI/CD foundation
**Depends on:** story-cicd-03-loc-cap-enforcement
**Estimate:** ~1h
**Status:** PENDING

---

## User story

**As a** coding agent committing on my local machine before pushing
**I want to** `git commit` to refuse my commit if I broke ruff lint, mypy --strict on the load-bearing packages, the 400-LOC cap, leaked a credential, or used `print()` in production code paths
**So that** I find out about violations on my laptop in <10s instead of after a 5-minute CI round-trip, and `sahil-pr-audit` never sees a PR with `print()`, secrets, or LOC overruns

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `.pre-commit-config.yaml` — NEW — verbatim copy of `docs/cicd-spec.md` § "Pre-commit hooks" lines 406-442. Five hook groups: (1) astral-sh/ruff-pre-commit `v0.7.0` for `ruff --fix` + `ruff-format`; (2) pre-commit/mirrors-mypy `v1.13.0` strict-mode on `packages/(aegis_core|aegis_judges)/src/`; (3) local hook `check-loc` calling `bash .github/scripts/check_loc.sh`; (4) local hook `no-print` rejecting `print(` in `packages/aegis_*/src/` except `*_mock.py` / test files / lines mentioning `structlog`; (5) gitleaks/gitleaks `v8.21.2`.
- `docs/ops/pre-commit-install.md` — NEW — short doc (~30 lines) with the install command (`uv run pre-commit install`) and the bypass policy (no `--no-verify` in normal flow; emergency-only with PR description justification).
- `README.md` — UPDATE — append a `### Local development setup` section (~10 lines) with the `uv sync` + `uv run pre-commit install` two-step. If README does not yet exist (it's owned by EPIC-11), create a stub with only this section and a TODO header.
- `tests/fixtures/pre_commit_violators/has_print.py.fixture` — NEW — single-line file `print("hello")` used by verification to prove the no-print hook fires
- `tests/fixtures/pre_commit_violators/has_secret.py.fixture` — NEW — file containing a synthetic AWS-key-shaped string (e.g., `AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"` — the well-known AWS docs example string is gitleaks-allowlisted by default; use a more realistic random 20-char `AKIA[0-9A-Z]{16}` to actually trigger gitleaks)

The coding agent must NOT modify files outside this map without re-checking CLAUDE.md.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given the repo has the file `.pre-commit-config.yaml` committed
When  `uv run pre-commit install` runs
Then  exit code is 0
And   `.git/hooks/pre-commit` exists and is executable

Given pre-commit is installed and `uv sync --all-packages --frozen` has succeeded
When  `uv run pre-commit run --all-files` runs on a clean repo
Then  exit code is 0
And   stdout contains the strings `ruff`, `ruff-format`, `mypy`, `400-LOC cap`, `No print() in production`, `gitleaks` (one per registered hook)

Given the no-print fixture `tests/fixtures/pre_commit_violators/has_print.py.fixture` is copied to `packages/aegis_judges/src/aegis_judges/_violator.py`
When  `uv run pre-commit run no-print --all-files` runs
Then  exit code is non-zero
And   stdout contains `Use structlog, not print()`
And   after deleting the violator file, `uv run pre-commit run no-print --all-files` exits 0

Given the 400-LOC oversized fixture is copied into `packages/aegis_core/src/aegis_core/_oversized.py` (re-use the fixture from cicd-03)
When  `uv run pre-commit run check-loc --all-files` runs
Then  exit code is non-zero
And   stdout contains `400 LOC` somewhere

Given the gitleaks fixture file (containing a realistic-shaped AWS key) is staged
When  `uv run pre-commit run gitleaks` runs
Then  exit code is non-zero

Given `grep -c "id: check-loc" .pre-commit-config.yaml` runs
When  the output is checked
Then  it equals `1`

Given `grep -c "id: no-print" .pre-commit-config.yaml` runs
When  the output is checked
Then  it equals `1`

Given `grep -c "ruff-pre-commit" .pre-commit-config.yaml` runs
When  the output is checked
Then  it equals `1`

Given `grep -c "mirrors-mypy" .pre-commit-config.yaml` runs
When  the output is checked
Then  it equals `1`

Given `grep -c "gitleaks/gitleaks" .pre-commit-config.yaml` runs
When  the output is checked
Then  it equals `1`
```

---

## Shell verification

The coding agent runs this end-to-end locally before opening a PR:

```bash
set -euo pipefail

# 1. Install hooks
uv run pre-commit install
test -x .git/hooks/pre-commit

# 2. Clean repo passes all hooks
uv run pre-commit run --all-files

# 3. no-print hook fires on a violator file
cp tests/fixtures/pre_commit_violators/has_print.py.fixture packages/aegis_judges/src/aegis_judges/_violator.py
if uv run pre-commit run no-print --all-files; then
  echo "FAIL: no-print hook didn't fire"; rm packages/aegis_judges/src/aegis_judges/_violator.py; exit 1
fi
rm packages/aegis_judges/src/aegis_judges/_violator.py

# 4. check-loc hook fires on an oversized file
cp tests/fixtures/loc_oversized.py.fixture packages/aegis_core/src/aegis_core/_oversized.py
if uv run pre-commit run check-loc --all-files; then
  echo "FAIL: check-loc hook didn't fire"; rm packages/aegis_core/src/aegis_core/_oversized.py; exit 1
fi
rm packages/aegis_core/src/aegis_core/_oversized.py

# 5. gitleaks fires on a realistic-shaped secret
cp tests/fixtures/pre_commit_violators/has_secret.py.fixture packages/aegis_core/src/aegis_core/_secret.py
git add packages/aegis_core/src/aegis_core/_secret.py
if uv run pre-commit run gitleaks; then
  echo "FAIL: gitleaks didn't catch the secret-shaped string"
  git restore --staged packages/aegis_core/src/aegis_core/_secret.py
  rm packages/aegis_core/src/aegis_core/_secret.py
  exit 1
fi
git restore --staged packages/aegis_core/src/aegis_core/_secret.py
rm packages/aegis_core/src/aegis_core/_secret.py

# 6. README has the dev-setup section
grep -q '### Local development setup' README.md
grep -q 'uv run pre-commit install' README.md
```

All blocks must exit 0.

---

## Notes for coding agent

- The `no-print` hook's bash regex (`docs/cicd-spec.md` line 434) is intentionally loose: `grep -rn "print(" packages/aegis_*/src/ --include="*.py" | grep -v "structlog\|test\|_mock\.py"`. It allows `structlog` in the same line (some bridge code logs via a `print`-like API but with structlog underneath) and exempts mock files and tests. Per `docs/architecture.md` § "Hard rules" #5, mock files are §14 carve-outs.
- The hook pins are exact versions (`ruff: v0.7.0`, `mypy: v1.13.0`, `gitleaks: v8.21.2`) — DO NOT use `latest`. Renovate/dependabot updates these via PR. This protects against silent rule changes mid-build.
- `mypy` hook `additional_dependencies: [pydantic, httpx, structlog]` is required because pre-commit runs mypy in an isolated env without the project's deps. The list mirrors the load-bearing runtime libs of `aegis_core` + `aegis_judges` per `docs/architecture.md` § "Required external libraries".
- The gitleaks fixture must use a key SHAPE that gitleaks v8.21.2's default ruleset detects (test with `gitleaks detect --no-git -v -s tests/fixtures/pre_commit_violators/`). The well-known AWS docs example `AKIAIOSFODNN7EXAMPLE` is allowlisted in gitleaks itself per their official ruleset; use `AKIA` + a fresh random 16-char `[A-Z0-9]` string in the fixture. The fixture file's first line should be a `# Synthetic secret for gitleaks fixture, not a real credential` comment to make intent obvious to human reviewers.
- Per `docs/cicd-spec.md` § "Failure mode handling" line 496, gitleaks failure means the secret must be rotated AND history rewritten with `git-filter-repo`. Do NOT add this story's fixture as a gitleaks allowlist entry — that would defeat the test. Instead, the verification script stages the fixture, runs gitleaks, then unstages and deletes the file (it never reaches git history).
- Per `docs/cicd-spec.md` § "Pre-commit hooks" line 425, `check-loc` and `no-print` are `language: system` local hooks (not pulled from a remote repo). They call the script written in cicd-03 (`.github/scripts/check_loc.sh`) and an inline bash command for `no-print`.
- The README stub for `Local development setup` is intentional even though EPIC-11 (`story-readme-01-headline-and-banner-and-credits.md`) owns the full README. Cross-flag in the PR description so the EPIC-11 author knows the section already exists and merges it into the full README rather than overwriting it.
- Per `../../../context/11-prior-art/01-build-a-thon-2025-deep-read.md`, no 2025 winner published a pre-commit config; documenting one signals build hygiene to Splunk-staff judges.
