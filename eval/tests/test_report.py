"""Tests for the report-generator (story-eval-05)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from splunkgate_eval.report import generate_report

if TYPE_CHECKING:
    from pathlib import Path


def _make_per_dataset(
    results_dir: Path,
    baseline_id: str,
    dataset_id: str,
    *,
    is_mock: bool = False,
) -> None:
    """Write a minimal per-dataset JSON record under results_dir/per_dataset/."""
    per_dir = results_dir / "per_dataset"
    per_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "baseline_id": baseline_id,
        "dataset_id": dataset_id,
        "is_mock": is_mock,
        "verdicts": [
            {
                "trace_id": "00000000-0000-0000-0000-000000000001",
                "timestamp": "2026-06-11T15:00:00+00:00",
                "verdict": "BLOCK",
                "severity": "HIGH",
                "rules": [],
                "modifications": None,
                "surface": "defenseclaw",
                "latency_ms": 1.5,
                "explanation": None,
                "agent_id": "default",
                "is_mock": is_mock,
            },
            {
                "trace_id": "00000000-0000-0000-0000-000000000002",
                "timestamp": "2026-06-11T15:00:00+00:00",
                "verdict": "ALLOW",
                "severity": "NONE_SEVERITY",
                "rules": [],
                "modifications": None,
                "surface": "defenseclaw",
                "latency_ms": 0.3,
                "explanation": None,
                "agent_id": "default",
                "is_mock": is_mock,
            },
        ],
        "expected": [
            {"id": "p1", "expected_verdict": "BLOCK", "expected_severity": "HIGH"},
            {"id": "p2", "expected_verdict": "ALLOW", "expected_severity": "NONE_SEVERITY"},
        ],
    }
    (per_dir / f"{dataset_id}__{baseline_id}.json").write_text(
        json.dumps(record, sort_keys=True),
        encoding="utf-8",
    )


def test_report_writes_summary_md_with_required_columns(tmp_path: Path) -> None:
    """summary.md must include every column header listed in the eval spec."""
    _make_per_dataset(tmp_path, "defenseclaw_regex_only", "benign_control")
    generate_report(tmp_path, output_path=tmp_path / "out.md")
    text = (tmp_path / "summary.md").read_text(encoding="utf-8")
    for col in ("Precision", "Recall", "F1", "ECE", "p50", "p99", "$/1k"):
        assert col in text, f"missing column '{col}' in summary.md"


def test_imprompter_arxiv_citation_in_footnote(tmp_path: Path) -> None:
    """The Imprompter arXiv ID must appear in the report footer."""
    _make_per_dataset(tmp_path, "defenseclaw_regex_only", "benign_control")
    generate_report(tmp_path, output_path=tmp_path / "out.md")
    assert "2410.14923" in (tmp_path / "summary.md").read_text(encoding="utf-8")


def test_msj_power_law_footnote_present(tmp_path: Path) -> None:
    """The Anthropic Many-Shot Jailbreaking power-law caveat must appear."""
    _make_per_dataset(tmp_path, "defenseclaw_regex_only", "benign_control")
    generate_report(tmp_path, output_path=tmp_path / "out.md")
    assert "power-law" in (tmp_path / "summary.md").read_text(encoding="utf-8")


def test_mock_annotation_appears(tmp_path: Path) -> None:
    """`(mock)` suffix must appear next to any row marked is_mock."""
    _make_per_dataset(tmp_path, "ai_defense_alone", "benign_control", is_mock=True)
    generate_report(tmp_path, output_path=tmp_path / "out.md")
    assert "(mock)" in (tmp_path / "summary.md").read_text(encoding="utf-8")


def test_mirror_writes_to_docs_eval_results(tmp_path: Path) -> None:
    """generate_report writes both summary.md AND the output_path mirror."""
    _make_per_dataset(tmp_path, "defenseclaw_regex_only", "benign_control")
    out_path = tmp_path / "doc.md"
    generate_report(tmp_path, output_path=out_path)
    assert out_path.exists()
    assert "Precision" in out_path.read_text(encoding="utf-8")


def test_reliability_pngs_written_per_evaluator(tmp_path: Path) -> None:
    """Per-evaluator reliability PNGs land under results_dir/reliability/."""
    _make_per_dataset(tmp_path, "defenseclaw_regex_only", "benign_control")
    generate_report(tmp_path, output_path=tmp_path / "out.md")
    assert (tmp_path / "reliability" / "defenseclaw_regex_only.png").exists()


def test_latency_pngs_written_per_evaluator(tmp_path: Path) -> None:
    """Per-evaluator latency-percentile PNGs land under results_dir/latency/."""
    _make_per_dataset(tmp_path, "defenseclaw_regex_only", "benign_control")
    generate_report(tmp_path, output_path=tmp_path / "out.md")
    assert (tmp_path / "latency" / "defenseclaw_regex_only.png").exists()


def test_report_is_deterministic_across_runs(tmp_path: Path) -> None:
    """Same per_dataset inputs → byte-identical summary.md."""
    _make_per_dataset(tmp_path, "defenseclaw_regex_only", "benign_control")
    generate_report(tmp_path, output_path=tmp_path / "out1.md")
    first = (tmp_path / "out1.md").read_text(encoding="utf-8")
    generate_report(tmp_path, output_path=tmp_path / "out2.md")
    second = (tmp_path / "out2.md").read_text(encoding="utf-8")
    assert first == second


@pytest.mark.parametrize("baseline_id", ["defenseclaw_regex_only", "ai_defense_alone"])
def test_table_row_per_baseline(tmp_path: Path, baseline_id: str) -> None:
    """A row appears in the rendered table for every distinct baseline_id in per_dataset."""
    _make_per_dataset(tmp_path, baseline_id, "benign_control")
    generate_report(tmp_path, output_path=tmp_path / "out.md")
    assert baseline_id in (tmp_path / "summary.md").read_text(encoding="utf-8")
