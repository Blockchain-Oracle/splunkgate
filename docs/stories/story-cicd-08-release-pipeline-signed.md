# Story — Release pipeline: tag-triggered, sigstore-signed wheels + Splunk app .tgz + auto-changelog

**ID:** story-cicd-08-release-pipeline-signed
**Epic:** EPIC-01 — CI/CD foundation
**Depends on:** story-cicd-01-build-pipeline-python-wheels
**Estimate:** ~1.5h
**Status:** PENDING

---

## User story

**As a** coding agent (or Abu) pushing a `v*.*.*` tag to ship a release
**I want to** the release workflow build all 4 wheels + the Splunk app `.tgz`, sigstore-sign each artifact, attach them to a GitHub Release, and auto-generate a changelog from conventional commits since the previous tag
**So that** downstream installers can verify provenance via sigstore, the README's "install" instructions point at a real signed `.whl` URL, and reproducible releases unblock Splunkbase submission (EPIC-12) without extra manual steps

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `.github/workflows/release.yml` — NEW — defines the `Release` workflow. Trigger: `push` on `tags: ['v*.*.*']`. Two jobs: `build-and-sign` and `gh-release`. Copy verbatim from `docs/cicd-spec.md` § "release.yml — signed release pipeline" lines 285-332. `permissions: contents: write, id-token: write` (OIDC for sigstore). Pre-release flag derived from tag contains `rc` or `alpha`.
- `docs/ops/release-process.md` — NEW — short runbook (~80 lines) covering: (1) how to bump version across all 4 `packages/*/pyproject.toml` files + the Splunk app's `app.conf` `[launcher]` `version` (one command, one file at a time); (2) commit-and-tag flow (`git tag -s vX.Y.Z`); (3) where artifacts land (GitHub Releases page); (4) how to verify a signature (`sigstore verify identity --bundle ...`); (5) rollback (`gh release delete vX.Y.Z`); (6) Splunkbase submission delta (manual, deferred to EPIC-12).
- `scripts/bump_version.sh` — NEW — bash script (~80 LOC, under cap) that takes a SemVer arg (e.g., `0.1.0`) and updates: (1) `packages/aegis_core/pyproject.toml` `version = "..."`; (2) same for the other three packages; (3) `splunk_apps/aegis_app/default/app.conf` `[launcher] version = ...`; (4) creates a `git commit -m "chore(release): bump to vX.Y.Z"`. Uses `sed -i` (Linux) or `sed -i ""` (macOS) — detect via `uname`. Refuses to run if working tree is dirty (`git status --porcelain` non-empty).
- `tests/test_bump_version.sh` — NEW — bash test (~50 LOC) that copies the four `pyproject.toml` files + `app.conf` to a temp dir, invokes `bump_version.sh 9.9.9` with the temp dir as cwd, verifies the regex `version = "9.9.9"` appears in all 5 files post-run, and cleans up. Wrapped in `bats` if available, else plain bash with `set -euo pipefail`.
- `tests/test_release_workflow_structure.py` — NEW — pytest module with minimum 5 test cases that parse `.github/workflows/release.yml` as YAML and assert: (a) trigger is `push.tags: ['v*.*.*']`; (b) `permissions.id-token == 'write'`; (c) `sigstore/gh-action-sigstore-python` step exists in `build-and-sign`; (d) `softprops/action-gh-release@v2` step in `gh-release` has `generate_release_notes: true`; (e) `prerelease` expression contains both `rc` and `alpha` literals.

The coding agent must NOT modify files outside this map without re-checking CLAUDE.md.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given `.github/workflows/release.yml` exists
When  `python -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml'))"` runs
Then  exit code is 0 (valid YAML)

Given the workflow file content
When  `grep -E "tags:.*\['v\*\.\*\.\*'\]" .github/workflows/release.yml` runs
Then  the count is `1`

Given the workflow file content
When  `grep "id-token: write" .github/workflows/release.yml` runs
Then  the count is `1`

Given the workflow file content
When  `grep "sigstore/gh-action-sigstore-python" .github/workflows/release.yml` runs
Then  the count is `1`

Given the workflow file content
When  `grep "generate_release_notes: true" .github/workflows/release.yml` runs
Then  the count is `1`

Given `scripts/bump_version.sh` exists and is executable
When  `bash tests/test_bump_version.sh` runs
Then  exit code is 0

Given `uv run pytest tests/test_release_workflow_structure.py` runs
When  the run completes
Then  exit code is 0
And   stdout contains `5 passed`

Given a tag `v0.0.0-test` is pushed (in a sandbox repo or local-only)
When  the release workflow runs
Then  the `build-and-sign` job produces 4 `.whl` artifacts + 1 `.tgz` artifact
And   each artifact has a corresponding sigstore bundle (`.sigstore` extension) in the uploaded artifacts

Given a working tree that has uncommitted changes
When  `bash scripts/bump_version.sh 0.1.0` runs
Then  exit code is non-zero
And   stderr contains `working tree dirty` or similar

Given `wc -l scripts/bump_version.sh | awk '{print $1}'` runs
When  the output is checked
Then  the value is < 400
```

---

## Shell verification

The coding agent runs this end-to-end locally before opening a PR:

```bash
set -euo pipefail

# 1. Workflow YAML valid + structural greps
test -f .github/workflows/release.yml
python -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml'))"
grep -E "tags:.*\['v\*\.\*\.\*'\]" .github/workflows/release.yml
grep -q 'id-token: write' .github/workflows/release.yml
grep -q 'sigstore/gh-action-sigstore-python' .github/workflows/release.yml
grep -q 'generate_release_notes: true' .github/workflows/release.yml

