#!/usr/bin/env bash
# Deploy splunkgate_app-1.0.0.tgz to Splunk Cloud via the Admin Configuration
# Service (ACS) API.
#
# Splunk Cloud (Victoria stack v10.4+) removed the "Install app from file"
# UI; private apps deploy through ACS only. The two-token flow:
#
#   1. ACS authenticates with a JWT minted INSIDE your stack's Splunk Web at
#      https://prd-p-t9irr.splunkcloud.com -> Settings -> Tokens
#      (capability: edit_all_tokens; sc_admin has it by default).
#
#   2. AppInspect cert from appinspect.splunk.com (your splunk.com SSO).
#      Get this via: bash scripts/run_appinspect_cloud.sh
#
# Required env vars:
#   SPLUNKGATE_STACK_NAME        — e.g. "prd-p-t9irr" (no .splunkcloud.com)
#   SPLUNKGATE_CLOUD_JWT         — the Splunk Cloud JWT from Settings -> Tokens
#   SPLUNK_COM_APPINSPECT_TOKEN  — from dist/appinspect-token.txt (run_appinspect_cloud.sh)
#
# Usage:
#   bash scripts/run_appinspect_cloud.sh                  # step 1: AppInspect cert
#   export SPLUNKGATE_CLOUD_JWT="<token from Splunk Web>"
#   export SPLUNKGATE_STACK_NAME="prd-p-t9irr"
#   export SPLUNK_COM_APPINSPECT_TOKEN="$(cat dist/appinspect-token.txt)"
#   bash scripts/deploy_to_splunk_cloud.sh                # step 2: actual deploy
#
# Per Splunk docs:
#   https://help.splunk.com/en/splunk-cloud-platform/administer/admin-config-service-manual/10.3.2512/administer-splunk-cloud-platform-using-the-admin-config-service-acs-api/manage-private-apps-in-splunk-cloud-platform

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARBALL="${REPO_ROOT}/dist/splunkgate_app-1.0.0.tgz"

# --- Pre-flight ---
if [ ! -f "${TARBALL}" ]; then
  echo "tarball not found at ${TARBALL}" >&2
  exit 2
fi
: "${SPLUNKGATE_STACK_NAME:?set SPLUNKGATE_STACK_NAME (e.g. prd-p-t9irr)}"
: "${SPLUNKGATE_CLOUD_JWT:?set SPLUNKGATE_CLOUD_JWT (mint at Splunk Web -> Settings -> Tokens)}"
: "${SPLUNK_COM_APPINSPECT_TOKEN:?set SPLUNK_COM_APPINSPECT_TOKEN (run scripts/run_appinspect_cloud.sh first)}"

ACS_URL="https://admin.splunk.com/${SPLUNKGATE_STACK_NAME}/adminconfig/v2/apps/victoria"

# --- Verify the stack is reachable (cheap GET) ---
echo "[1/2] verifying stack is reachable: ${SPLUNKGATE_STACK_NAME}"
HTTP_CODE=$(curl -ks -o /dev/null -w "%{http_code}" \
  "https://admin.splunk.com/${SPLUNKGATE_STACK_NAME}/adminconfig/v2/info" \
  -H "Authorization: Bearer ${SPLUNKGATE_CLOUD_JWT}")
case "${HTTP_CODE}" in
  200) echo "    stack reachable" ;;
  401|403) echo "JWT invalid or expired (HTTP ${HTTP_CODE})" >&2; exit 1 ;;
  404) echo "stack not found: ${SPLUNKGATE_STACK_NAME} (HTTP 404)" >&2; exit 1 ;;
  *) echo "unexpected HTTP ${HTTP_CODE} from ACS /info" >&2; exit 1 ;;
esac

# --- Deploy ---
echo "[2/2] POSTing ${TARBALL} to ${ACS_URL}"
RESP=$(curl -sS -X POST \
  -H "Authorization: Bearer ${SPLUNKGATE_CLOUD_JWT}" \
  -H "X-Splunk-Authorization: ${SPLUNK_COM_APPINSPECT_TOKEN}" \
  -H "ACS-Legal-Ack: Y" \
  --data-binary "@${TARBALL}" \
  -w "\nHTTP_STATUS=%{http_code}\n" \
  "${ACS_URL}")
echo "${RESP}"

HTTP_CODE=$(echo "${RESP}" | awk -F'=' '/HTTP_STATUS=/{print $2}' | tr -d '[:space:]')
case "${HTTP_CODE}" in
  200|202)
    echo ""
    echo "===================================================="
    echo "  Deploy succeeded."
    echo "  Splunk Cloud: https://${SPLUNKGATE_STACK_NAME}.splunkcloud.com"
    echo "  App:         Apps -> SplunkGate"
    echo ""
    echo "  Now emit synthetic events to your Cloud HEC:"
    echo "    source .env"
    echo "    uv run python Synthetic-Data/scripts/emit_sample_verdict.py --count 500"
    echo "===================================================="
    ;;
  *)
    echo "deploy FAILED with HTTP ${HTTP_CODE}" >&2
    exit 1
    ;;
esac
