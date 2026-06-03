# Security scan policy

`.github/workflows/security.yml` runs four scanners on every push to any branch and nightly at 03:00 UTC.

## Scanners + triggers

| Scanner | What it scans | Severity floor | On-fail action |
|---|---|---|---|
| `pip-audit` | Python deps in `uv.lock` for known CVEs | strict (any vuln) | Triage GHSA; ignore via `--ignore-vuln <GHSA-ID>` ONLY with ADR documenting why |
| `gitleaks` | Full git history for secret patterns | default ruleset | Rotate the secret + `git-filter-repo` to rewrite history (per `docs/cicd-spec.md` line 496) |
| `trivy` (fs) | Committed files for OS/lib CVEs | `CRITICAL,HIGH` | Patch the lib or pin a fixed version; document in ADR if no fix exists |
| `bandit` | `packages/aegis_judges/src/` only | `MEDIUM,MEDIUM` | Fix the smell; rule skip ONLY in `.bandit` with comment justifying |

## Triage runbook

### pip-audit GHSA hit

1. Read the GHSA advisory — is the CVE in code we actually exercise?
2. If yes: upgrade the affected package via `uv add <pkg>@>=<fixed-version>` and re-run `pip-audit --strict`.
3. If no fix exists and the path is unreachable in our usage:
   - Open an ADR documenting the unreachable path
   - Add `--ignore-vuln <GHSA-ID>` to the pip-audit workflow step
   - Add an inline comment in the workflow YAML linking to the ADR
4. Re-evaluate every 30 days.

### gitleaks hit (real secret)

1. **Rotate the secret immediately** — assume it's compromised the moment it touched git history.
2. Rewrite history with `git-filter-repo --invert-paths --path <file>` (see `docs/cicd-spec.md` line 496).
3. Force-push (announce in PR description; required follow-up: every collaborator re-clones).
4. Do NOT add the secret's fingerprint to `.gitleaksignore`. The allowlist is for synthetic fixtures only.

### gitleaks hit (false positive)

1. Verify the string is truly synthetic (CI/test fixture, env-var name, docs example).
2. Add the path or pattern to `.gitleaks.toml` `[allowlist]` with a comment citing the docs/ file justifying the carve-out.

### trivy CRITICAL/HIGH hit

1. Check if the affected lib has a fixed version; if so, upgrade.
2. If the affected lib is a transitive dep, force a min-version via `[project.dependencies]` pin.
3. If no fix is available, document in ADR + add an exception comment in the workflow.

### bandit MEDIUM+ hit

1. Read the rule docs and the flagged line.
2. If genuine: fix the code (replace `subprocess.call(shell=True)` with `subprocess.run([...], shell=False)`, swap `eval()` for `ast.literal_eval()`, etc.).
3. If pattern is legitimate for our use case: add the rule to `.bandit` `skips =` with an inline comment justifying.

## What's NOT covered by these scanners

- Missing/never-existed package detection (e.g., depending on a library that doesn't exist) — covered by ADRs and primary-source verification per `../../../context/HALLUCINATION-AUDIT.md`.
- Cisco AI Defense API key validity — runtime concern, not a static scan.
- MCP protocol-level vulnerabilities — addressed by upstream MCP SDK pinning.

## Branch protection wiring

Per `docs/cicd-spec.md` § "Branch protection", these checks are required for merge to `main`:
- `pip-audit`
- `gitleaks`
- `trivy`

`bandit` is recommended but not yet required (deferred to EPIC-02's branch-protection doc — `story-ops-01-branch-protection-config`).
