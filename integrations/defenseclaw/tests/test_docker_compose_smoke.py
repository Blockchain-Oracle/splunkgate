"""Docker-compose smoke tests — gated on SPLUNKGATE_DC_INTEGRATION=1 (story-dc-01).

These run only against a live Docker daemon. The unit-CI matrix should NOT
run them (slow, requires Docker, requires DefenseClaw image pull). Pin to
the nightly-integration matrix via the env-var gate.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

_COMPOSE = Path(__file__).parent.parent / "examples" / "docker-compose.yaml"
_EVENT_LOG_PATH_IN_VOLUME = "/data/events.jsonl"
_INTEGRATION_GATE = os.environ.get("SPLUNKGATE_DC_INTEGRATION") == "1"

pytestmark = pytest.mark.skipif(
    not _INTEGRATION_GATE,
    reason="set SPLUNKGATE_DC_INTEGRATION=1 to opt into the docker-compose smoke",
)


def _docker_available() -> bool:
    """Docker daemon must be reachable for any of these tests to run."""
    if shutil.which("docker") is None:
        return False
    try:
        subprocess.run(
            ["docker", "info"],
            check=True,
            capture_output=True,
            timeout=5,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False
    return True


@pytest.fixture
def compose_up_and_down() -> object:
    """Bring up the compose stack and tear it down in finalizer."""
    assert _docker_available(), "Docker daemon unavailable"
    subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(_COMPOSE),
            "up",
            "-d",
            "defenseclaw-gateway",
            "splunk-hec-double",
        ],
        check=True,
    )
    try:
        yield None
    finally:
        subprocess.run(
            ["docker", "compose", "-f", str(_COMPOSE), "down", "-v"],
            check=False,
        )


def test_compose_file_parses() -> None:
    """Sanity check — the YAML loads and declares the 3 expected services."""
    import yaml  # noqa: PLC0415

    parsed = yaml.safe_load(_COMPOSE.read_text(encoding="utf-8"))
    services = parsed.get("services", {})
    for expected in ("defenseclaw-gateway", "splunk-hec-double", "verifier"):
        assert expected in services, f"{expected} missing from compose"


def _dump_gateway_logs() -> str:
    """Return the last 100 lines of the gateway container log; used to enrich failure messages."""
    proc = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(_COMPOSE),
            "logs",
            "--tail",
            "100",
            "defenseclaw-gateway",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return proc.stdout + proc.stderr


def test_compose_smoke_verifier_exits_zero(compose_up_and_down: object) -> None:  # noqa: ARG001
    """Run the verifier one-shot; it must exit 0. Dump gateway logs on failure for triage."""
    result = subprocess.run(
        ["docker", "compose", "-f", str(_COMPOSE), "run", "--rm", "verifier"],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        logs = _dump_gateway_logs()
        msg = (
            f"verifier exit={result.returncode}\n"
            f"--- verifier stdout ---\n{result.stdout}\n"
            f"--- verifier stderr ---\n{result.stderr}\n"
            f"--- defenseclaw-gateway logs (tail 100) ---\n{logs}\n"
        )
        raise AssertionError(msg)


def test_compose_smoke_verdict_lands_in_hec_double_volume(
    compose_up_and_down: object,  # noqa: ARG001
) -> None:
    """After the verifier runs, the HEC double volume must hold ≥1 verdict event."""
    subprocess.run(
        ["docker", "compose", "-f", str(_COMPOSE), "run", "--rm", "verifier"],
        check=True,
        timeout=120,
    )
    # Give the HEC sink a moment to flush + the verifier to settle.
    time.sleep(2)
    cat = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(_COMPOSE),
            "run",
            "--rm",
            "--entrypoint",
            "cat",
            "splunk-hec-double",
            _EVENT_LOG_PATH_IN_VOLUME,
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert "cisco_ai_defense:splunkgate_verdict" in cat.stdout
