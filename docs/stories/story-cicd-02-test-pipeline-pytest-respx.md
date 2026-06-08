# Story — CI test pipeline: pytest matrix per package with respx + hypothesis + codecov

**ID:** story-cicd-02-test-pipeline-pytest-respx
**Epic:** EPIC-01 — CI/CD foundation
**Depends on:** story-skel-01-uv-workspace-pyproject, story-cicd-01-build-pipeline-python-wheels
**Estimate:** ~1.5h
**Status:** PENDING

---

## User story

**As a** coding agent landing a story that adds behavioral tests
**I want to** push a commit and see a green `test` matrix job in GitHub Actions with coverage reported to Codecov for `splunkgate_core` + `splunkgate_judges`
**So that** I know my tests actually ran in CI, mocking via `respx` works for `httpx`, async tests work via `pytest-asyncio`, property-based tests work via `hypothesis`, and the >=70% coverage gate cannot regress silently

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `.github/workflows/ci.yml` — UPDATE — append the `test` job (matrix over `[splunkgate_core, splunkgate_judges, splunkgate_mw, splunkgate_mcp]`) and the `eval-smoke` job stub (full eval-smoke wiring is owned by cicd-06; here we add the `needs: [test]` plumbing). Copy verbatim from `docs/cicd-spec.md` § "Concrete YAML skeleton" lines 103-119 for the `test` job. `test` `needs: [lint, typecheck]`.
- `pyproject.toml` — UPDATE — add `[dependency-groups]` table with a `dev` group listing `pytest`, `pytest-asyncio`, `pytest-cov`, `hypothesis`, `respx` (versions resolved by uv). `[tool.pytest.ini_options]` sets `asyncio_mode = "auto"` so async tests don't need explicit decoration.
- `packages/splunkgate_core/tests/__init__.py` — NEW — empty file (Python package marker)
- `packages/splunkgate_core/tests/test_smoke.py` — NEW — single test `def test_version_present(): import splunkgate_core; assert splunkgate_core.__version__ == "0.0.0"` so the matrix run for `splunkgate_core` actually executes one test case (proves wiring)
- `packages/splunkgate_judges/tests/__init__.py` — NEW — empty
- `packages/splunkgate_judges/tests/test_smoke.py` — NEW — single smoke test asserting the package import succeeds
- `packages/splunkgate_mw/tests/__init__.py` — NEW — empty
- `packages/splunkgate_mw/tests/test_smoke.py` — NEW — single smoke test
- `packages/splunkgate_mcp/tests/__init__.py` — NEW — empty
- `packages/splunkgate_mcp/tests/test_smoke.py` — NEW — single smoke test
- `codecov.yml` — NEW — set `coverage.status.project.default.target: 70%` and `flags: [splunkgate_core, splunkgate_judges]` per `docs/cicd-spec.md` § "Required green checks before merge"

The coding agent must NOT modify files outside this map without re-checking CLAUDE.md.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given `uv sync --all-packages --frozen` has succeeded
When  `uv run pytest packages/splunkgate_core --cov=splunkgate_core --cov-report=xml --cov-fail-under=70` runs
Then  exit code is 0
And   `coverage.xml` exists in the working directory

Given `uv run pytest packages/splunkgate_judges` runs
When  the run completes
Then  exit code is 0
And   stdout contains `1 passed` (one smoke test)

Given `uv run pytest packages/splunkgate_mw packages/splunkgate_mcp` runs
When  the run completes
Then  exit code is 0
And   stdout contains `2 passed` (one smoke per package)

Given the `test` matrix job runs on GitHub Actions
When  the workflow completes
Then  exactly 4 matrix runners executed (one per package)
And   the codecov upload step only fires for `splunkgate_core` and `splunkgate_judges` matrix entries (verified via `if: ${{ matrix.package == 'splunkgate_core' || matrix.package == 'splunkgate_judges' }}`)

Given `grep -c "asyncio_mode" pyproject.toml` runs
When  the output is checked
Then  it equals `1` (auto mode wired)

