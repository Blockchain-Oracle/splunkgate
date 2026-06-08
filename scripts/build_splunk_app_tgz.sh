#!/usr/bin/env bash
# Splunkbase artifact builder.
#
# Produces dist/splunkgate_app-<version>.tgz from splunk_apps/splunkgate_app/.
# Version is read from default/app.conf so the manifest, tarball name,
# and shell output all reference the same source of truth.
#
# Determinism: macOS BSD tar lacks --mtime / --sort flags, so this
# script delegates to scripts/_pack_tarball.py (Python tarfile) which
# is byte-stable across OS at a pinned Python version. AppInspect
# preflight is gated on splunk-appinspect installation; absence is
# loud (exit 2 with install hint) per story-app-11 semantics.
#
# Output to stdout:
#   - SHA-256 of the artifact (matches what Splunkbase + the verify
#     script consume)
#   - Size in bytes
#
# Env overrides:
#   REPO_ROOT  default: derived from script location
#   DIST_DIR   default: ${REPO_ROOT}/dist
#   SKIP_APPINSPECT  default: 0; set to 1 to skip the preflight (CI may
#                    run AppInspect separately so the build step stays
#                    fast on every push)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${REPO_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
DIST_DIR="${DIST_DIR:-${REPO_ROOT}/dist}"
APP_SRC="${REPO_ROOT}/splunk_apps/splunkgate_app"
APP_CONF="${APP_SRC}/default/app.conf"
SKIP_APPINSPECT="${SKIP_APPINSPECT:-0}"

if [ ! -f "${APP_CONF}" ]; then
  echo "missing ${APP_CONF}" >&2
  exit 2
fi

# Parse version from app.conf — single source of truth.
VERSION=$(awk -F= '/^version[[:space:]]*=/ {gsub(/[[:space:]]/,"",$2); print $2; exit}' "${APP_CONF}")
if [ -z "${VERSION}" ] || ! [[ "${VERSION}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "could not parse semver version from app.conf: '${VERSION}'" >&2
  exit 2
fi

# Manifest version must match app.conf — fail loud if they drift.
MANIFEST="${APP_SRC}/META-INF/manifest.json"
if [ -f "${MANIFEST}" ]; then
  MANIFEST_VERSION=$(uv run python -c "import json; print(json.load(open('${MANIFEST}'))['info']['version'])")
  if [ "${MANIFEST_VERSION}" != "${VERSION}" ]; then
    echo "manifest.json version '${MANIFEST_VERSION}' != app.conf version '${VERSION}'" >&2
    exit 2
  fi
fi

# AppInspect preflight (story-app-11 semantics: zero unsuppressed errors).
# Silent skip is forbidden: if the runner is missing AND the bypass flag is
# not explicitly set, refuse to build rather than ship an unchecked artifact.
if [ "${SKIP_APPINSPECT}" != "1" ]; then
  if [ -x "${APP_SRC}/scripts/run_appinspect.sh" ]; then
    echo "running AppInspect preflight..."
    OUTPUT_DIR="${DIST_DIR}" bash "${APP_SRC}/scripts/run_appinspect.sh" || {
      echo "AppInspect preflight failed; refusing to build artifact" >&2
      exit 1
    }
  else
    echo "AppInspect runner not found at ${APP_SRC}/scripts/run_appinspect.sh" >&2
    echo "  install splunk-appinspect or set SKIP_APPINSPECT=1 to bypass" >&2
    exit 2
  fi
fi

mkdir -p "${DIST_DIR}"
ARTIFACT="${DIST_DIR}/splunkgate_app-${VERSION}.tgz"
echo "packing ${APP_SRC} -> ${ARTIFACT}"
uv run python "${SCRIPT_DIR}/_pack_tarball.py" \
  --source "${APP_SRC}" \
  --top-level splunkgate_app \
  --output "${ARTIFACT}"

# sha256 + size — both feed the Splunkbase upload + the verify script.
if command -v sha256sum >/dev/null 2>&1; then
  SHA=$(sha256sum "${ARTIFACT}" | awk '{print $1}')
else
  SHA=$(shasum -a 256 "${ARTIFACT}" | awk '{print $1}')
fi
SIZE=$(wc -c < "${ARTIFACT}" | tr -d ' ')

echo "artifact: ${ARTIFACT}"
echo "sha256:   ${SHA}"
echo "size:     ${SIZE} bytes"
