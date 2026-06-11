"""Latency percentile + plot helpers for the eval report.

`percentiles(latencies_ms)` returns a frozen `LatencySummary` with p50/p90/p95/p99/p99.9.
`percentile_plot(latencies_ms, output_path)` renders a log-scaled percentile-vs-latency PNG.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import matplotlib as mpl
import numpy as np
from pydantic import BaseModel, ConfigDict

mpl.use("Agg")
import matplotlib.pyplot as plt

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["LatencySummary", "percentile_plot", "percentiles"]

_PERCENTILES: Final[tuple[tuple[str, float], ...]] = (
    ("p50", 50.0),
    ("p90", 90.0),
    ("p95", 95.0),
    ("p99", 99.0),
    ("p99_9", 99.9),
)


class LatencySummary(BaseModel):
    """Latency percentiles for a sample population (units: milliseconds)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    p50: float
    p90: float
    p95: float
    p99: float
    p99_9: float
    mean: float
    count: int


def percentiles(latencies_ms: list[float]) -> LatencySummary:
    """Compute percentile + mean summary over a latency-ms sample."""
    if not latencies_ms:
        msg = "empty input — at least one latency sample required"
        raise ValueError(msg)
    arr = np.asarray(latencies_ms, dtype=np.float64)
    qs = np.percentile(arr, [p for _, p in _PERCENTILES])
    return LatencySummary(
        p50=float(qs[0]),
        p90=float(qs[1]),
        p95=float(qs[2]),
        p99=float(qs[3]),
        p99_9=float(qs[4]),
        mean=float(arr.mean()),
        count=int(arr.size),
    )


def percentile_plot(latencies_ms: list[float], output_path: Path) -> None:
    """Render a percentile-vs-latency PNG; closes the figure to prevent backend leaks."""
    if not latencies_ms:
        msg = "empty input — cannot plot empty latency series"
        raise ValueError(msg)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    arr = np.sort(np.asarray(latencies_ms, dtype=np.float64))
    n = arr.size
    quantiles = np.linspace(0.0, 1.0, n, endpoint=True)
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(quantiles, arr, marker="o", markersize=2, linewidth=0.8)
    ax.set_xlabel("quantile")
    ax.set_ylabel("latency (ms)")
    ax.set_yscale("log")
    ax.set_title(f"latency percentiles (n={n})")
    ax.grid(visible=True, which="both", linestyle=":", alpha=0.5)
    fig.tight_layout()
    fig.savefig(output_path, dpi=120)
    plt.close(fig)
