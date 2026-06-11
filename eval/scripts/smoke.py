#!/usr/bin/env python3
# ruff: noqa: T201, S603 — script: print() is the contract; sys.executable is controlled
"""Smoke driver — small subset for CI; must exit 0 in <60 seconds."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    """Invoke run_full.py with the smoke baseline + dataset subset."""
    here = Path(__file__).resolve().parent
    env = {**os.environ, "SPLUNKGATE_AI_DEFENSE_MOCK": "1", "SPLUNKGATE_GPT_OSS_MOCK": "1"}
    cmd = [
        sys.executable,
        str(here / "run_full.py"),
        "--limit",
        "25",
        "--baselines",
        "defenseclaw_regex_only,ai_defense_alone",
        "--datasets",
        "benign_control,jailbreakbench",
    ]
    try:
        result = subprocess.run(cmd, check=False, env=env, timeout=120)
    except subprocess.TimeoutExpired:
        print("smoke FAILED: ran > 120s budget", file=sys.stderr)
        return 1
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