# 2. bump_version.sh works on a temp copy + refuses dirty trees
bash tests/test_bump_version.sh
echo "test dirt" > /tmp/__aegis_dirty_test
git add -A 2>/dev/null || true
if bash scripts/bump_version.sh 0.0.99 2>/dev/null; then
  echo "FAIL: bump_version did not refuse dirty tree"; exit 1
fi
git restore --staged . 2>/dev/null || true
rm -f /tmp/__aegis_dirty_test

# 3. Pytest covers workflow structure
uv run pytest tests/test_release_workflow_structure.py -v
uv run pytest tests/test_release_workflow_structure.py -q | grep -q '5 passed'

# 4. LOC under cap
test "$(grep -cvE '^\s*(#|$)' scripts/bump_version.sh)" -lt 400

# 5. Release doc exists with required sections
for section in "Version bump" "Signature verification" "Rollback"; do
  grep -q "$section" docs/ops/release-process.md
done

# 6. (Manual / sandbox repo) End-to-end smoke: push a test tag in a fork
# git tag v0.0.0-sandboxtest && git push origin v0.0.0-sandboxtest
# gh run watch --exit-status
# Then delete: gh release delete v0.0.0-sandboxtest -y && git push origin :refs/tags/v0.0.0-sandboxtest

# 7. Regular CI on the PR introducing this story still passes
git push origin HEAD
gh run watch --exit-status
```

All non-manual blocks must exit 0. The manual block (step 6) is documented in `docs/ops/release-process.md` for Abu to execute when shipping v0.1.0.

---

## Notes for coding agent

- Per `docs/cicd-spec.md` § "release.yml" line 280, the release pipeline is informational-only (not required for merge to `main`) — but it must work end-to-end before EPIC-12 ships Splunkbase artifacts.
- `permissions: id-token: write` is REQUIRED for sigstore OIDC token issuance — without it, `sigstore/gh-action-sigstore-python@v3.0.0` errors. The job also needs `contents: write` to upload to GitHub Releases.
- Per `docs/cicd-spec.md` line 466, `PYPI_API_TOKEN` is listed as "deferred to v0.2" — this story does NOT publish to PyPI. The `release.yml` produces GitHub-Release-hosted wheels only. Add a `# TODO(v0.2): publish to PyPI once Abu approves package namespace` comment in the workflow.
- `softprops/action-gh-release@v2` with `generate_release_notes: true` uses GitHub's auto-generation, which honors `.github/release.yml` config if present (not in this story). Conventional-commit-shaped commit messages get cleaner notes — note this in `docs/ops/release-process.md` and recommend `feat: …`, `fix: …`, `chore: …`, `docs: …` prefixes (consistent with the auto-generated `commit -m "chore(release): bump to vX.Y.Z"` from `bump_version.sh`).
- The `prerelease: ${{ contains(github.ref_name, 'rc') || contains(github.ref_name, 'alpha') }}` expression is verbatim from spec line 331. Tags like `v0.1.0-rc1` mark as prerelease; `v0.1.0` ships as full release. Do not add `beta` to the predicate without an ADR (we choose `rc` + `alpha` as the two pre-release channels).
- `uv build --all-packages --out-dir dist/` (spec line 305) builds all 4 wheels in one invocation — same artifacts as the matrix build in `ci.yml` but produced in a single tagged run. This is intentional (the release pipeline must produce a coherent batch; matrix parallelism in CI is for speed, not for releases).
- The `.tgz` filename pattern is `aegis_app-${{ github.ref_name }}.tgz` (spec line 306) — uses the tag name (e.g., `aegis_app-v0.1.0.tgz`). This differs from `ci.yml`'s `aegis_app-$(git rev-parse --short HEAD).tgz` (commit SHA). Both are intentional.
- Per `../../../context/05-splunk-core/09-appinspect.md`, Splunkbase requires the `.tgz` filename to match `<app_id>-<version>.tgz`. `v0.1.0` (with the `v` prefix) is NOT Splunkbase-compliant — Splunkbase expects `aegis_app-0.1.0.tgz` (no `v`). EPIC-12 story `story-app-12-splunkbase-submission-package-and-checklist.md` handles the rename for Splunkbase upload; the GitHub Release `.tgz` keeps the `v` for consistency with the tag. Document this divergence in `docs/ops/release-process.md`.
- `bump_version.sh` is the only place version numbers get bumped — DO NOT scatter `sed` calls in CI. Cross-platform sed: `sed_inplace() { if [[ "$(uname)" == "Darwin" ]]; then sed -i ""  "$@"; else sed -i "$@"; fi }`.
- Per ADR-002, the monorepo uses uv workspaces — every package gets the same version per release (no independent versioning yet). Document this constraint in `docs/ops/release-process.md`; revisit in v0.2 if surfaces need independent release cadence.
- The `tests/test_bump_version.sh` test copies fixtures to `/tmp/aegis_bump_test_$$/` (PID suffix for isolation), invokes the script with `--cwd` or by `cd`-ing inside a subshell, then `grep -q 'version = "9.9.9"'` across the 5 fixture files. Use `mktemp -d` for atomic temp dir creation.
- sigstore signing on first run can take ~30-60s (cert provisioning). Workflow `timeout-minutes` should be at least 15 — set to 20 to be safe (spec doesn't pin this; pick 20).
- Per `../../../context/11-prior-art/01-build-a-thon-2025-deep-read.md`, no 2025 winner shipped signed artifacts via sigstore — this differentiates Aegis's submission as production-shape. Mention in the README (EPIC-11) under a "Provenance" section.
