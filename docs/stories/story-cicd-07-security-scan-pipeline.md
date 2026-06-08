# Story — Security scan pipeline: pip-audit + gitleaks + trivy + bandit

**ID:** story-cicd-07-security-scan-pipeline
**Epic:** EPIC-01 — CI/CD foundation
**Depends on:** None
**Estimate:** ~1.5h
**Status:** PENDING

---

## User story

**As a** coding agent who might unknowingly pull a CVE-laden transitive dep, leak a credential into git history, or write Python that bandit flags as security-smelling
**I want to** the security workflow run pip-audit, gitleaks, trivy filesystem scan, and bandit (scoped to `splunkgate_judges`) on every push and nightly
**So that** vulnerable dependencies, leaked secrets, and security smells get caught before they reach `main`, and SplunkGate's submission gets to claim a clean security posture in the README

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `.github/workflows/security.yml` — NEW — defines the `Security` workflow. Triggers: `push` on all branches + `schedule: cron '0 3 * * *'` (3am UTC nightly). Four jobs (`pip-audit`, `gitleaks`, `trivy`, `bandit`) — each runs `runs-on: ubuntu-latest`, no `needs:` (run in parallel). Copy verbatim from `docs/cicd-spec.md` § "security.yml — security scanning" lines 352-398. Severity floor for trivy: `CRITICAL,HIGH` (`exit-code: '1'`). Bandit scope: `packages/splunkgate_judges/src/` only (the package that touches credentials).
- `.bandit` — NEW — bandit config file (~30 lines). Skip rules: `B101` (assert_used — pytest uses asserts), `B404` (subprocess imports — needed for `splunklib`-style invocation). Confidence floor: `MEDIUM`. Severity floor: `MEDIUM`.
- `.gitleaks.toml` — NEW — gitleaks config (~50 lines). Inherits from gitleaks default ruleset. Allowlist: (1) `tests/fixtures/` paths (synthetic-fixture carve-out); (2) `SPLUNKGATE_AI_DEFENSE_API_KEY` placeholder in `docs/` (env-var name not the value); (3) the `verify=False` documented warning in `docs/architecture.md` (string contains `verify=False` but is not a secret). NO allowlist for `AKIA*`-shaped strings outside fixture paths.
- `docs/ops/security-scan-policy.md` — NEW — short doc (~50 lines) covering: (1) which scanners run on which trigger; (2) the severity floor per scanner; (3) how to triage a pip-audit GHSA hit (open ADR, ignore via `--ignore-vuln GHSA-XXXX`, document in `pyproject.toml` comment); (4) how to handle a real gitleaks hit (rotate + `git-filter-repo` per `docs/cicd-spec.md` line 496).
- `tests/fixtures/security/has_pip_audit_target.txt` — NEW — file documenting that pip-audit runs over `uv.lock` (no fixture content needed; pip-audit auto-detects)
- `tests/test_bandit_clean.py` — NEW — pytest module with 2 test cases: (a) running `bandit -r packages/splunkgate_judges/src/` on placeholder code exits 0 (or low-severity-only); (b) inserting `eval("user_input")` in a temp file causes bandit `-r` over the temp file to exit non-zero (proves bandit actually fires)

The coding agent must NOT modify files outside this map without re-checking CLAUDE.md.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given `.github/workflows/security.yml` exists
When  `gh workflow list` runs after pushing the file
Then  the workflow appears with name `Security`

Given the security workflow runs on GitHub Actions
When  it completes on a clean PR
Then  all four jobs (`pip-audit`, `gitleaks`, `trivy`, `bandit`) finish with `conclusion: success`
And   `gh run view --json jobs --jq '.jobs | map(select(.workflow_name == "Security")) | length'` is at least 4

Given the project has no known-CVE deps
When  `uv run pip-audit --strict` runs locally
Then  exit code is 0
And   stdout contains either `No known vulnerabilities found` or matches the strict-mode no-vulns format

Given `gitleaks detect --no-git -v --config .gitleaks.toml --source .` runs on a clean repo
When  the scan completes
Then  exit code is 0
And   stdout contains either `No leaks found` or `no leaks found`

Given `trivy fs --severity CRITICAL,HIGH --exit-code 1 .` runs locally
When  the scan completes
Then  exit code is 0 (or trivy not installed locally — accept via env-gate `if command -v trivy`)

Given `uv run --with bandit bandit -r packages/splunkgate_judges/src/ -c .bandit` runs
When  the scan completes on placeholder code
Then  exit code is 0 (no MEDIUM+/MEDIUM+ findings)

Given `uv run pytest tests/test_bandit_clean.py` runs
When  the run completes
Then  exit code is 0
And   stdout contains `2 passed`

Given the security workflow has triggers
When  `grep -E "(push|schedule)" .github/workflows/security.yml` runs
Then  both `push` and `schedule` trigger sections appear

Given `grep "cron: '0 3 \* \* \*'" .github/workflows/security.yml` runs
When  the output is checked
Then  the count is `1` (nightly cron at 3am UTC)

