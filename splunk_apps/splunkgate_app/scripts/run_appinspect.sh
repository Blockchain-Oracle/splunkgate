#!/usr/bin/env bash
# SplunkGate AppInspect runner.
#
# Single source of truth for invoking splunk-appinspect against the
# packaged SplunkGate app. Mirrors the canonical invocation from
# context/05-splunk-core/09-appinspect.md verbatim. Used by both local
# devs ("does my change still pass?") and CI (story-cicd-05 gate).
#
# Contract:
#   - exits 0 iff zero error-severity findings outside .appinspect.expect.yaml
#   - writes appinspect-report.json + appinspect-summary.txt next to itself
#   - hard-fails if splunk-appinspect < 4.2.1 (per docs/architecture.md)
#
# Env overrides:
#   APP_DIR         path to app root (default: derived from script location)
#   OUTPUT_DIR      where the JSON + summary land (default: $PWD)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${APP_DIR:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
OUTPUT_DIR="${OUTPUT_DIR:-$PWD}"
REPORT="${OUTPUT_DIR}/appinspect-report.json"

mkdir -p "${OUTPUT_DIR}"

# --- Version gate ---------------------------------------------------------
# splunk-appinspect 4.2.1 is the floor per docs/architecture.md. Older
# releases miss the cloud-mode tag set and silently skip the strictest
# checks; we hard-fail to keep CI honest.
if ! command -v splunk-appinspect >/dev/null 2>&1; then
  if ! uv run splunk-appinspect --version >/dev/null 2>&1; then
    echo "splunk-appinspect not installed. Install via: uv add --dev splunk-appinspect" >&2
    exit 2
  fi
  RUNNER=(uv run splunk-appinspect)
else
  RUNNER=(splunk-appinspect)
fi

INSTALLED=$("${RUNNER[@]}" --version 2>&1 | head -n1 | awk '{print $NF}' | tr -d '\r')
# Loud-fail on parse miss (e.g. corrupt venv that prints nothing or a banner
# instead of a version). Avoids a cryptic InvalidVersion traceback below.
if [ -z "${INSTALLED}" ] || ! [[ "${INSTALLED}" =~ ^[0-9] ]]; then
  echo "could not parse splunk-appinspect version: '${INSTALLED}'" >&2
  exit 2
fi
# Pass the version through the environment to avoid bash-into-Python source
# interpolation; the closing `'PY'` quotes disable heredoc interpolation.
INSTALLED="${INSTALLED}" uv run python - <<'PY'
import os
import sys

from packaging.version import Version

installed = os.environ["INSTALLED"]
if Version(installed) < Version("4.2.1"):
    sys.stderr.write(f"splunk-appinspect {installed} too old; need >= 4.2.1\n")
    sys.exit(2)
PY

# --- Inspect --------------------------------------------------------------
# Canonical invocation per context/05-splunk-core/09-appinspect.md.
# --excluded-tags manual short-circuits the 25 items we acknowledge in
# .appinspect.manualcheck.yaml.
"${RUNNER[@]}" inspect "${APP_DIR}" \
  --mode test \
  --included-tags cloud \
  --excluded-tags manual \
  --output-file "${REPORT}" \
  --data-format json

# --- Postprocess ----------------------------------------------------------
# Walks the JSON, separates by result, fails if any unsuppressed error.
exec uv run python "${SCRIPT_DIR}/_appinspect_postprocess.py" \
  "${REPORT}" \
  --expect-file "${APP_DIR}/.appinspect.expect.yaml" \
  --summary-file "${OUTPUT_DIR}/appinspect-summary.txt"
