#!/usr/bin/env bash
# bump_version.sh — bumps SemVer across all 4 packages + the Splunk app.conf.
#
# Single source of truth for release version updates. Refuses to run on a
# dirty working tree so the resulting commit is atomic. Cross-platform
# sed via uname detection.
set -euo pipefail

if [[ "$#" -ne 1 ]]; then
    echo "usage: $0 <semver>" >&2
    echo "example: $0 0.1.0" >&2
    exit 2
fi

VERSION="$1"

if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?$ ]]; then
    echo "bump_version FAIL: '$VERSION' is not a valid SemVer (X.Y.Z[-suffix])" >&2
    exit 2
fi

if [[ -n "$(git status --porcelain 2>/dev/null || true)" ]]; then
    echo "bump_version FAIL: working tree dirty — commit or stash first" >&2
    exit 1
fi

# Cross-platform in-place sed.
sed_inplace() {
    if [[ "$(uname)" == "Darwin" ]]; then
        sed -i "" "$@"
    else
        sed -i "$@"
    fi
}

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

PYPROJECTS=(
    "packages/splunkgate_core/pyproject.toml"
    "packages/splunkgate_judges/pyproject.toml"
    "packages/splunkgate_mw/pyproject.toml"
    "packages/splunkgate_mcp/pyproject.toml"
)
APP_CONF="splunk_apps/splunkgate_app/default/app.conf"

for f in "${PYPROJECTS[@]}"; do
    if [[ ! -f "$f" ]]; then
        echo "bump_version FAIL: $f missing" >&2
        exit 1
    fi
    # Assert the regex will match BEFORE editing — a future `dynamic = [...]`
    # or differently-indented version line would otherwise sed-noop silently.
    if ! grep -qE '^version = ".*"' "$f"; then
        echo "bump_version FAIL: $f has no '^version = \"...\"' line (dynamic versioning?)" >&2
        exit 1
    fi
    sed_inplace -E "s|^version = \".*\"|version = \"${VERSION}\"|" "$f"
    # Belt-and-suspenders: assert the file actually changed to the target version.
    if ! grep -qE "^version = \"${VERSION}\"$" "$f"; then
        echo "bump_version FAIL: sed did not update $f to $VERSION" >&2
        exit 1
    fi
done

if [[ -f "$APP_CONF" ]]; then
    if ! grep -qE '^version = .*' "$APP_CONF"; then
        echo "bump_version FAIL: $APP_CONF has no '^version = ...' line" >&2
        exit 1
    fi
    sed_inplace -E "s|^version = .*|version = ${VERSION}|" "$APP_CONF"
    if ! grep -qE "^version = ${VERSION}$" "$APP_CONF"; then
        echo "bump_version FAIL: sed did not update $APP_CONF to $VERSION" >&2
        exit 1
    fi
else
    echo "bump_version WARN: $APP_CONF missing — Splunk app version not bumped" >&2
fi

git add "${PYPROJECTS[@]}" "$APP_CONF" 2>/dev/null || git add "${PYPROJECTS[@]}"
git commit -m "chore(release): bump to v${VERSION}"

echo "bump_version OK: v${VERSION} committed across $((${#PYPROJECTS[@]} + 1)) files"
