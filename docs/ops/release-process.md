# Release process

Tag-triggered, sigstore-signed releases for SplunkGate. Single source of
truth for `vX.Y.Z` cuts.

## Version bump

`scripts/bump_version.sh` is the canonical bumper. It updates **five
files in lockstep**:

- `packages/splunkgate_core/pyproject.toml`
- `packages/splunkgate_judges/pyproject.toml`
- `packages/splunkgate_mw/pyproject.toml`
- `packages/splunkgate_mcp/pyproject.toml`
- `splunk_apps/splunkgate_app/default/app.conf` (`[launcher] version = ...`)

```bash
# From a CLEAN working tree:
bash scripts/bump_version.sh 0.1.0
```

The script refuses to run on a dirty tree. It commits with the message
`chore(release): bump to v<VERSION>` so the auto-generated changelog
(`softprops/action-gh-release@v2 generate_release_notes: true`) renders
the bump cleanly.

Per ADR-002, the monorepo uses uv workspaces — **every package gets the
same version per release**. Independent versioning is a v0.2 decision.

## Cutting a release

```bash
# 1. Bump
bash scripts/bump_version.sh 0.1.0

# 2. Sign the tag (GPG / SSH-signed per Abu's git config)
git tag -s v0.1.0 -m "v0.1.0"

# 3. Push branch + tag
git push origin main
git push origin v0.1.0
```

The push of `v0.1.0` fires `.github/workflows/release.yml`. The pipeline:

1. Builds all 4 wheels via `uv build --all-packages`.
2. Builds the Splunk app `.tgz` (named `splunkgate_app-v0.1.0.tgz`).
3. Sigstore-signs every artifact (`.whl.sigstore` and `.tgz.sigstore`
   bundles land alongside the inputs).
4. Creates a GitHub Release with auto-generated release notes from
   conventional-commit messages.

`-rc` and `-alpha` suffixes mark the Release as pre-release.

## Signature verification

```bash
# Install the verifier
pip install sigstore

# Verify any artifact:
sigstore verify identity \
  --bundle splunkgate_core-0.1.0-py3-none-any.whl.sigstore \
  --cert-identity https://github.com/Blockchain-Oracle/splunkgate/.github/workflows/release.yml@refs/tags/v0.1.0 \
  --cert-oidc-issuer https://token.actions.githubusercontent.com \
  splunkgate_core-0.1.0-py3-none-any.whl
```

## Rollback

```bash
gh release delete v0.1.0 --yes
git push origin :refs/tags/v0.1.0
```

If the tag has been consumed by a downstream (Splunkbase upload,
Anthropic sandbox install, README link), rollback requires a follow-up
`v0.1.1` rather than a retag.

## Splunkbase divergence

Splunkbase expects `<app_id>-<version>.tgz` (e.g.
`splunkgate_app-0.1.0.tgz`, no `v`). The GitHub Release tarball uses
the `v` prefix (`splunkgate_app-v0.1.0.tgz`) for consistency with the
git tag. **EPIC-12** (`story-app-12-splunkbase-submission-package-and-checklist`)
owns the rename + manual upload to Splunkbase.

## What's NOT here

- **PyPI publish** — deferred to v0.2 (see `TODO(v0.2)` in
  `.github/workflows/release.yml`). The GitHub Release page is the
  canonical wheel distribution for v0.1.x.
- **Splunkbase auto-submission** — EPIC-12, manual.

## Conventional-commit guidance

Auto-generated release notes group commits by type. Use
`feat: …`, `fix: …`, `chore: …`, `docs: …`, `refactor: …`, `test: …`
prefixes so each section renders cleanly.
