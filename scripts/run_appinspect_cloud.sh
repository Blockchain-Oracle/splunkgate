#!/usr/bin/env bash
# Run AppInspect with the private_victoria tag — gate for Splunk Cloud deploy.
#
# Splunk Cloud (Victoria stack) REJECTS uploads that don't pass AppInspect's
# `private_victoria` tag set on the splunk.com appinspect.splunk.com service.
# This script does the full round-trip:
#
#   1. POST tarball to appinspect.splunk.com/v1/app/validate
#   2. Poll status until SUCCESS / FAILURE
#   3. Fetch report, fail script if errors/failures > 0
#   4. Print the AppInspect token (Authorization header for ACS deploy)
#
# Requires SPLUNK_COM_USERNAME + SPLUNK_COM_PASSWORD env vars (your splunk.com
# SSO login — same account you use for Splunkbase / docs / support).
#
# Output: appinspect-token.txt with the token to pass to deploy_to_splunk_cloud.sh
#         appinspect-report.json with the full validation report.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARBALL="${REPO_ROOT}/dist/splunkgate_app-1.0.0.tgz"
APPINSPECT_BASE="https://appinspect.splunk.com/v1"
OUT_DIR="${REPO_ROOT}/dist"

# --- Pre-flight ---
if [ ! -f "${TARBALL}" ]; then
  echo "tarball not found at ${TARBALL}" >&2
  echo "run: bash scripts/build_splunk_app_tgz.sh" >&2
  exit 2
fi
if [ -z "${SPLUNK_COM_USERNAME:-}" ] || [ -z "${SPLUNK_COM_PASSWORD:-}" ]; then
  echo "set SPLUNK_COM_USERNAME and SPLUNK_COM_PASSWORD (your splunk.com SSO)" >&2
  exit 2
fi

# --- Step 1: login to appinspect.splunk.com to mint a session token ---
echo "[1/4] logging in to appinspect.splunk.com as ${SPLUNK_COM_USERNAME}"
LOGIN_RESP=$(curl -fsSL -X GET \
  --user "${SPLUNK_COM_USERNAME}:${SPLUNK_COM_PASSWORD}" \
  "${APPINSPECT_BASE}/login")
SESSION_TOKEN=$(echo "${LOGIN_RESP}" | uv run python -c "import sys,json;print(json.load(sys.stdin)['data']['token'])")
if [ -z "${SESSION_TOKEN}" ]; then
  echo "failed to mint AppInspect session token" >&2
  exit 1
fi

# --- Step 2: submit the tarball ---
echo "[2/4] submitting ${TARBALL} for validation (tag: private_victoria)"
SUBMIT_RESP=$(curl -fsSL -X POST \
  -H "Authorization: bearer ${SESSION_TOKEN}" \
  -F "app_package=@${TARBALL}" \
  -F "included_tags=private_victoria" \
  "${APPINSPECT_BASE}/app/validate")
REQUEST_ID=$(echo "${SUBMIT_RESP}" | uv run python -c "import sys,json;print(json.load(sys.stdin)['request_id'])")
echo "    request_id: ${REQUEST_ID}"

# --- Step 3: poll until SUCCESS or FAILURE ---
echo "[3/4] polling validation status"
for i in $(seq 1 60); do
  STATUS_RESP=$(curl -fsSL -X GET \
    -H "Authorization: bearer ${SESSION_TOKEN}" \
    "${APPINSPECT_BASE}/app/validate/status/${REQUEST_ID}")
  STATUS=$(echo "${STATUS_RESP}" | uv run python -c "import sys,json;print(json.load(sys.stdin)['status'])")
  echo "    [${i}/60] status=${STATUS}"
  if [ "${STATUS}" = "SUCCESS" ]; then
    break
  fi
  if [ "${STATUS}" = "FAILURE" ]; then
    echo "AppInspect FAILURE — see full report" >&2
    echo "${STATUS_RESP}" >&2
    exit 1
  fi
  sleep 5
done

# --- Step 4: fetch the report + verify no errors/failures ---
echo "[4/4] fetching report"
curl -fsSL -X GET \
  -H "Authorization: bearer ${SESSION_TOKEN}" \
  -H "Accept: application/json" \
  "${APPINSPECT_BASE}/app/report/${REQUEST_ID}" \
  > "${OUT_DIR}/appinspect-report.json"

uv run python - <<PY
import json
report = json.load(open("${OUT_DIR}/appinspect-report.json"))
info = report.get("info", {})
n_error = info.get("error", 0)
n_failure = info.get("failure", 0)
n_manual = info.get("manual_check", 0)
print(f"summary: errors={n_error} failures={n_failure} manual_checks={n_manual} "
      f"success={info.get('success', 0)} not_applicable={info.get('not_applicable', 0)}")
if n_error or n_failure:
    print("\nFAILED — see appinspect-report.json for details")
    raise SystemExit(1)
print("OK — ready for Splunk Cloud deploy")
PY

# Save the AppInspect token so deploy_to_splunk_cloud.sh can pick it up.
echo "${SESSION_TOKEN}" > "${OUT_DIR}/appinspect-token.txt"
chmod 600 "${OUT_DIR}/appinspect-token.txt"
echo ""
echo "AppInspect token written to ${OUT_DIR}/appinspect-token.txt"
echo "Pass to deploy_to_splunk_cloud.sh as SPLUNK_COM_APPINSPECT_TOKEN env var."
