# Story — GitHub secrets registry + ADR template + docs/adrs/ directory bootstrap

**ID:** story-ops-02-github-secrets-and-adr-template
**Epic:** EPIC-12 — AppInspect hardening + Ops
**Depends on:** story-cicd-07-security-scan-pipeline, story-skel-03-claude-md-and-contribution-conventions
**Estimate:** ~1.5h
**Status:** PENDING

---

## User story

**As a** repo maintainer (or a future contributor) preparing to run the `eval-full` GitHub Actions workflow or to record an architectural decision after the build locks
**I want to** consult `docs/ops/secrets.md` for every required GitHub secret (name, source, who provisions, which workflow consumes it) and `docs/adrs/_template.md` as the canonical format for new ADRs, plus a populated `docs/adrs/README.md` listing the 11 ADRs that already exist in `docs/architecture.md` § "Architecture decisions"
**So that** the `eval-full` job doesn't silently skip on missing tokens, and post-build architecture decisions land in the right shape (matching the in-architecture ADRs 001–011) without forcing every contributor to invent a template — also unblocks `docs/architecture.md:68` which references `docs/adrs/` that doesn't yet exist on disk (audit Block B-5)

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `docs/ops/secrets.md` — NEW — operator-facing registry of every GitHub Actions secret SplunkGate depends on. Sections: (1) one-paragraph purpose citing `docs/cicd-spec.md` § "Secrets to configure in GitHub"; (2) per-secret table with columns `Secret name | Source | Provisioned by | Consumed by workflow:job | Required-or-optional | Rotation policy`; (3) verbatim entries for `SPLUNKGATE_AI_DEFENSE_API_KEY` (Cisco Security Cloud Control tenant, Abu provisions, `eval.yml:eval-full`, required for live judge chain — gated by `SPLUNKGATE_AI_DEFENSE_MOCK=false`, rotate every 90 days per Cisco docs), `SPLUNKGATE_SPLUNK_HEC_TOKEN` (Splunk Cloud Explorer Edition HEC config, Abu provisions, `eval.yml:eval-full` + `story-eval-06:e2e_demo`, required, rotate on token leak only — long-lived), `SPLUNKGATE_SPLUNK_HEC_URL` (Abu's `https://prd-p-t9irr.splunkcloud.com:8088/services/collector/event` per `docs/cicd-spec.md`, Abu provisions, required, change on instance migration), `SPLUNKGATE_SPLUNK_HOST` + `SPLUNKGATE_SPLUNK_API_TOKEN` (for `story-eval-06` SPL polling — Splunk REST API on port 8089), `GITLEAKS_LICENSE` (optional, free for OSS via gitleaks.io, used by `security.yml:gitleaks`), `CODECOV_TOKEN` (optional, codecov.io, used by `ci.yml:test` matrix); (4) "How to set" — `gh secret set <NAME> --body "$(cat secret.txt)"` per secret; (5) "How to verify" — `gh secret list` shows every required name (script provided at `scripts/check_required_secrets.sh`); (6) "How to revoke" — `gh secret delete <NAME>` + rotation guidance; (7) §14 disclaimer that this file documents NAMES + SOURCES only, never values.
- `scripts/check_required_secrets.sh` — NEW — ~80 LOC bash. Reads the list of required secret names (hardcoded from this story's spec; future-edit signals are caught by `sahil-pr-audit` cross-spec consistency). Calls `gh secret list --json name`, asserts every required name present, prints a table with one-line OK/MISSING column per secret. Exit codes: 0 all required present, 1 one or more missing, 2 `gh` not authenticated. Verbose flag `-v` lists every secret (required + optional).
- `docs/adrs/_template.md` — NEW — ADR template matching the existing in-architecture ADR shape (`docs/architecture.md` § "Architecture decisions"). Sections: `# ADR-NNN — <Title>`, `**Status:** Proposed | Accepted | Superseded by ADR-XXX | Deprecated`, `**Date:** YYYY-MM-DD`, `**Context:** <one paragraph — why this decision matters>`, `**Decision:** <the decision in declarative voice>`, `**Consequences:** <bulleted list of positive + negative impacts>`, `**Citations:** <bulleted list of `context/` and `docs/` paths backing the decision>`. The template is short (≤ 60 lines) so it doesn't intimidate contributors.
- `docs/adrs/README.md` — NEW — index of ADRs. (1) one-paragraph purpose ("Architecture Decision Records — formal post-build decisions that change SplunkGate's shape outside the locked `docs/architecture.md` ADR list. Use the `_template.md` and number sequentially."); (2) table listing ADR-001 through ADR-011 with their titles + a note that they live verbatim in `docs/architecture.md` § "Architecture decisions" (NOT duplicated here — the README points at the source); (3) "How to add ADR-012+" — copy `_template.md` to `ADR-012-<slug>.md`, fill, link from this README; (4) status flow diagram or list (Proposed → Accepted → Superseded); (5) citation to `docs/architecture.md` § "Architecture decisions" and `https://adr.github.io/`.
- `docs/ops/README.md` — UPDATE (or NEW if `story-ops-01` hasn't landed yet — coordinate via this story's PR, do not race-condition the file) — append a bullet pointing at `secrets.md`. Final file should list both `branch-protection.md` (from ops-01) and `secrets.md` (from this story).
- `scripts/tests/test_check_required_secrets.sh` — NEW — ~60 LOC test harness. Covers: missing-required-secret returns exit 1; all-required-present returns exit 0; verbose mode lists all secrets; `gh` unauthenticated returns exit 2. Uses a PATH-overridden `gh` stub (§14 carve-out for ops test scaffolding).

The coding agent must NOT modify files outside this map without re-checking `CLAUDE.md`. In particular: **do not** commit any secret value (`gitleaks` will reject the push); **do not** modify `docs/architecture.md` from this story (ADR-001 through ADR-011 are read-only — they're locked in architecture.md); **do not** duplicate the existing 11 ADRs in `docs/adrs/` (this is the audit Block B-5 fix — point at the source, don't fork it); **do not** redo `story-ops-01`'s `docs/ops/README.md` from scratch — append/merge.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given docs/ops/secrets.md exists
When  `grep -cE "SPLUNKGATE_AI_DEFENSE_API_KEY|SPLUNKGATE_SPLUNK_HEC_TOKEN|SPLUNKGATE_SPLUNK_HEC_URL" docs/ops/secrets.md` runs
Then  the count is ≥ 3

Given docs/ops/secrets.md exists
When  the file is grepped for "SPLUNKGATE_SPLUNK_HOST" and "SPLUNKGATE_SPLUNK_API_TOKEN" and "GITLEAKS_LICENSE" and "CODECOV_TOKEN"
Then  all four names appear

Given docs/ops/secrets.md exists
When  `grep -c '| Source ' docs/ops/secrets.md` runs (the table header line)
Then  count ≥ 1

Given docs/ops/secrets.md must never contain real secret values
When  `grep -E "(eyJ[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9]{20,}|[A-Fa-f0-9]{64})" docs/ops/secrets.md` runs
Then  zero matches (no JWT-shaped, OpenAI-key-shaped, or 64-hex-shaped strings present)

Given docs/adrs/_template.md exists
When  the file is parsed
Then  it contains the literal headings: "Status:", "Date:", "Context:", "Decision:", "Consequences:", "Citations:"

Given docs/adrs/README.md exists
When  `grep -cE "ADR-(00[1-9]|01[01])" docs/adrs/README.md` runs
Then  the count is ≥ 11 (all of ADR-001 through ADR-011 are listed)

Given docs/adrs/README.md exists
When  the file is grepped for "_template.md"
Then  count ≥ 1 (template referenced for new ADRs)

Given docs/adrs/README.md exists
When  the file is grepped for the literal string "docs/architecture.md"
Then  count ≥ 1 (canonical ADR source is referenced, not duplicated)

Given scripts/check_required_secrets.sh exists and is executable
When  `bash scripts/check_required_secrets.sh --help` runs
Then  exit code is 0
And   stdout lists all required secret names

Given a PATH-overridden gh stub reports all required secrets present
When  `bash scripts/check_required_secrets.sh` runs
Then  exit code is 0

Given the gh stub reports SPLUNKGATE_SPLUNK_HEC_TOKEN missing
When  `bash scripts/check_required_secrets.sh` runs
Then  exit code is 1
And   stdout names "SPLUNKGATE_SPLUNK_HEC_TOKEN" as MISSING

Given the gh stub returns auth-error
When  `bash scripts/check_required_secrets.sh` runs
Then  exit code is 2

Given the test harness
When  `bash scripts/tests/test_check_required_secrets.sh` runs
Then  exit code is 0

Given the §14 grep
When  `grep -rE "(mock|fake|dummy|hardcoded|simulated)" docs/ops/secrets.md docs/adrs/_template.md docs/adrs/README.md scripts/check_required_secrets.sh` runs
Then  the output is empty (or only inside test-stub paths annotated with §14 carve-out)

Given the script line counts
When  `wc -l scripts/check_required_secrets.sh` runs
Then  the count is ≤ 400
```

---

## Shell verification

The coding agent runs this end-to-end locally to confirm the story is done before opening a PR:

```bash
set -euo pipefail

# 1. Files exist
test -f docs/ops/secrets.md
test -f docs/ops/README.md
test -f docs/adrs/_template.md
test -f docs/adrs/README.md
test -f scripts/check_required_secrets.sh
test -x scripts/check_required_secrets.sh
test -f scripts/tests/test_check_required_secrets.sh

# 2. Secrets doc enumerates every required + optional secret
for name in SPLUNKGATE_AI_DEFENSE_API_KEY SPLUNKGATE_SPLUNK_HEC_TOKEN SPLUNKGATE_SPLUNK_HEC_URL SPLUNKGATE_SPLUNK_HOST SPLUNKGATE_SPLUNK_API_TOKEN GITLEAKS_LICENSE CODECOV_TOKEN; do
  grep -qF "$name" docs/ops/secrets.md || { echo "MISSING: $name"; exit 1; }
done

# 3. No real-looking secret values committed
! grep -E "(eyJ[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9]{20,}|[A-Fa-f0-9]{64})" docs/ops/secrets.md

# 4. ADR template has all required sections
for section in 'Status:' 'Date:' 'Context:' 'Decision:' 'Consequences:' 'Citations:'; do
  grep -qF "$section" docs/adrs/_template.md || { echo "MISSING ADR section: $section"; exit 1; }
done

# 5. ADR README lists ADR-001..ADR-011 + references _template.md + architecture.md
for n in 001 002 003 004 005 006 007 008 009 010 011; do
  grep -qF "ADR-$n" docs/adrs/README.md || { echo "MISSING: ADR-$n in README"; exit 1; }
done
grep -qF '_template.md'      docs/adrs/README.md
grep -qF 'docs/architecture.md' docs/adrs/README.md

# 6. ops/README.md indexes both branch-protection.md and secrets.md
grep -qF 'secrets.md' docs/ops/README.md

# 7. check_required_secrets.sh --help works
out=$(bash scripts/check_required_secrets.sh --help)
for name in SPLUNKGATE_AI_DEFENSE_API_KEY SPLUNKGATE_SPLUNK_HEC_TOKEN SPLUNKGATE_SPLUNK_HEC_URL; do
  echo "$out" | grep -qF "$name"
done

# 8. Test harness passes (stubs gh CLI)
bash scripts/tests/test_check_required_secrets.sh

# 9. 400-LOC cap
[ "$(wc -l < scripts/check_required_secrets.sh)" -le 400 ]

# 10. §14 clean
! grep -E "(mock|fake|dummy|hardcoded|simulated)" docs/ops/secrets.md docs/adrs/_template.md docs/adrs/README.md scripts/check_required_secrets.sh

# 11. Live secret-check (gated; requires gh auth + GH_OWNER + GH_REPO)
if [ -n "${GH_OWNER:-}" ] && [ -n "${GH_REPO:-}" ] && gh auth status >/dev/null 2>&1; then
  bash scripts/check_required_secrets.sh -v || echo "Some required secrets missing — expected on a fresh repo; document for Abu"
fi
echo "ALL CHECKS PASS"
```

All blocks must exit 0 before opening the PR (block 11 is conditional + best-effort; otherwise skipped).

---

## Notes for coding agent

- **Per `docs/cicd-spec.md` § "Secrets to configure in GitHub"**, the canonical table of required + optional secrets is verbatim:
  - `SPLUNKGATE_AI_DEFENSE_API_KEY` — required for `eval-full` live judge chain
  - `SPLUNKGATE_SPLUNK_HEC_TOKEN` — required for `eval-full` + e2e demo
  - `SPLUNKGATE_SPLUNK_HEC_URL` — required for HEC write
  - `PYPI_API_TOKEN` — NOT wired in v0.1 (deferred per spec — document as future)
  - `GITLEAKS_LICENSE` — optional, free OSS license
  - `CODECOV_TOKEN` — optional
  - Plus: `SPLUNKGATE_SPLUNK_HOST` + `SPLUNKGATE_SPLUNK_API_TOKEN` (added by `story-eval-06` for SPL polling — document them here as a forward-reference; the eval-06 story will consume them).
- **Per audit Block B-5 in `docs/plans/2026-06-03-audit-synthesis.md`**, `docs/architecture.md:68` references a `docs/adrs/` directory that doesn't yet exist. This story creates the directory + a template + a README. The 11 in-architecture ADRs (001–011) are NOT duplicated into `docs/adrs/` files — they stay locked in `architecture.md`. The README points at architecture.md as the canonical source. Future ADRs (012+) get their own files.
- **Per `docs/architecture.md` Hard Rule 5 ("No real Cisco API credentials in code or fixtures") and Hard Rule 6 ("No real Splunk credentials")**, this doc documents NAMES + SOURCES only — never values. The §14 grep is enforced in the BDD; any 32+ hex-char string or JWT-shape string in secrets.md is a hard fail.
- **Per `docs/architecture.md` § "submission checklist gates"** > "No real API keys committed; `gitleaks scan` returns clean" — this story's secrets.md MUST itself be gitleaks-clean.
- **ADR shape match `docs/architecture.md` § "Architecture decisions"** — the existing ADRs use bold-headed prose: `**ADR-XXX — Title.** Body.` Our template uses MD-heading + `**Status:**`/`**Date:**` for clarity (future ADRs are full documents, not one-liners). Cite both shapes in the template's Notes.
- **`gh secret list` returns `{"name": "...", "updated_at": "..."}`**. The check script parses with `jq -r '.[].name'` and intersects with the required set.
- **PATH-stubbed `gh` for tests**: create a temp dir, drop a `gh` shell script that echoes a configurable JSON body and exits with a configurable code, prepend dir to PATH for the test. Annotate as §14 carve-out. Same pattern as `story-ops-01`'s test harness.
- **Coordination with `story-ops-01` on `docs/ops/README.md`**: ops-01 creates the file with one bullet for `branch-protection.md`. This story appends a second bullet for `secrets.md`. If ops-01 hasn't landed yet (depends_on graph allows either order via independent CI checks), this story creates the file with both bullets and ops-01's PR rebases / accepts the unified file. Coordinate via PR review.
- **The 11 ADRs to list in `docs/adrs/README.md`** (verbatim from `docs/architecture.md` § "Architecture decisions"):
  1. ADR-001 — uv over poetry/pdm
  2. ADR-002 — Multi-package monorepo via uv workspaces
  3. ADR-003 — Foundation-Sec as explainer, NOT classifier
  4. ADR-004 — Our own MCP server, NOT registering into Splunk's
  5. ADR-005 — SplunkGate events emit to `cisco_ai_defense:splunkgate_verdict` sourcetype
  6. ADR-006 — Default to AI Defense mock client; live calls gated on env var
  7. ADR-007 — Luna-2 ships as `NotImplementedError`-raising stub
  8. ADR-008 — Splunk app uses Classic Simple XML wrapper around Dashboard Studio v2 JSON-in-XML
  9. ADR-009 — pre-commit hook + CI fail-on-exceed for the 400-LOC rule
  10. ADR-010 — splunklib.ai's 9-regex `detect_injection` is the cheap first-pass classifier
  11. ADR-011 — `Synthetic-Data/` folder name uses corrected spelling
- **Rotation policy notes** per secret type:
  - Cisco AI Defense API key: 90 days standard for tenant credentials
  - Splunk HEC token: long-lived, rotate on leak only (revoke via `splunk-cli` or web UI)
  - Splunk REST API token: 1 year default for service tokens
  - Codecov / gitleaks: managed by the third-party UIs
- **Per `docs/cicd-spec.md` § "Secrets to configure in GitHub"**, `SPLUNKGATE_SPLUNK_HEC_URL` value is `https://prd-p-t9irr.splunkcloud.com:8088/services/collector/event` — document this as the default-but-overridable value for Abu's instance. Future deployments swap the hostname.
- **`PYPI_API_TOKEN` is documented as "deferred to v0.2"** — list it in the table but mark as "Required for: release.yml (v0.2+), unused in v0.1". This prevents future contributors from being surprised.
- **`docs/ops/secrets.md` should NEVER show how to obtain `SPLUNKGATE_AI_DEFENSE_API_KEY` via cisco.com console** — operational detail belongs in operator runbooks (not in this repo). Link out to Cisco Security Cloud Control docs.
- Estimate breakdown: ~30 min secrets table + per-secret prose, ~30 min ADR template + README index, ~30 min check_required_secrets.sh + stub harness, ~15 min `docs/ops/README.md` merge + final polish.
