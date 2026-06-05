#!/usr/bin/env bash
# Aegis AppInspect runner.
#
# Single source of truth for invoking splunk-appinspect against the
# packaged Aegis app. Mirrors the canonical invocation from
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

INSTALLED=$("${RUNNER[@]}" --version 2>&1 | awk '{print $NF}' | tr -d '\r')
uv run python - <<PY
from packaging.version import Version
import sys
installed = "${INSTALLED}"
if Version(installed) < Version("4.2.1"):
    sys.stderr.write(f"splunk-appinspect ${INSTALLED} too old; need >= 4.2.1\n")
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