Given `grep -E "(pytest-asyncio|respx|hypothesis)" pyproject.toml | wc -l` runs
When  the output is checked
Then  it is >= 3 (all three test deps declared)

Given a deliberately failing assertion is added to any smoke test
When  pytest runs
Then  the matrix job for that package exits non-zero and the `test` job overall fails
```

---

## Shell verification

The coding agent runs this end-to-end locally before opening a PR:

```bash
set -euo pipefail

# 1. All dev deps resolvable + locked
uv sync --all-packages --frozen
uv pip list | grep -E "(pytest-asyncio|respx|hypothesis|pytest-cov)" | wc -l | grep -q 4

# 2. Each package's tests pass
for pkg in splunkgate_core splunkgate_judges splunkgate_mw splunkgate_mcp; do
  uv run pytest "packages/${pkg}" --tb=short -q
done

# 3. Coverage XML generated for the codecov-uploaded packages
uv run pytest packages/splunkgate_core --cov=splunkgate_core --cov-report=xml --cov-fail-under=70
test -s coverage.xml
uv run pytest packages/splunkgate_judges --cov=splunkgate_judges --cov-report=xml --cov-fail-under=70
test -s coverage.xml

# 4. CI YAML wires the matrix correctly
grep -q 'matrix:' .github/workflows/ci.yml
grep -q 'package: \[splunkgate_core, splunkgate_judges, splunkgate_mw, splunkgate_mcp\]' .github/workflows/ci.yml
grep -q 'codecov/codecov-action' .github/workflows/ci.yml
grep -q "matrix.package == 'splunkgate_core' || matrix.package == 'splunkgate_judges'" .github/workflows/ci.yml

# 5. asyncio + respx wiring
grep -q 'asyncio_mode = "auto"' pyproject.toml

# 6. Push and verify GitHub Actions
git push origin HEAD
gh run watch --exit-status
```

All blocks must exit 0.

---

## Notes for coding agent

- Per `docs/architecture.md` § "Soft rules", `respx` is mandatory for HTTP mocking; `unittest.mock` for HTTP is banned. This story imports `respx` only as a dependency declaration; first real `respx` usage lands in EPIC-04 stories (`story-judges-04-ai-defense-mock-respx-fixtures.md`).
- Per `docs/cicd-spec.md` § "Concrete YAML skeleton" line 116, the `--cov-fail-under=70` flag is required. The 70% floor is verbatim from the spec. Do not raise (more friction for EPIC-03 onwards) or lower (gates the eval headline).
- `asyncio_mode = "auto"` matters because `splunkgate_judges` is fully async (httpx async client) — every test that touches the client must be an `async def`. The alternative (`strict` mode) requires `@pytest.mark.asyncio` on every test; `auto` removes the boilerplate.
- Codecov upload is gated by `if: matrix.package == 'splunkgate_core' || matrix.package == 'splunkgate_judges'` because those two packages have `--strict` mypy and are load-bearing; `splunkgate_mw` and `splunkgate_mcp` have non-strict typing per `docs/architecture.md` § "Hard rules" #2 and are slower-moving for coverage tracking.
- The `CODECOV_TOKEN` secret listed in `docs/cicd-spec.md` § "Secrets to configure" is set by Abu manually; this story does not block on the secret being present (Codecov action soft-fails gracefully on missing token for public repos).
- Per `../../../context/02-agent-frameworks/06-splunklib-ai-deep-read.md`, `splunklib.ai` itself uses httpx — keeping respx as our canonical mocker matches the upstream lib's test style.
- The smoke tests in this story are throwaways; EPIC-03 onwards replaces them with real behavioral tests. They exist solely to prove the CI test matrix actually runs commands and the codecov uploader fires for the right packages.
- Hypothesis usage example deferred to EPIC-03 (`story-core-01-verdict-pydantic-types.md` adds property tests for `Verdict.severity` enum round-trips).
