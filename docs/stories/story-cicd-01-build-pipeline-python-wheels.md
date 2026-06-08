# Story — CI build pipeline: per-package Python wheels via uv workspace

**ID:** story-cicd-01-build-pipeline-python-wheels
**Epic:** EPIC-01 — CI/CD foundation
**Depends on:** story-skel-01-uv-workspace-pyproject (workspace skeleton must exist before CI can build it)
**Estimate:** ~1.5h
**Status:** PENDING

---

## User story

**As a** coding agent picking up any downstream story
**I want to** push a commit and see a green `build-wheels` matrix job in GitHub Actions that produces a wheel artifact per package
**So that** every subsequent epic can assume the monorepo builds and ships installable artifacts before I touch a line of code

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `.github/workflows/ci.yml` — NEW — defines the `CI` workflow with `lint`, `typecheck`, `build-wheels` (matrix over the 4 packages), and `build-app` jobs; pinned `PYTHON_VERSION: "3.13"` and `UV_VERSION: "latest"`; `concurrency.group: ci-${{ github.ref }}` with `cancel-in-progress: true`; copy the YAML skeleton verbatim from `docs/cicd-spec.md` § "Concrete YAML skeleton" lines 49-187 (this story owns only `lint`, `typecheck`, `build-wheels`, `build-app`; other jobs land in cicd-02..08)
- `pyproject.toml` — PRECONDITION (owned NEW by story-skel-01) — uv workspace root must exist; this job READS it, does not create it. If absent, CI cannot resolve packages.
- `.python-version` — PRECONDITION (owned NEW by story-skel-01) — Python pin must exist
- `packages/splunkgate_core/pyproject.toml` — PRECONDITION (owned NEW by story-skel-01)
- `packages/splunkgate_judges/pyproject.toml` — PRECONDITION (owned NEW by story-skel-01)
- `packages/splunkgate_mw/pyproject.toml` — PRECONDITION (owned NEW by story-skel-01)
- `packages/splunkgate_mcp/pyproject.toml` — PRECONDITION (owned NEW by story-skel-01)
- `packages/splunkgate_core/src/splunkgate_core/__init__.py` — PRECONDITION (owned NEW by story-skel-01)
- `packages/splunkgate_judges/src/splunkgate_judges/__init__.py` — PRECONDITION (owned NEW by story-skel-01)
- `packages/splunkgate_mw/src/splunkgate_mw/__init__.py` — PRECONDITION (owned NEW by story-skel-01)
- `packages/splunkgate_mcp/src/splunkgate_mcp/__init__.py` — PRECONDITION (owned NEW by story-skel-01)
- `uv.lock` — PRECONDITION (owned NEW by story-skel-01); cicd-01 only confirms the lockfile is present + non-empty as part of the workflow assertions

The coding agent must NOT modify files outside this map without re-checking CLAUDE.md.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given the repo is freshly cloned and `uv` is installed
When  `uv sync --all-packages --frozen` runs from the repo root
Then  exit code is 0
And   `uv.lock` exists and is non-empty

Given `uv sync --all-packages --frozen` has succeeded
When  `uv build --package splunkgate_core --out-dir dist/` runs
Then  exit code is 0
And   `ls dist/splunkgate_core-*.whl | wc -l` outputs `1`

Given `uv build` has succeeded for splunkgate_core
When  the same command runs for splunkgate_judges, splunkgate_mw, splunkgate_mcp
Then  each produces exactly one `.whl` in dist/ (4 wheels total when all four packages build)

Given the `.github/workflows/ci.yml` file is committed and pushed to a branch
When  GitHub Actions runs the CI workflow
Then  the `build-wheels` matrix job spawns exactly 4 runners (one per package)
And   the workflow uploads 4 artifacts named `wheel-splunkgate_core`, `wheel-splunkgate_judges`, `wheel-splunkgate_mw`, `wheel-splunkgate_mcp`

Given the `lint` job runs
When  `uv run ruff check .` executes
Then  exit code is 0 (placeholder __init__.py files trivially pass)

Given the `typecheck` job runs
When  `uv run mypy --strict packages/splunkgate_core packages/splunkgate_judges` executes
Then  exit code is 0 (placeholder __init__.py files trivially pass)

Given `grep -c "matrix:" .github/workflows/ci.yml` runs
When  the output is inspected
Then  count >= 1 (matrix strategy present for build-wheels)

