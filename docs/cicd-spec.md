# CI/CD Spec — SplunkGate

**Status:** DRAFT
**Last updated:** 2026-06-02
**Anchors EPIC-01.** The first epic the orchestrator dispatches stories for. Nothing else builds until the pipeline is green on `main`.

---

## Why this spec is separate from `architecture.md`

Abu's explicit instruction. CI/CD is the foundation; every subsequent epic depends on it. Carving it out as its own spec makes it easier for the dispatched coding agent to focus + easier for `sahil-pr-audit` to validate that each story added the right workflow file.

---

## Pipeline overview

Four GitHub Actions workflows. Each lives in `.github/workflows/`.

| Workflow | Trigger | Purpose | Required for merge to main |
|---|---|---|---|
| `ci.yml` | push + PR | lint + typecheck + test + loc-cap + appinspect + eval-smoke | YES |
| `eval.yml` | PR (label `eval`) + nightly (cron) | full eval harness against JailbreakBench + AdvBench + custom | NO (informational) |
| `release.yml` | tag push (`v*`) | signed release artifacts (wheels + Splunk app `.tgz`) | NO |
| `security.yml` | push + nightly | pip-audit + gitleaks + trivy (Docker scan) | YES |

---

## `ci.yml` — the main pipeline

### Jobs

1. **`lint`** — ruff check, ruff format --check, markdown-lint on docs/
2. **`typecheck`** — `mypy --strict packages/splunkgate_core packages/splunkgate_judges` + `mypy packages/splunkgate_mw packages/splunkgate_mcp eval`
3. **`loc-cap`** — fail if any `*.py` file exceeds 400 LOC (excluding blank + pure-comment lines)
4. **`test`** — `uv run pytest packages/splunkgate_core packages/splunkgate_judges packages/splunkgate_mw packages/splunkgate_mcp eval`
5. **`appinspect`** — `splunk-appinspect inspect splunk_apps/splunkgate_app/` with zero `error`-severity findings
6. **`eval-smoke`** — fast subset (~20 prompts) of the eval harness; verifies the judgment layer wires end-to-end
7. **`build-wheels`** — `uv build` for each of `splunkgate_core`, `splunkgate_judges`, `splunkgate_mw`, `splunkgate_mcp`
8. **`build-app`** — packages `splunk_apps/splunkgate_app/` into a `.tgz` with hashed name

### Trigger rules

- `on: [push, pull_request]` for all branches
- `paths-ignore: ['docs/**', '*.md', 'LICENSE']` exists but does NOT skip CI for spec changes — we still run `lint` on doc edits (markdown-lint) for consistency
- `concurrency.group: ci-${{ github.ref }}` with `cancel-in-progress: true` so force-pushes don't pile up workers

### Concrete YAML skeleton

