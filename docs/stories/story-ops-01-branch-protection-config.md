# Story — GitHub branch protection: docs + configuration script

**ID:** story-ops-01-branch-protection-config
**Epic:** EPIC-12 — AppInspect hardening + Ops
**Depends on:** story-cicd-07-security-scan-pipeline
**Estimate:** ~1.5h
**Status:** PENDING

---

## User story

**As a** repo maintainer (or Abu, after `gh repo create` lands the public SplunkGate repo)
**I want to** run a single `bash scripts/configure_branch_protection.sh` command and have GitHub's `main` branch protection configured exactly as specified in `docs/cicd-spec.md` § "Branch protection" — required status checks, no force pushes, no deletions, up-to-date-before-merge
**So that** no PR (including agent-authored ones) lands on `main` without a green CI matrix, and the build's submission-checklist gates ("CI green on main") cannot be bypassed during the demo crunch

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `docs/ops/branch-protection.md` — NEW — operator-facing doc. Sections: (1) one-paragraph purpose citing `docs/cicd-spec.md` § "Branch protection"; (2) verbatim list of the 14 required status checks (`lint`, `typecheck`, `loc-cap`, `test (splunkgate_core)`, `test (splunkgate_judges)`, `test (splunkgate_mw)`, `test (splunkgate_mcp)`, `appinspect`, `eval-smoke`, `build-wheels`, `build-app`, `pip-audit`, `gitleaks`, `trivy`); (3) the non-check rules (`required_pull_request_reviews.required_approving_review_count: 1`, `enforce_admins: true`, `restrictions: null`, `allow_force_pushes: false`, `allow_deletions: false`, `required_linear_history: false`, `required_conversation_resolution: true`); (4) "How to apply" — recommended path is `bash scripts/configure_branch_protection.sh` (idempotent); manual fallback via `gh api` documented for read-only auditors; (5) "How to verify" — `gh api /repos/$OWNER/$REPO/branches/main/protection | jq .` and grep for each required check name; (6) post-submission relaxation guidance (e.g., post-hackathon, allow admin self-merge on docs-only PRs); (7) citation to `docs/cicd-spec.md` § "Branch protection" and `docs/architecture.md` § "submission checklist gates".
- `scripts/configure_branch_protection.sh` — NEW — ~120 LOC bash script. Reads `GH_OWNER` + `GH_REPO` env vars (fail fast with exit 2 if either missing); calls `gh api -X PUT /repos/$GH_OWNER/$GH_REPO/branches/main/protection` with a heredoc'd JSON body matching the spec exactly. Idempotent — re-running on an already-configured repo updates in place without error. Verbose mode (`-v` or `VERBOSE=1`) prints the JSON body before sending. Dry-run mode (`-n` or `DRY_RUN=1`) prints what would be sent and exits 0. Exit codes: 0 success, 1 `gh` CLI not authenticated / API call failed, 2 missing env var. Includes a post-call verification step: re-reads via `gh api` + greps for each of the 14 required check names; if any missing, exit 3.
- `scripts/tests/test_configure_branch_protection.sh` — NEW — ~80 LOC bats-or-shell test. Covers: dry-run prints the JSON body containing all 14 status check names; missing env vars exits 2; invalid `gh` auth exits 1; the JSON body contains `enforce_admins: true`, `allow_force_pushes: false`, `allow_deletions: false`, `required_linear_history: false`. Uses `gh` stub (PATH-overridden mock) so no real API call fires.
- `docs/ops/README.md` — NEW — short index pointing at `branch-protection.md` and `secrets.md` (the latter ships in `story-ops-02`); one-paragraph description of the `docs/ops/` directory's purpose ("GitHub-side operational configuration documentation; mirrors what `docs/architecture.md` says about CI gates but at the org/repo configuration layer").

The coding agent must NOT modify files outside this map without re-checking `CLAUDE.md`. In particular: **do not** add a Python wrapper around `gh` (bash is the right shape for `gh` CLI orchestration); **do not** commit a `GITHUB_TOKEN` or any auth fixture; **do not** modify `.github/workflows/` from this story (the workflow definitions are owned by EPIC-01 stories).

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given docs/ops/branch-protection.md exists
When  `grep -c 'status check' docs/ops/branch-protection.md` runs
Then  the count is ≥ 1 (the doc references "status check" by name)

Given docs/ops/branch-protection.md exists
When  the file is grepped for each of the 14 required status check names
Then  every name (lint, typecheck, loc-cap, test (splunkgate_core), test (splunkgate_judges), test (splunkgate_mw), test (splunkgate_mcp), appinspect, eval-smoke, build-wheels, build-app, pip-audit, gitleaks, trivy) appears at least once