Given `grep -c "^  [a-z-]*:$" .github/workflows/security.yml` runs (rough top-level job count)
When  the output is checked
Then  the count >= 4 (four jobs)
```

---

## Shell verification

The coding agent runs this end-to-end locally before opening a PR:

```bash
set -euo pipefail

# 1. Workflow file syntactically valid
test -f .github/workflows/security.yml
python -c "import yaml; yaml.safe_load(open('.github/workflows/security.yml'))"
grep -q 'name: Security' .github/workflows/security.yml
grep -q "cron: '0 3 \* \* \*'" .github/workflows/security.yml

# 2. pip-audit clean on current lock
uv sync --frozen
uv run pip-audit --strict

# 3. gitleaks clean
if command -v gitleaks >/dev/null; then
  gitleaks detect --no-git -v --config .gitleaks.toml --source .
else
  echo "skipping local gitleaks (not installed); CI will catch"
fi

# 4. trivy fs clean (if locally installed)
if command -v trivy >/dev/null; then
  trivy fs --severity CRITICAL,HIGH --exit-code 1 .
fi

# 5. bandit clean on splunkgate_judges placeholder code
uv run --with bandit bandit -r packages/splunkgate_judges/src/ -c .bandit

# 6. Bandit-violator test fires
uv run pytest tests/test_bandit_clean.py -v
uv run pytest tests/test_bandit_clean.py -q | grep -q '2 passed'

# 7. Workflow YAML has all 4 job IDs
for job in pip-audit gitleaks trivy bandit; do
  grep -qE "^  ${job}:" .github/workflows/security.yml
done

# 8. Push and verify
git push origin HEAD
gh run watch --exit-status
```

All blocks must exit 0.

---

## Notes for coding agent

- Per `docs/cicd-spec.md` § "Pipeline overview" line 24, `security.yml` is required for merge to `main`. Branch protection wiring (EPIC-02 ops doc) lists `pip-audit`, `gitleaks`, `trivy` as required status checks; `bandit` is recommended but not yet required (deferred to EPIC-02's ops doc).
- The spec line 348 mentions a 5th job `splunk-mcp-ta-style-check` — verbatim regex patterns from Rod Soto's Splunk MCP TA (Splunkbase 8377). THIS STORY DEFERS THAT JOB to a future EPIC-12 story because: (1) the patterns require pulling the TA from Splunkbase and extracting regex from `transforms.conf`, which is read-only research; (2) the patterns scan MCP traffic logs, which don't exist until Surface 2 ships (EPIC-07); (3) self-dog-fooding has no value pre-Surface-2. Flag this deferral in the PR description with a TODO.
- Per `docs/architecture.md` § "Hard rules" #5-#7, the project never commits real Cisco / Splunk credentials. The `.gitleaks.toml` allowlist must NOT broaden beyond the documented carve-outs — every additional allowlist entry must reference a `docs/` file as justification.
- The bandit config skips `B101` (assert usage) because pytest is built on `assert`. Per `../../../context/02-agent-frameworks/06-splunklib-ai-deep-read.md`, `splunklib` itself uses asserts in its test suite — we follow the same convention.
- `B404` (subprocess imports) is skipped because Splunk SDK invocation patterns in EPIC-05 (`story-foundsec-01-splunk-rest-search-client.md`) may shell out to `splunk` CLI in test fixtures. Document this skip in the `.bandit` config as `# Skipped: subprocess legitimate for Splunk CLI invocation tests`.
- Per `docs/cicd-spec.md` line 369, `--ignore-vuln GHSA-XXXX-XXXX-XXXX` is a placeholder — DO NOT copy the literal `GHSA-XXXX...` placeholder; remove the `--ignore-vuln` flag for now. Add the flag back per-CVE only when a real GHSA is triaged and needs deferral (with ADR).
- Trivy filesystem scan covers committed files + OS-level deps if a `Dockerfile` exists. The current project has no `Dockerfile`; trivy will only scan committed files. When EPIC-09 adds a Splunk Cloud container fixture (if any), revisit trivy config.
- `gitleaks-action@v2` (`docs/cicd-spec.md` line 377) honors `GITLEAKS_LICENSE` env var; for public OSS repos this is free. Document in `docs/ops/secrets.md` (EPIC-02) that the secret is optional.
- Nightly cron at 3am UTC stays out of US working hours (avoids noisy notifications) and doesn't collide with eval workflow at 2am UTC. Do not move it.
- Per `../../../context/HALLUCINATION-AUDIT.md`, several Cisco-adjacent libraries did not exist at audit time (e.g., Luna-2 SDK). pip-audit and trivy DO NOT detect missing libraries; this story does not address supply-chain "did the package exist when we depended on it" questions — that's an ADR concern.
- The bandit violator test must not actually leave an `eval("...")` line in the tree (pre-commit would block the commit anyway). Use `tmp_path` fixture + write a temp `.py` file inside the test, run bandit against it via `subprocess.run(["uv", "run", "--with", "bandit", "bandit", "-r", str(tmp_path)])`, assert non-zero exit. Pytest tmp_path fixtures are auto-cleaned.
