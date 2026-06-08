#!/usr/bin/env bash
# Local Splunk Enterprise (Docker) — spin up, install SplunkGate, verify.
#
# Use this BEFORE deploying to Splunk Cloud:
#   1. Verifies the .tgz installs cleanly
#   2. Lets you screenshot dashboards for the README + demo video
#   3. Catches any sourcetype / dashboard rendering issues locally
#
# Splunk Enterprise's "Install app from file" UI works (unlike Cloud), but
# this script uses the CLI for reproducibility.
#
# Container: splunk/splunk:latest (Splunk Enterprise 10.x)
# Web UI:    http://localhost:8000  (admin / $SPLUNK_PASSWORD)
# HEC:       http://localhost:8088  (after Phase 2 setup)
# REST:      https://localhost:8089
#
# Subcommands:
#   ./scripts/local_docker_splunk.sh up           # start container + install app
#   ./scripts/local_docker_splunk.sh emit         # emit synthetic events
#   ./scripts/local_docker_splunk.sh logs         # tail Splunk logs
#   ./scripts/local_docker_splunk.sh down         # stop + remove container

set -euo pipefail

CONTAINER="splunkgate-local"
IMAGE="splunk/splunk:latest"
PASSWORD="${SPLUNKGATE_LOCAL_SPLUNK_PASSWORD:-splunked99}"
HEC_TOKEN="${SPLUNKGATE_LOCAL_HEC_TOKEN:-00000000-1111-2222-3333-444444444444}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARBALL="${REPO_ROOT}/dist/splunkgate_app-1.0.0.tgz"

_check_tarball() {
  if [ ! -f "${TARBALL}" ]; then
    echo "tarball not found at ${TARBALL}" >&2
    echo "run: bash scripts/build_splunk_app_tgz.sh" >&2
    exit 2
  fi
}

cmd_up() {
  _check_tarball

  # Idempotent — if already running, just install/upgrade the app.
  if docker ps -a --format '{{.Names}}' | grep -qx "${CONTAINER}"; then
    echo "container '${CONTAINER}' already exists; starting if stopped"
    docker start "${CONTAINER}" >/dev/null 2>&1 || true
  else
    echo "spinning up ${CONTAINER} from ${IMAGE}"
    # Splunk's official image ships amd64 only; on Apple Silicon we run it
    # under Rosetta via --platform linux/amd64. Slower but functional.
    docker run -d --name="${CONTAINER}" \
      --platform=linux/amd64 \
      -e "SPLUNK_PASSWORD=${PASSWORD}" \
      -e "SPLUNK_START_ARGS=--accept-license" \
      -e "SPLUNK_GENERAL_TERMS=--accept-sgt-current-at-splunk-com" \
      -e "SPLUNK_HEC_TOKEN=${HEC_TOKEN}" \
      -p 8000:8000 -p 8088:8088 -p 8089:8089 \
      "${IMAGE}"
  fi

  echo "waiting for Splunk to start (60s)..."
  for i in $(seq 1 60); do
    if curl -ksf "https://localhost:8089/services/server/info" -u "admin:${PASSWORD}" >/dev/null 2>&1; then
      echo "Splunk ready after ${i}s"
      break
    fi
    sleep 1
  done

  echo "copying tarball into container"
  docker cp "${TARBALL}" "${CONTAINER}:/tmp/splunkgate_app-1.0.0.tgz"

  echo "installing app"
  docker exec "${CONTAINER}" /opt/splunk/bin/splunk install app /tmp/splunkgate_app-1.0.0.tgz \
    -update 1 -auth "admin:${PASSWORD}"

  echo "restarting Splunk"
  docker exec "${CONTAINER}" /opt/splunk/bin/splunk restart >/dev/null

  echo ""
  echo "===================================================="
  echo "  Splunk Web:  http://localhost:8000"
  echo "  Login:       admin / ${PASSWORD}"
  echo "  HEC token:   ${HEC_TOKEN}"
  echo "  App:         Apps -> SplunkGate"
  echo ""
  echo "  Emit synthetic events:"
  echo "    bash scripts/local_docker_splunk.sh emit"
  echo "===================================================="
}

cmd_emit() {
  local count="${1:-500}"
  echo "emitting ${count} events to local HEC"
  SPLUNKGATE_SPLUNK_HEC_URL="http://localhost:8088" \
  SPLUNKGATE_SPLUNK_HEC_TOKEN="${HEC_TOKEN}" \
    uv run python "${REPO_ROOT}/Synthetic-Data/scripts/emit_sample_verdict.py" \
      --count "${count}"
}

cmd_logs() {
  docker logs -f --tail 100 "${CONTAINER}"
}

cmd_down() {
  docker stop "${CONTAINER}" 2>/dev/null || true
  docker rm "${CONTAINER}" 2>/dev/null || true
  echo "removed ${CONTAINER}"
}

case "${1:-up}" in
  up)    cmd_up ;;
  emit)  shift; cmd_emit "$@" ;;
  logs)  cmd_logs ;;
  down)  cmd_down ;;
  *)
    echo "usage: $0 {up|emit [count]|logs|down}" >&2
    exit 1
    ;;
esac