Given docs/ops/branch-protection.md exists
When  the file is grepped for each setting key in turn
Then  every one of `allow_force_pushes`, `allow_deletions`, `enforce_admins`, `required_conversation_resolution` appears at least once
(Verify per-key — do NOT use `grep -F` with `\|` because `-F` treats backslash-pipe as literal characters, not alternation. Either loop the 4 keys with `-c` per key, or use plain `grep -cE` for extended-regex alternation.)

Given scripts/configure_branch_protection.sh exists and is executable
When  `bash scripts/configure_branch_protection.sh -n` runs without GH_OWNER/GH_REPO env
Then  exit code is 2

Given GH_OWNER=test GH_REPO=test
When  `GH_OWNER=test GH_REPO=test bash scripts/configure_branch_protection.sh -n` runs
Then  exit code is 0
And   stdout contains all 14 required status check names (lint, typecheck, loc-cap, test (splunkgate_core), test (splunkgate_judges), test (splunkgate_mw), test (splunkgate_mcp), appinspect, eval-smoke, build-wheels, build-app, pip-audit, gitleaks, trivy)
And   stdout contains '"enforce_admins": true'
And   stdout contains '"allow_force_pushes": false'
And   stdout contains '"allow_deletions": false'

Given the test harness in scripts/tests/test_configure_branch_protection.sh
When  `bash scripts/tests/test_configure_branch_protection.sh` runs
Then  exit code is 0

Given the script file
When  `wc -l scripts/configure_branch_protection.sh` runs
Then  the line count is ≤ 400

Given the §14 grep is run on the script + docs (this is operational tooling, no production code path)
When  `grep -rE "(mock|fake|dummy|hardcoded|simulated)" docs/ops/branch-protection.md scripts/configure_branch_protection.sh` runs
Then  output is empty (or only inside test-stub comments annotated with §14 carve-out)
```

---

## Shell verification

The coding agent runs this end-to-end locally to confirm the story is done before opening a PR:

```bash
set -euo pipefail

# 1. Files exist
test -f docs/ops/branch-protection.md
test -f docs/ops/README.md
test -f scripts/configure_branch_protection.sh
test -x scripts/configure_branch_protection.sh
test -f scripts/tests/test_configure_branch_protection.sh

# 2. Branch-protection doc references all 14 required status checks
for check in 'lint' 'typecheck' 'loc-cap' 'test (splunkgate_core)' 'test (splunkgate_judges)' 'test (splunkgate_mw)' 'test (splunkgate_mcp)' 'appinspect' 'eval-smoke' 'build-wheels' 'build-app' 'pip-audit' 'gitleaks' 'trivy'; do
  grep -qF "$check" docs/ops/branch-protection.md || { echo "MISSING check name in doc: $check"; exit 1; }
done

# 3. Branch-protection doc references the non-check rules
grep -q 'allow_force_pushes' docs/ops/branch-protection.md
grep -q 'allow_deletions'    docs/ops/branch-protection.md
grep -q 'enforce_admins'     docs/ops/branch-protection.md
grep -q 'required_conversation_resolution' docs/ops/branch-protection.md

# 4. Script fails without env vars
set +e
bash scripts/configure_branch_protection.sh -n 2>/dev/null
rc=$?
set -e
[ "$rc" -eq 2 ]

# 5. Dry-run with env vars prints all 14 check names + the three rule flags
out=$(GH_OWNER=test GH_REPO=test bash scripts/configure_branch_protection.sh -n)
for check in 'lint' 'typecheck' 'loc-cap' 'test (splunkgate_core)' 'test (splunkgate_judges)' 'test (splunkgate_mw)' 'test (splunkgate_mcp)' 'appinspect' 'eval-smoke' 'build-wheels' 'build-app' 'pip-audit' 'gitleaks' 'trivy'; do
  echo "$out" | grep -qF "$check" || { echo "MISSING from dry-run: $check"; exit 1; }
done
echo "$out" | grep -q '"enforce_admins": true'
echo "$out" | grep -q '"allow_force_pushes": false'
echo "$out" | grep -q '"allow_deletions": false'

# 6. Test harness passes
bash scripts/tests/test_configure_branch_protection.sh

# 7. 400-LOC cap
[ "$(wc -l < scripts/configure_branch_protection.sh)" -le 400 ]

# 8. §14 clean
! grep -E "(mock|fake|dummy|hardcoded|simulated)" docs/ops/branch-protection.md scripts/configure_branch_protection.sh