```yaml
# .github/workflows/ci.yml
name: CI
on:
  push:
    branches: ['**']
  pull_request:
    branches: ['main']

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

env:
  PYTHON_VERSION: "3.13"
  UV_VERSION: "latest"

jobs:
  lint:
    name: Lint
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with:
          version: ${{ env.UV_VERSION }}
      - run: uv python install ${{ env.PYTHON_VERSION }}
      - run: uv sync --all-packages --frozen
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run python -m mdformat --check docs/

  typecheck:
    name: Typecheck
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv python install ${{ env.PYTHON_VERSION }}
      - run: uv sync --all-packages --frozen
      - run: uv run mypy --strict packages/splunkgate_core packages/splunkgate_judges
      - run: uv run mypy packages/splunkgate_mw packages/splunkgate_mcp eval

  loc-cap:
    name: 400-LOC cap
    runs-on: ubuntu-latest
    timeout-minutes: 2
    steps:
      - uses: actions/checkout@v4
      - run: |
          uv run python .github/scripts/check_loc.py

  test:
    name: Tests
    runs-on: ubuntu-latest
    timeout-minutes: 15
    needs: [lint, typecheck]
    strategy:
      matrix:
        package: [splunkgate_core, splunkgate_judges, splunkgate_mw, splunkgate_mcp]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv python install ${{ env.PYTHON_VERSION }}
      - run: uv sync --all-packages --frozen
      - run: uv run pytest packages/${{ matrix.package }} --cov=src/${{ matrix.package }} --cov-report=xml --cov-fail-under=70
      - uses: codecov/codecov-action@v4
        if: ${{ matrix.package == 'splunkgate_core' || matrix.package == 'splunkgate_judges' }}

  appinspect:
    name: Splunk AppInspect
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv python install ${{ env.PYTHON_VERSION }}
      - run: uv sync --frozen
      - run: uv run splunk-appinspect inspect splunk_apps/splunkgate_app/ --output-file appinspect-report.json --mode test --included-tags cloud --included-tags self-service --included-tags appapproval
      - uses: actions/upload-artifact@v4
        with:
          name: appinspect-report
          path: appinspect-report.json
      - run: |
          if uv run python .github/scripts/parse_appinspect.py appinspect-report.json; then
            echo "AppInspect passed (no error-severity findings)"
          else
            echo "AppInspect found error-severity issues"; exit 1
          fi

  eval-smoke:
    name: Eval smoke (fast subset)
    runs-on: ubuntu-latest
    timeout-minutes: 10
    needs: [test]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv python install ${{ env.PYTHON_VERSION }}
      - run: uv sync --frozen
      - run: SPLUNKGATE_AI_DEFENSE_MOCK=true uv run python eval/scripts/smoke.py

  build-wheels:
    name: Build wheels
    runs-on: ubuntu-latest
    timeout-minutes: 5
    needs: [test, typecheck]
    strategy:
      matrix:
        package: [splunkgate_core, splunkgate_judges, splunkgate_mw, splunkgate_mcp]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv python install ${{ env.PYTHON_VERSION }}
      - run: uv build --package ${{ matrix.package }} --out-dir dist/
      - uses: actions/upload-artifact@v4
        with:
          name: wheel-${{ matrix.package }}
          path: dist/

  build-app:
    name: Build Splunk app .tgz
    runs-on: ubuntu-latest
    timeout-minutes: 5
    needs: [appinspect]
    steps:
      - uses: actions/checkout@v4
      - run: |
          mkdir -p dist/
          tar --exclude='__pycache__' --exclude='*.pyc' --exclude='.appinspect.expect.yaml' \
              -czf dist/splunkgate_app-$(git rev-parse --short HEAD).tgz -C splunk_apps splunkgate_app
          ls -la dist/
      - uses: actions/upload-artifact@v4
        with:
          name: splunk-app-tgz
          path: dist/*.tgz
```

### The 400-LOC gate script

```bash
#!/usr/bin/env bash
# .github/scripts/check_loc.py (canonical — Python; replaces the historical .sh form)
set -euo pipefail

THRESHOLD=400
VIOLATIONS=0

while IFS= read -r -d '' f; do
    # Count non-blank, non-pure-comment lines
    LOC=$(grep -cvE '^\s*(#|$)' "$f" || true)
    if (( LOC > THRESHOLD )); then
        echo "::error file=$f::File has $LOC LOC (cap: $THRESHOLD). Split it via composition or extraction."
        VIOLATIONS=$((VIOLATIONS + 1))
    fi
done < <(find packages eval splunk_apps/splunkgate_app/bin -name '*.py' \
            -not -path '*/.venv/*' -not -path '*/__pycache__/*' -print0 2>/dev/null)

if (( VIOLATIONS > 0 )); then
    echo "::error::$VIOLATIONS file(s) exceed 400 LOC. See above for details."
    exit 1
fi
echo "All files within 400 LOC cap."
```

The same script runs as a pre-commit hook (see `.pre-commit-config.yaml` skeleton in story `cicd-04`).

---

## `eval.yml` — the full eval pipeline

### Triggers

- PR with label `eval` added (manual)
- Nightly cron `0 2 * * *` (UTC)
- Manual `workflow_dispatch`

### Jobs

1. `eval-full` — runs the full eval harness (JailbreakBench + AdvBench + custom corpus + Imprompter payloads)
2. `eval-publish` — uploads `eval/results/<sha>/` artifact + commits a summary to `docs/eval-results.md` on `main` (nightly only)

### Concrete YAML skeleton

