#!/usr/bin/env bash
# Verify a Splunkbase artifact end-to-end.
#
# Used by:
#   - Local dev as the gate after `build_splunk_app_tgz.sh`
#   - CI release lane (story-cicd-08) before publishing a GitHub Release
#
# Steps:
#   1. tarball exists and is a valid gzip
#   2. extracts cleanly into a temp dir
#   3. top-level dir is splunkgate_app/ (Splunk convention)
#   4. required files present: default/app.conf, README, LICENSE,
#      META-INF/manifest.json
#   5. no dev cruft (no __pycache__, no .pyc, no tests/)
#   6. manifest.json info.version matches default/app.conf version
#   7. AppInspect (if installed) passes against the extracted tree
#
# Usage:
#   bash scripts/verify_splunkbase_artifact.sh dist/splunkgate_app-1.0.0.tgz
set -euo pipefail

ARTIFACT="${1:-}"
if [ -z "${ARTIFACT}" ] || [ ! -f "${ARTIFACT}" ]; then
  echo "usage: $0 <path/to/splunkgate_app-VERSION.tgz>" >&2
  exit 2
fi

# 1. gzip header check
file "${ARTIFACT}" | grep -q "gzip compressed" || {
  echo "${ARTIFACT} is not a gzip file" >&2
  exit 1
}

# 2. Extract into a temp dir we clean on exit.
TMPDIR_EXTRACT=$(mktemp -d)
trap 'rm -rf "${TMPDIR_EXTRACT}"' EXIT
tar -xzf "${ARTIFACT}" -C "${TMPDIR_EXTRACT}"

# 3. Top-level dir
APP_ROOT="${TMPDIR_EXTRACT}/splunkgate_app"
if [ ! -d "${APP_ROOT}" ]; then
  echo "artifact does not have splunkgate_app/ as top-level directory" >&2
  exit 1
fi

# 4. Required files
REQUIRED=(
  "default/app.conf"
  "README"
  "LICENSE"
  "RELEASE_NOTES.md"
  "META-INF/manifest.json"
)
for path in "${REQUIRED[@]}"; do
  if [ ! -f "${APP_ROOT}/${path}" ]; then
    echo "missing required file: splunkgate_app/${path}" >&2
    exit 1
  fi
done

# 5. No dev cruft or operations tooling — scripts/ and tests/ are dev-only
# and must NOT ship inside the Splunkbase tarball.
if find "${APP_ROOT}" \( -name "__pycache__" -o -name "*.pyc" -o -name ".DS_Store" -o -name "tests" -o -name "scripts" \) | grep -q .; then
  echo "artifact contains dev cruft / operations tooling:" >&2
  find "${APP_ROOT}" \( -name "__pycache__" -o -name "*.pyc" -o -name ".DS_Store" -o -name "tests" -o -name "scripts" \) >&2
  exit 1
fi

# 6. Manifest <-> app.conf version match
MANIFEST_VERSION=$(uv run python -c "import json; print(json.load(open('${APP_ROOT}/META-INF/manifest.json'))['info']['version'])")
APP_VERSION=$(awk -F= '/^version[[:space:]]*=/ {gsub(/[[:space:]]/,"",$2); print $2; exit}' "${APP_ROOT}/default/app.conf")
if [ "${MANIFEST_VERSION}" != "${APP_VERSION}" ]; then
  echo "manifest.json version '${MANIFEST_VERSION}' != app.conf version '${APP_VERSION}'" >&2
  exit 1
fi

# 7. AppInspect re-run on the extracted tree (best effort; only if
# splunk-appinspect is installed). Invoked inline rather than via the
# packaged scripts/run_appinspect.sh because the tarball intentionally
# omits scripts/ — the runner lives at the repo root for ops use.
if command -v splunk-appinspect >/dev/null 2>&1 || uv run splunk-appinspect --version >/dev/null 2>&1; then
  echo "running AppInspect on extracted tree..."
  if command -v splunk-appinspect >/dev/null 2>&1; then
    APPINSPECT=(splunk-appinspect)
  else
    APPINSPECT=(uv run splunk-appinspect)
  fi
  # Version floor 4.2.1 per docs/architecture.md — older releases miss
  # the cloud-mode tag set and silently skip the strictest checks.
  # Mirrors the gate in splunk_apps/splunkgate_app/scripts/run_appinspect.sh
  # (re-asserted here because the tarball intentionally omits scripts/).
  INSTALLED=$("${APPINSPECT[@]}" --version 2>&1 | head -n1 | awk '{print $NF}' | tr -d '\r')
  if [ -z "${INSTALLED}" ] || ! [[ "${INSTALLED}" =~ ^[0-9] ]]; then
    echo "could not parse splunk-appinspect version: '${INSTALLED}'" >&2
    exit 2
  fi
  INSTALLED="${INSTALLED}" uv run python - <<'PY'
import os
import sys

from packaging.version import Version

installed = os.environ["INSTALLED"]
if Version(installed) < Version("4.2.1"):
    sys.stderr.write(f"splunk-appinspect {installed} too old; need >= 4.2.1\n")
    sys.exit(2)
PY
  "${APPINSPECT[@]}" inspect "${APP_ROOT}" \
    --mode test \
    --included-tags cloud \
    --excluded-tags manual \
    --output-file "${TMPDIR_EXTRACT}/appinspect-report.json" \
    --data-format json
fi

echo "OK: ${ARTIFACT} passed all checks"