Given `grep "PYTHON_VERSION:" .github/workflows/ci.yml`
When  the output is inspected
Then  the value `"3.13"` appears exactly once
```

---

## Shell verification

The coding agent runs this end-to-end locally to confirm the story is done before opening a PR:

```bash
set -euo pipefail

# 1. uv workspace resolves and locks
uv sync --all-packages --frozen
test -s uv.lock || { echo "uv.lock missing/empty"; exit 1; }

# 2. All four packages build a wheel
rm -rf dist/
for pkg in splunkgate_core splunkgate_judges splunkgate_mw splunkgate_mcp; do
  uv build --package "$pkg" --out-dir dist/
  test "$(ls dist/${pkg}-*.whl 2>/dev/null | wc -l)" -eq 1 || { echo "wheel missing for $pkg"; exit 1; }
done
test "$(ls dist/*.whl | wc -l)" -eq 4

# 3. Lint + strict typecheck pass on placeholder code
uv run ruff check .
uv run ruff format --check .
uv run mypy --strict packages/splunkgate_core packages/splunkgate_judges

# 4. CI YAML structure
test -f .github/workflows/ci.yml
grep -q 'PYTHON_VERSION: "3.13"' .github/workflows/ci.yml
grep -q 'cancel-in-progress: true' .github/workflows/ci.yml
grep -q 'build-wheels' .github/workflows/ci.yml
grep -q 'splunkgate_core' .github/workflows/ci.yml
grep -q 'splunkgate_judges' .github/workflows/ci.yml
grep -q 'splunkgate_mw' .github/workflows/ci.yml
grep -q 'splunkgate_mcp' .github/workflows/ci.yml

# 5. Push to a branch and verify GitHub Actions green
git push origin HEAD
gh run watch --exit-status
```

All five blocks must exit 0 before opening the PR.

---

## Notes for coding agent

- **OWNERSHIP NOTE — file-map flip from audit synthesis Block C.** All uv-workspace artifacts (`pyproject.toml` root, `uv.lock`, `.python-version`, every `packages/splunkgate_*/pyproject.toml`, every `packages/splunkgate_*/src/splunkgate_*/__init__.py`, `eval/pyproject.toml`) are owned NEW by story-skel-01. cicd-01 depends_on skel-01 and assumes those artifacts exist; the only NEW file in this story is `.github/workflows/ci.yml`. The BDD assertions confirm wheels build, but the package shells themselves are skel-01's deliverable.
- Per `../../../context/05-splunk-core/08-app-packaging-and-conf-files.md`, the Splunk app `.tgz` is owned by the `build-app` job in this same workflow; we include it here (vs. cicd-08) because the spec colocates it under `ci.yml`. Story cicd-08 only owns `release.yml`.
- Per `../research/splunk-agentic-ops-2026/13-architecture-recommendation-v2.md`, the monorepo uses uv workspaces (ADR-001, ADR-002 in `docs/architecture.md`). Do not switch to poetry/pdm even if a transitive dep complains.
- Per `docs/architecture.md` § "Stack (locked)", Python 3.13 is hard-pinned because `splunk-sdk-python 3.0.0` requires it. Do not relax to 3.12.
- The four placeholder `__init__.py` files each contain a single `__version__` constant — well under the 400-LOC cap, but flag in PR description that EPIC-03 stories replace these with real domain types.
- Use `hatchling` as the build backend (default for `uv init`); do not introduce `setuptools` or `flit`.
- The `build-app` job (`splunk_apps/splunkgate_app/` → `.tgz`) depends on `appinspect` which lands in story cicd-05; this story's `build-app` step can early-exit if `splunk_apps/splunkgate_app/` does not yet exist (guard with `if [ -d splunk_apps/splunkgate_app ]`). Reaffirm with `sahil-pr-audit` reviewer that this guard is acceptable.
- `concurrency.cancel-in-progress: true` is mandatory per `docs/cicd-spec.md` § "Trigger rules" — force-pushes during agent iteration would otherwise pile up workers and exhaust the GitHub Actions free-tier minute budget.
- `codecov-action` referenced in the spec belongs to story cicd-02 — do not wire it here.
- Verify wheel filenames match PEP 491 naming (`{name}-{version}-{python tag}-{abi tag}-{platform tag}.whl`); `uv build` enforces this automatically.