```yaml
# .github/workflows/eval.yml
name: Eval
on:
  pull_request:
    types: [labeled]
  schedule:
    - cron: '0 2 * * *'
  workflow_dispatch:

jobs:
  eval-full:
    if: github.event.label.name == 'eval' || github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-latest
    timeout-minutes: 60
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: recursive   # pulls llm-attacks/llm-attacks dataset
      - uses: astral-sh/setup-uv@v3
      - run: uv python install 3.13
      - run: uv sync --frozen
      - run: uv run python eval/scripts/run_full.py
        env:
          SPLUNKGATE_AI_DEFENSE_API_KEY: ${{ secrets.SPLUNKGATE_AI_DEFENSE_API_KEY }}
          SPLUNKGATE_AI_DEFENSE_MOCK: false
          SPLUNKGATE_SPLUNK_HEC_TOKEN: ${{ secrets.SPLUNKGATE_SPLUNK_HEC_TOKEN }}
          SPLUNKGATE_SPLUNK_HEC_URL: ${{ secrets.SPLUNKGATE_SPLUNK_HEC_URL }}
      - uses: actions/upload-artifact@v4
        with:
          name: eval-results-${{ github.sha }}
          path: eval/results/
```

---

## `release.yml` — signed release pipeline

### Triggers

- Tag push matching `v*.*.*` (e.g., `v0.1.0`)

### Jobs

1. `build-and-sign` — build wheels + Splunk app `.tgz` + sigstore-signed
2. `gh-release` — create GitHub Release with auto-generated changelog from conventional commits

### Concrete YAML skeleton

```yaml
# .github/workflows/release.yml
name: Release
on:
  push:
    tags: ['v*.*.*']

permissions:
  contents: write
  id-token: write       # required for sigstore OIDC

jobs:
  build-and-sign:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: astral-sh/setup-uv@v3
      - run: uv python install 3.13
      - run: uv sync --all-packages --frozen
      - run: uv build --all-packages --out-dir dist/
      - run: tar --exclude='__pycache__' -czf dist/splunkgate_app-${{ github.ref_name }}.tgz -C splunk_apps splunkgate_app
      - uses: sigstore/gh-action-sigstore-python@v3.0.0
        with:
          inputs: dist/*.whl dist/*.tgz
      - uses: actions/upload-artifact@v4
        with:
          name: release-artifacts
          path: dist/

  gh-release:
    needs: build-and-sign
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/download-artifact@v4
        with:
          name: release-artifacts
          path: dist/
      - uses: softprops/action-gh-release@v2
        with:
          files: dist/*
          generate_release_notes: true
          draft: false
          prerelease: ${{ contains(github.ref_name, 'rc') || contains(github.ref_name, 'alpha') }}
```

---

## `security.yml` — security scanning

### Triggers

- `push` + nightly cron

### Jobs

1. `pip-audit` — known CVEs in deps
2. `gitleaks` — credential scan
3. `trivy-fs` — filesystem scan (catches secrets in committed files + OS deps in Docker images)
4. `bandit` — Python static security scan on `splunkgate_judges` (touches credentials)
5. **`splunk-mcp-ta-style-check`** — verbatim regex patterns the Rod-Soto-authored Splunk MCP TA (Splunkbase 8377) flags (`context/06-splunk-ai-stack/`). We run them against our own MCP traffic logs to dog-food our own audit framing.

### Concrete YAML skeleton

```yaml
# .github/workflows/security.yml
name: Security
on:
  push:
    branches: ['**']
  schedule:
    - cron: '0 3 * * *'

jobs:
  pip-audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv python install 3.13
      - run: uv sync --frozen
      - run: uv run pip-audit --strict --ignore-vuln GHSA-XXXX-XXXX-XXXX

  gitleaks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: gitleaks/gitleaks-action@v2
        env:
          GITLEAKS_LICENSE: ${{ secrets.GITLEAKS_LICENSE }}   # optional, free for OSS

  trivy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: aquasecurity/trivy-action@master
        with:
          scan-type: 'fs'
          scan-ref: '.'
          severity: 'CRITICAL,HIGH'
          exit-code: '1'

  bandit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv run --with bandit bandit -r packages/splunkgate_judges/src/
```

---

## Pre-commit hooks (`.pre-commit-config.yaml`)

