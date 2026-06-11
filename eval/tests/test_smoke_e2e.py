"""End-to-end smoke tests (story-eval-05)."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SMOKE = _REPO_ROOT / "eval" / "scripts" / "smoke.py"


@pytest.fixture
def _ensure_mock_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every smoke test runs in mock mode — live calls would burn quota in CI."""
    monkeypatch.setenv("SPLUNKGATE_AI_DEFENSE_MOCK", "1")
    monkeypatch.setenv("SPLUNKGATE_GPT_OSS_MOCK", "1")


def _run_smoke() -> tuple[int, float]:
    """Run the smoke script via the workspace python; return (exit_code, elapsed_seconds)."""
    started = time.perf_counter()
    env = {**os.environ, "SPLUNKGATE_AI_DEFENSE_MOCK": "1", "SPLUNKGATE_GPT_OSS_MOCK": "1"}
    result = subprocess.run(
        [sys.executable, str(_SMOKE)],
        check=False,
        env=env,
        cwd=_REPO_ROOT,
        timeout=120,
    )
    return result.returncode, time.perf_counter() - started


@pytest.mark.usefixtures("_ensure_mock_env")
def test_smoke_exits_zero_under_60_seconds() -> None:
    """Smoke run must exit 0 in <60s — CI eval-smoke job depends on this budget."""
    code, elapsed = _run_smoke()
    assert code == 0, f"smoke exited {code}"
    assert elapsed < 60, f"smoke took {elapsed:.1f}s, expected <60s"


@pytest.mark.usefixtures("_ensure_mock_env")
def test_smoke_writes_per_dataset_artifacts() -> None:
    """The smoke run produces at least one per_dataset JSON file under eval/results/."""
    _run_smoke()
    results_dir = _REPO_ROOT / "eval" / "results"
    per_dataset_files = list(results_dir.glob("*/per_dataset/*.json"))
    assert per_dataset_files, "no per_dataset JSON files written"


@pytest.mark.usefixtures("_ensure_mock_env")
def test_smoke_renders_docs_eval_results() -> None:
    """The smoke run writes docs/eval-results.md with the headline columns."""
    _run_smoke()
    doc = _REPO_ROOT / "docs" / "eval-results.md"
    assert doc.exists()
    text = doc.read_text(encoding="utf-8")
    assert "Precision" in text
    assert "$/1k" in text


@pytest.mark.usefixtures("_ensure_mock_env")
def test_smoke_is_structurally_idempotent() -> None:
    """Two smoke runs produce identical row ORDERING + columns + mock flags.

    Byte-identical content is not achievable here: per-row latency values come
    from `time.perf_counter_ns()` measurements that vary at the microsecond
    level between runs. The .1f formatting in `report._render_table` is
    sometimes enough to round both runs to the same string and sometimes not,
    depending on which side of a tenth-millisecond boundary the measurement
    lands. Assert the structural invariants only.
    """
    _run_smoke()
    first = (_REPO_ROOT / "docs" / "eval-results.md").read_text(encoding="utf-8")
    _run_smoke()
    second = (_REPO_ROOT / "docs" / "eval-results.md").read_text(encoding="utf-8")

    # Column ordering + headers + footnotes are byte-identical.
    assert first.split("|")[:9] == second.split("|")[:9]
    # Row order is alphabetical and stable across runs.
    first_evaluators = [
        line.split("|")[1].strip()
        for line in first.splitlines()
        if line.startswith(("| ai", "| def"))
    ]
    second_evaluators = [
        line.split("|")[1].strip()
        for line in second.splitlines()
        if line.startswith(("| ai", "| def"))
    ]
    assert first_evaluators == second_evaluators
    # Footnotes are deterministic.
    assert "2410.14923" in first
    assert "2410.14923" in second
    assert "power-law" in first
    assert "power-law" in second
