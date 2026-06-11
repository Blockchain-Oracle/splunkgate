"""Behavioural tests for the AdvBench loader (story-eval-02)."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from splunkgate_eval import AdvBenchSubmoduleMissingError, EvalPrompt, load_advbench
from splunkgate_eval.advbench import DEFAULT_CSV_PATH

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "advbench_sample.csv"


def test_default_load_returns_520_records() -> None:
    """Upstream `harmful_behaviors.csv` is 520 data rows — submodule must be initialised."""
    records = load_advbench()
    assert len(records) == 520


def test_csv_row_count_matches_loader_count() -> None:
    """Spec verification: wc -l = len(records) + 1 (header)."""
    with DEFAULT_CSV_PATH.open("r", encoding="utf-8", newline="") as h:
        reader = csv.DictReader(h)
        row_count = sum(1 for _ in reader)
    assert row_count == len(load_advbench())


def test_limit_kwarg_returns_exactly_n() -> None:
    """`limit=10` returns exactly 10 records."""
    assert len(load_advbench(limit=10)) == 10


def test_every_record_validates_as_eval_prompt() -> None:
    """Records are native EvalPrompts; loaders cannot ship raw dicts."""
    for r in load_advbench(limit=50):
        assert isinstance(r, EvalPrompt)


def test_canonical_triple_on_every_record() -> None:
    """Every record reports (advbench, BLOCK, HIGH)."""
    for r in load_advbench(limit=50):
        assert r.category == "advbench"
        assert r.expected_verdict == "BLOCK"
        assert r.expected_severity == "HIGH"


def test_missing_submodule_raises_with_remediation_string(tmp_path: Path) -> None:
    """`AdvBenchSubmoduleMissingError` carries the verbatim `git submodule update --init` command."""
    nonexistent = tmp_path / "missing.csv"
    with pytest.raises(AdvBenchSubmoduleMissingError) as exc_info:
        load_advbench(csv_path=nonexistent)
    assert "git submodule update --init inspiration/llm-attacks" in str(exc_info.value)
    assert exc_info.value.expected_path == str(nonexistent)


def test_fixture_path_overrides_default() -> None:
    """Loader honours a custom csv_path kwarg; useful for fixture-driven unit tests."""
    records = load_advbench(csv_path=_FIXTURE)
    assert len(records) == 10  # the fixture has 10 rows
    for r in records:
        assert r.category == "advbench"
        assert r.source_citation.startswith("advbench:zou-et-al-2023:row-")


def test_loading_is_deterministic_across_repeat_calls() -> None:
    """Two consecutive calls produce identical id sequences."""
    first = [r.id for r in load_advbench(limit=20)]
    second = [r.id for r in load_advbench(limit=20)]
    assert first == second
