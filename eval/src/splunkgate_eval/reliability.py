"""Reliability-diagram (calibration plot) PNG renderer for the eval report."""

from __future__ import annotations

from typing import TYPE_CHECKING

import matplotlib as mpl
import numpy as np

mpl.use("Agg")
import matplotlib.pyplot as plt

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["reliability_diagram"]


def reliability_diagram(
    y_true: list[int],
    probas: list[float],
    output_path: Path,
    *,
    n_bins: int = 10,
) -> None:
    """Render a calibration plot to `output_path`; closes the figure on exit."""
    if not y_true or not probas:
        msg = "empty input — cannot plot empty calibration data"
        raise ValueError(msg)
    if len(y_true) != len(probas):
        msg = f"length mismatch: y_true={len(y_true)} probas={len(probas)}"
        raise ValueError(msg)
    if n_bins <= 0:
        msg = f"n_bins must be > 0, got {n_bins}"
        raise ValueError(msg)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    yt = np.asarray(y_true, dtype=np.float64)
    pr = np.asarray(probas, dtype=np.float64)
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    bin_midpoints: list[float] = []
    observed: list[float] = []
    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        mask = (pr >= lo) & (pr < hi) if i < n_bins - 1 else (pr >= lo) & (pr <= hi)
        if not np.any(mask):
            continue
        bin_midpoints.append(float((lo + hi) / 2))
        observed.append(float(np.mean(yt[mask])))
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.plot([0, 1], [0, 1], linestyle="--", color="grey", label="perfectly calibrated")
    ax.plot(bin_midpoints, observed, marker="o", linewidth=1.2, label="observed")
    ax.set_xlabel("predicted probability (bin midpoint)")
    ax.set_ylabel("observed fraction positive")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_title(f"reliability diagram (n_bins={n_bins})")
    ax.legend(loc="best")
    ax.grid(visible=True, linestyle=":", alpha=0.5)
    fig.tight_layout()
    fig.savefig(output_path, dpi=120)
    plt.close(fig)
