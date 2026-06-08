"""Skeleton + meta-tests asserting ruff/mypy stay clean against splunkgate_core."""

from __future__ import annotations

import subprocess
from pathlib import Path

import splunkgate_core

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_splunkgate_core_imports_cleanly() -> None:
    assert splunkgate_core.__name__ == "splunkgate_core"


def test_splunkgate_core_ruff_clean() -> None:
    """ruff check on splunkgate_core's source tree exits 0."""
    result = subprocess.run(
        ["uv", "run", "ruff", "check", "packages/splunkgate_core"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"ruff check failed on splunkgate_core:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )


def test_splunkgate_core_mypy_strict_clean() -> None:
    """mypy --strict on splunkgate_core's source tree exits 0 (no Any leaks)."""
    result = subprocess.run(
        ["uv", "run", "mypy", "--strict", "-p", "splunkgate_core"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"mypy --strict failed on splunkgate_core:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
