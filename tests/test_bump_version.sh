#!/usr/bin/env bash
# Tests scripts/bump_version.sh against a fixture copy of the version files.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
SCRIPT="${REPO_ROOT}/scripts/bump_version.sh"
TMP="$(mktemp -d -t splunkgate_bump_test.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

# Copy the 4 pyproject.toml + app.conf into a fresh git repo so the script's
# `working tree dirty` + `git commit` paths can run without polluting the
# real working tree.
mkdir -p "$TMP/packages/splunkgate_core" \
         "$TMP/packages/splunkgate_judges" \
         "$TMP/packages/splunkgate_mw" \
         "$TMP/packages/splunkgate_mcp" \
         "$TMP/splunk_apps/splunkgate_app/default"

for pkg in splunkgate_core splunkgate_judges splunkgate_mw splunkgate_mcp; do
    cp "${REPO_ROOT}/packages/${pkg}/pyproject.toml" "$TMP/packages/${pkg}/"
done
cp "${REPO_ROOT}/splunk_apps/splunkgate_app/default/app.conf" "$TMP/splunk_apps/splunkgate_app/default/"

cd "$TMP"
git init -q
git config user.email "ci@splunkgate.test"
git config user.name "ci"
git add -A
git commit -q -m "fixture seed"

# Sanity check: pre-bump, no file mentions 9.9.9.
if grep -r 'version = "9.9.9"\|version = 9.9.9' packages splunk_apps >/dev/null 2>&1; then
    echo "FAIL: fixture already has 9.9.9 — test setup broken" >&2
    exit 1
fi

# Bump.
bash "$SCRIPT" 9.9.9

# Every pyproject.toml has `version = "9.9.9"` exactly.
for pkg in splunkgate_core splunkgate_judges splunkgate_mw splunkgate_mcp; do
    if ! grep -q '^version = "9.9.9"$' "packages/${pkg}/pyproject.toml"; then
        echo "FAIL: ${pkg} pyproject.toml did not bump" >&2
        exit 1
    fi
done

# app.conf has `version = 9.9.9` (no quotes per Splunk conf syntax).
if ! grep -q '^version = 9.9.9$' splunk_apps/splunkgate_app/default/app.conf; then
    echo "FAIL: app.conf did not bump" >&2
    exit 1
fi

# A commit landed with the expected message.
if ! git log -1 --pretty=%B | grep -q '^chore(release): bump to v9.9.9$'; then
    echo "FAIL: commit message did not match" >&2
    exit 1
fi

# Dirty-tree refusal: stash a junk file + verify exit non-zero.
echo "dirt" > junk.txt
git add junk.txt
if bash "$SCRIPT" 8.8.8 2>/dev/null; then
    echo "FAIL: bump did not refuse on dirty tree" >&2
    exit 1
fi

echo "test_bump_version OK"
