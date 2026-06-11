"""Classification metrics: precision, recall, F1, specificity, confusion-matrix, ECE.

Operates on `y_true`/`y_pred` int sequences (0 = negative, 1 = positive) and
on `(y_true, probas)` pairs for the calibration ECE. numpy is allowed in
`eval/` per `docs/architecture.md` § "Banned" (banned only in
`splunkgate_core`/`splunkgate_judges`).

ECE formula per Naeini et al. 2015:
    ECE = sum_b (|bin_b| / N) * |acc(bin_b) - conf(bin_b)|
with equal-width bins across [0, 1]. Empty bins contribute 0.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "ConfusionMatrix",
    "confusion_matrix",
    "expected_calibration_error",
    "f1",
    "precision",
    "recall",
    "specificity",
]


class ConfusionMatrix(NamedTuple):
    """2x2 binary confusion matrix; element naming matches sklearn semantics."""

    tn: int
    fp: int
    fn: int
    tp: int


def _validate_pair(y_true: Sequence[int], y_pred: Sequence[int]) -> None:
    """Raise ValueError if the two label sequences are misshaped."""
    if len(y_true) != len(y_pred):
        msg = f"length mismatch: y_true={len(y_true)} y_pred={len(y_pred)}"
        raise ValueError(msg)
    if not y_true:
        msg = "empty input — at least one (y_true, y_pred) pair required"
        raise ValueError(msg)


def confusion_matrix(y_true: Sequence[int], y_pred: Sequence[int]) -> ConfusionMatrix:
    """Return a 2x2 ConfusionMatrix from two int sequences."""
    _validate_pair(y_true, y_pred)
    yt = np.asarray(y_true, dtype=np.int8)
    yp = np.asarray(y_pred, dtype=np.int8)
    tp = int(np.sum((yt == 1) & (yp == 1)))
    fp = int(np.sum((yt == 0) & (yp == 1)))
    fn = int(np.sum((yt == 1) & (yp == 0)))
    tn = int(np.sum((yt == 0) & (yp == 0)))
    return ConfusionMatrix(tn=tn, fp=fp, fn=fn, tp=tp)


def precision(y_true: Sequence[int], y_pred: Sequence[int]) -> float:
    """TP / (TP + FP). Returns 0.0 when no positive predictions exist."""
    cm = confusion_matrix(y_true, y_pred)
    denom = cm.tp + cm.fp
    return float(cm.tp) / denom if denom else 0.0


def recall(y_true: Sequence[int], y_pred: Sequence[int]) -> float:
    """TP / (TP + FN). Returns 0.0 when no positive ground-truth labels exist."""
    cm = confusion_matrix(y_true, y_pred)
    denom = cm.tp + cm.fn
    return float(cm.tp) / denom if denom else 0.0


def specificity(y_true: Sequence[int], y_pred: Sequence[int]) -> float:
    """TN / (TN + FP). Returns 0.0 when no negative ground-truth labels exist."""
    cm = confusion_matrix(y_true, y_pred)
    denom = cm.tn + cm.fp
    return float(cm.tn) / denom if denom else 0.0


def f1(y_true: Sequence[int], y_pred: Sequence[int]) -> float:
    """Harmonic mean of precision + recall."""
    p, r = precision(y_true, y_pred), recall(y_true, y_pred)
    return 2 * p * r / (p + r) if (p + r) else 0.0


def expected_calibration_error(
    y_true: Sequence[int],
    probas: Sequence[float],
    n_bins: int = 10,
) -> float:
    """ECE on `n_bins` equal-width bins across [0, 1]. Empty bins contribute 0."""
    if len(y_true) != len(probas):
        msg = f"length mismatch: y_true={len(y_true)} probas={len(probas)}"
        raise ValueError(msg)
    if not y_true:
        return 0.0
    if n_bins <= 0:
        msg = f"n_bins must be > 0, got {n_bins}"
        raise ValueError(msg)
    yt = np.asarray(y_true, dtype=np.float64)
    pr = np.asarray(probas, dtype=np.float64)
    n = len(yt)
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        mask = (pr >= lo) & (pr < hi) if i < n_bins - 1 else (pr >= lo) & (pr <= hi)
        bin_count = int(np.sum(mask))
        if bin_count == 0:
            continue
        acc = float(np.mean(yt[mask]))
        conf = float(np.mean(pr[mask]))
        ece += (bin_count / n) * abs(acc - conf)
    return ece