Runs on every `git commit`. Coding agents must install (`uv run pre-commit install`).

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.7.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.13.0
    hooks:
      - id: mypy
        files: ^packages/(splunkgate_core|splunkgate_judges)/src/
        args: [--strict]
        additional_dependencies: [pydantic, httpx, structlog]

  - repo: local
    hooks:
      - id: check-loc
        name: 400-LOC cap
        entry: uv run python .github/scripts/check_loc.py
        language: system
        pass_filenames: false

      - id: no-print
        name: No print() in production
        entry: bash -c 'if grep -rn "print(" packages/splunkgate_*/src/ --include="*.py" | grep -v "structlog\|test\|_mock\.py"; then echo "Use structlog, not print()"; exit 1; fi'
        language: system
        pass_filenames: false

  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.21.2
    hooks:
      - id: gitleaks
```

---

## Branch protection (manual GitHub config — coding agent documents in `docs/`)

Required after `gh repo create`:

- `main` branch:
  - Require pull request review (1 approval) — for solo project, "Require status checks" is the gate
  - Required status checks: `lint`, `typecheck`, `loc-cap`, `test (splunkgate_core)`, `test (splunkgate_judges)`, `test (splunkgate_mw)`, `test (splunkgate_mcp)`, `appinspect`, `eval-smoke`, `build-wheels`, `build-app`, `pip-audit`, `gitleaks`, `trivy`
  - Require branches up to date before merging
  - Restrict who can push to matching branches: only `main` PR-only
  - Allow force pushes: no
  - Allow deletions: no

---

## Secrets to configure in GitHub

| Secret | Source | Used by |
|---|---|---|
| `SPLUNKGATE_AI_DEFENSE_API_KEY` | Cisco Security Cloud Control tenant (Abu sets up) | `eval-full` job |
| `SPLUNKGATE_SPLUNK_HEC_TOKEN` | Abu's Splunk Cloud instance HEC config | `eval-full` job (writes verdicts to live Splunk for the demo) |
| `SPLUNKGATE_SPLUNK_HEC_URL` | `https://prd-p-t9irr.splunkcloud.com:8088/services/collector/event` | `eval-full` job |
| `PYPI_API_TOKEN` | PyPI publish (only if Abu wants public packages) | `release.yml` — currently NOT wired (deferred to v0.2) |
| `GITLEAKS_LICENSE` | gitleaks.io (free for OSS) | `gitleaks` job |
| `CODECOV_TOKEN` | codecov.io | `test` job |

Coding agent for `story-cicd-08-secrets-setup` documents how Abu obtains each.

---

## Acceptance for the CI/CD epic as a whole

CI/CD epic is "done" when:

- [ ] All 4 workflow YAML files exist under `.github/workflows/`
- [ ] All required status checks listed above appear in a PR's "Checks" view and all turn green
- [ ] Pre-commit installed and working locally
- [ ] `check_loc.py` exists and rejects a deliberately-too-big test file
- [ ] `parse_appinspect.py` exists and a sample AppInspect output is parsed correctly
- [ ] Branch protection documented in `docs/ops/branch-protection.md`
- [ ] Secrets list documented in `docs/ops/secrets.md`
- [ ] At least one test commit demonstrates the full pipeline running on a real PR (story `story-cicd-08`)
- [ ] Eval-smoke job runs end-to-end with AI Defense mock client

---

## Failure mode handling

- **`test` matrix job fails on one package:** other matrix entries continue; PR fails overall; coding agent fixes that package without breaking others.
- **`appinspect` fails:** error-severity findings block; warning-severity findings get listed in `.appinspect.expect.yaml` as accepted (mirrors CIMplicity 2025 winner pattern — `context/11-prior-art/01-build-a-thon-2025-deep-read.md`).
- **`loc-cap` fails:** error message names the file + LOC + suggests `split via composition or extraction`. No `# noqa: loc-cap` escape hatch — split the file.
- **`gitleaks` fails:** rejects the push entirely; coding agent rotates the leaked secret + force-pushes a rewritten history with `git-filter-repo`.
- **`eval-smoke` fails:** PR can still merge IF Abu approves with a comment `/override eval-smoke`. This is the only override path. The full `eval` workflow runs nightly anyway.
