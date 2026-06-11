"""Tests for the classification metrics module (story-eval-05)."""

from __future__ import annotations

import math

import pytest
from splunkgate_eval.metrics import (
    ConfusionMatrix,
    confusion_matrix,
    expected_calibration_error,
    f1,
    precision,
    recall,
    specificity,
)


def test_precision_basic_case() -> None:
    """precision([1,1,0,0], [1,0,0,0]) = 1/1 = 1.0."""
    assert precision([1, 1, 0, 0], [1, 0, 0, 0]) == 1.0


def test_recall_basic_case() -> None:
    """recall([1,1,0,0], [1,0,0,0]) = 1/2 = 0.5."""
    assert recall([1, 1, 0, 0], [1, 0, 0, 0]) == 0.5


def test_f1_is_harmonic_mean() -> None:
    """f1 of P=1.0 R=0.5 is 2*1*0.5/1.5 = 2/3."""
    assert math.isclose(f1([1, 1, 0, 0], [1, 0, 0, 0]), 2 / 3)


def test_perfect_predictions_give_one() -> None:
    """All-correct predictions yield P=R=F1=1.0."""
    assert precision([1, 1, 0, 0], [1, 1, 0, 0]) == 1.0
    assert recall([1, 1, 0, 0], [1, 1, 0, 0]) == 1.0
    assert f1([1, 1, 0, 0], [1, 1, 0, 0]) == 1.0


def test_all_wrong_predictions_give_zero() -> None:
    """All-wrong predictions yield P=R=F1=0.0 without ZeroDivisionError."""
    assert precision([1, 1, 0, 0], [0, 0, 1, 1]) == 0.0
    assert recall([1, 1, 0, 0], [0, 0, 1, 1]) == 0.0
    assert f1([1, 1, 0, 0], [0, 0, 1, 1]) == 0.0


def test_specificity_basic_case() -> None:
    """specificity = TN/(TN+FP); all-negative-correct gives 1.0."""
    assert specificity([0, 0, 0, 0], [0, 0, 0, 0]) == 1.0
    assert specificity([0, 0, 1, 1], [0, 0, 1, 0]) == 1.0


def test_confusion_matrix_layout() -> None:
    """The 2x2 ConfusionMatrix maps to (tn, fp, fn, tp) like sklearn."""
    cm = confusion_matrix([1, 1, 0, 0], [1, 0, 0, 1])
    assert cm == ConfusionMatrix(tn=1, fp=1, fn=1, tp=1)


def test_ece_perfectly_calibrated_inputs_yield_zero() -> None:
    """probas 1.0 on label-1 + probas 0.0 on label-0 give ECE = 0."""
    assert expected_calibration_error([1, 0, 1, 0], [1.0, 0.0, 1.0, 0.0]) == pytest.approx(
        0.0, abs=1e-6
    )


def test_ece_uniform_50pct_is_calibrated() -> None:
    """ECE measures calibration, not informativeness: 50% probs on 50% accuracy is calibrated."""
    assert expected_calibration_error([1, 0, 1, 0], [0.5, 0.5, 0.5, 0.5]) == pytest.approx(
        0.0, abs=1e-6
    )


def test_ece_overconfident_returns_high() -> None:
    """Probas of 0.9 on all-wrong labels yield ECE near 0.9."""
    assert expected_calibration_error([0, 0, 0, 0], [0.9, 0.9, 0.9, 0.9]) == pytest.approx(
        0.9, abs=1e-6
    )


def test_ece_is_bounded_in_unit_interval() -> None:
    """ECE is bounded in [0, 1] by construction (weighted |acc - conf|)."""
    ece = expected_calibration_error([1, 1, 0, 0], [0.7, 0.3, 0.6, 0.4])
    assert 0.0 <= ece <= 1.0


def test_metrics_reject_misshaped_input() -> None:
    """Length mismatch raises ValueError before the math runs."""
    with pytest.raises(ValueError, match="length mismatch"):
        precision([1, 0], [1])
    with pytest.raises(ValueError, match="empty input"):
        precision([], [])