# 9. Live apply (gated on env vars + explicit SPLUNKGATE_APPLY_BRANCH_PROTECTION=1)
if [ -n "${GH_OWNER:-}" ] && [ -n "${GH_REPO:-}" ] && [ "${SPLUNKGATE_APPLY_BRANCH_PROTECTION:-0}" = "1" ]; then
  bash scripts/configure_branch_protection.sh
  # Re-read + verify
  gh api "/repos/${GH_OWNER}/${GH_REPO}/branches/main/protection" | jq -e '.required_status_checks.contexts | length >= 14'
fi
echo "ALL CHECKS PASS"
```

All blocks must exit 0 before opening the PR (block 9 is conditional on env var + explicit opt-in; otherwise skipped).

---

## Notes for coding agent

- **Per `docs/cicd-spec.md` § "Branch protection"**, the 14 required status checks are: `lint`, `typecheck`, `loc-cap`, `test (splunkgate_core)`, `test (splunkgate_judges)`, `test (splunkgate_mw)`, `test (splunkgate_mcp)`, `appinspect`, `eval-smoke`, `build-wheels`, `build-app`, `pip-audit`, `gitleaks`, `trivy`. These map 1:1 to the job names in the CI workflows from EPIC-01 stories. The matrix-job names use the format `test (splunkgate_core)` — preserve the space + parens exactly (GitHub Actions reports matrix jobs with this exact display name).
- **Per `docs/cicd-spec.md` § "Acceptance for the CI/CD epic as a whole"** checklist item "Branch protection documented in `docs/ops/branch-protection.md`" — this story owns that line item. Without it, EPIC-01 cannot mark itself done.
- **Per `docs/architecture.md` § "submission checklist gates"** > "CI" > "`.github/workflows/{ci,eval,release,security}.yml` exist and pass on main branch" — branch protection is the GitHub-side guarantee that the gates can't be bypassed.
- **GitHub branch-protection API payload shape** (canonical reference: https://docs.github.com/en/rest/branches/branch-protection):
  ```json
  {
    "required_status_checks": {
      "strict": true,
      "contexts": ["lint", "typecheck", "loc-cap", "test (splunkgate_core)", ...]
    },
    "enforce_admins": true,
    "required_pull_request_reviews": {
      "required_approving_review_count": 1,
      "dismiss_stale_reviews": true,
      "require_code_owner_reviews": false
    },
    "restrictions": null,
    "allow_force_pushes": false,
    "allow_deletions": false,
    "required_linear_history": false,
    "required_conversation_resolution": true
  }
  ```
  Use `gh api -X PUT` with a heredoc — do NOT use multiple `gh api` calls. The branch-protection endpoint is PUT-based (full-replace), not PATCH; missing fields revert to defaults.
- **Idempotency** is load-bearing: re-running the script after a one-line CI workflow rename (e.g., `build-wheels` → `build_wheels`) MUST update the protection rule, not error. The PUT semantics handle this — just send the new full body.
- **`gh` CLI auth check**: run `gh auth status` at the top of the script; if it exits non-zero, abort with exit 1 + a message pointing the operator at `gh auth login`.
- **The script + docs are read-only on `main` branch settings until executed**: this story does NOT apply protection to the real repo automatically. The CI/CD epic's "Apply branch protection to the real repo" step is a separate manual operation Abu runs after the EPIC-01 + EPIC-02 stories land (the protection rules require the workflow names to already exist as GitHub Actions check contexts, which only happens after the workflows have run at least once).
- **Per `docs/architecture.md` § "Banned patterns"**, no `print()` debug output in production. The script's `set -x` (or `VERBOSE=1` mode) is the operator-debugging path — not always-on.
- **`docs/ops/` is a new directory** introduced by this story + `story-ops-02`. Both stories' agents share that namespace — the `docs/ops/README.md` from this story is a one-paragraph index; `story-ops-02` extends it with a link to `secrets.md`. Coordinate via the docs/ops/README.md atomic edit (this story creates it with one bullet, ops-02 appends a second).
- **Test stub for `gh` CLI**: the harness creates a temp directory, drops a `gh` shell script that echoes its args + exits 0 (or 1 / 2 based on test scenario), prepends the temp dir to `PATH`. Annotate this as a §14 carve-out (operational test scaffolding, not production code).
- **No `gh secret` calls in this story** — secrets are owned by `story-ops-02-github-secrets-and-adr-template`. Cross-reference but don't overlap.
- **Per the hackathon submission rules from `../../../research/splunk-agentic-ops-2026/01-prizes-tracks.md`**, the public repo is a non-negotiable submission requirement. Branch protection signals that the agent-driven build was disciplined — judges who skim the repo settings will see required-status-checks enforcement.
- Estimate breakdown: ~30 min `gh api` body construction + dry-run flag, ~30 min docs + verbatim status-check list, ~30 min test harness with stubbed `gh`, ~15 min readme + idempotency loop.
