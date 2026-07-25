"""Tests for the metric-computation helpers in training/train.py."""

from train import compute_metrics, compute_per_class_metrics

CLASS_NAMES = ["A", "B", "C"]


def test_compute_metrics_perfect_predictions():
    y_true = [0, 1, 2, 0, 1, 2]
    y_pred = [0, 1, 2, 0, 1, 2]
    metrics = compute_metrics(y_true, y_pred, CLASS_NAMES)
    assert metrics["accuracy"] == 1.0
    assert metrics["macro_precision"] == 1.0
    assert metrics["macro_recall"] == 1.0
    assert metrics["macro_f1"] == 1.0
    assert metrics["weighted_f1"] == 1.0


def test_compute_metrics_zero_division_safe_for_unpredicted_class():
    # Class 2 never appears in y_pred at all.
    y_true = [0, 1, 2]
    y_pred = [0, 1, 1]
    metrics = compute_metrics(y_true, y_pred, CLASS_NAMES)
    assert 0.0 <= metrics["macro_f1"] <= 1.0  # must not raise/NaN


def test_compute_per_class_metrics_reports_support_per_class():
    y_true = [0, 0, 1, 2, 2, 2]
    y_pred = [0, 1, 1, 2, 2, 0]
    per_class = compute_per_class_metrics(y_true, y_pred, CLASS_NAMES)
    assert per_class["A"]["support"] == 2
    assert per_class["B"]["support"] == 1
    assert per_class["C"]["support"] == 3
    for name in CLASS_NAMES:
        assert 0.0 <= per_class[name]["precision"] <= 1.0
        assert 0.0 <= per_class[name]["recall"] <= 1.0
        assert 0.0 <= per_class[name]["f1"] <= 1.0


def test_compute_per_class_metrics_zero_division_safe_for_absent_class():
    # Class "C" appears in neither y_true nor y_pred.
    y_true = [0, 1, 0, 1]
    y_pred = [0, 1, 1, 0]
    per_class = compute_per_class_metrics(y_true, y_pred, CLASS_NAMES)
    assert per_class["C"]["support"] == 0
    assert per_class["C"]["precision"] == 0.0
    assert per_class["C"]["recall"] == 0.0
    assert per_class["C"]["f1"] == 0.0
