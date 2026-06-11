"""Tests for the latency module (story-eval-05)."""

from __future__ import annotations

from pathlib import Path

import pytest
from splunkgate_eval.latency import LatencySummary, percentile_plot, percentiles


def test_median_of_ten_samples_is_five_point_five() -> None:
    """percentile(50) of [1..10] is 5.5 by linear interpolation."""
    assert percentiles([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]).p50 == pytest.approx(5.5)


def test_count_matches_input_length() -> None:
    """`count` field equals len(input)."""
    assert percentiles([0.5, 1.5, 2.5]).count == 3


def test_pydantic_validates_summary() -> None:
    """LatencySummary is a frozen Pydantic model with extra='forbid'."""
    s = LatencySummary(p50=1.0, p90=2.0, p95=3.0, p99=4.0, p99_9=5.0, mean=2.0, count=10)
    assert s.p50 == 1.0


def test_empty_input_raises_value_error() -> None:
    """Empty latency series is a programming error, not a degenerate stat."""
    with pytest.raises(ValueError, match="empty"):
        percentiles([])
    with pytest.raises(ValueError, match="empty"):
        percentile_plot([], Path("/tmp/never-written.png"))  # noqa: S108 — never written


def test_percentile_plot_writes_png(tmp_path: Path) -> None:
    """percentile_plot creates the PNG file at the given output path."""
    out = tmp_path / "subdir" / "lat.png"
    percentile_plot([0.5, 1.0, 1.5, 2.0, 10.0, 100.0], out)
    assert out.exists()
    assert out.stat().st_size > 0


def test_p99_of_100_uniform_samples_returns_top_quantile() -> None:
    """percentile(99) of 1..100 returns ~99 by linear interpolation."""
    summary = percentiles(list(range(1, 101)))
    assert summary.p99 == pytest.approx(99.01, abs=0.5)
