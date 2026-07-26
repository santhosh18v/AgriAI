"""Tests for training/select_threshold.py: candidate calculations, the
predeclared selection rule, zero-support handling, determinism, confidence-
policy schema, frozen-threshold application, and bootstrap CIs. Uses tiny
synthetic prediction rows only -- never real dataset predictions."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json

import numpy as np
import pytest
from sklearn.metrics import precision_recall_fscore_support

import select_threshold as st

CLASS_NAMES = ["A", "B"]


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def _write_predictions_csv(path, rows):
    fieldnames = [
        "path", "true_class_name", "true_class_index", "predicted_class_name",
        "predicted_class_index", "maximum_probability", "correct", "group_key",
        "similarity_guard_group",
    ]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in fieldnames})


def _write_class_map_and_scope(tmp_path, class_to_index):
    class_map_path = tmp_path / "class_map.json"
    class_map_path.write_text(json.dumps({str(i): name for name, i in class_to_index.items()}))
    model_scope_path = tmp_path / "model_scope.json"
    model_scope_path.write_text(
        json.dumps(
            {
                "status": "approved",
                "active_model_classes": [n for n, _ in sorted(class_to_index.items(), key=lambda kv: kv[1])],
            }
        )
    )
    return class_map_path, model_scope_path


def _write_integrity(tmp_path, predictions_csv_path, checkpoint_sha256, manifest_sha256, class_to_index, **overrides):
    class_names = [n for n, _ in sorted(class_to_index.items(), key=lambda kv: kv[1])]
    with open(predictions_csv_path, newline="") as f:
        row_count = sum(1 for _ in csv.DictReader(f))
    integrity = {
        "evaluation_mode": "validation",
        "test_output": False,
        "checkpoint_sha256": checkpoint_sha256,
        "manifest_sha256": manifest_sha256,
        "predictions_csv_sha256": _sha256(predictions_csv_path),
        "row_count": row_count,
        "class_names": class_names,
        "class_to_index": class_to_index,
    }
    integrity.update(overrides)
    path = tmp_path / "validation_evaluation_integrity.json"
    path.write_text(json.dumps(integrity))
    return path


def _row(true_idx, pred_idx, prob, group, guard=""):
    return {
        "path": f"p_{true_idx}_{pred_idx}_{prob}_{group}",
        "true_class_name": CLASS_NAMES[true_idx],
        "true_class_index": true_idx,
        "predicted_class_name": CLASS_NAMES[pred_idx],
        "predicted_class_index": pred_idx,
        "maximum_probability": prob,
        "correct": true_idx == pred_idx,
        "group_key": group,
        "similarity_guard_group": guard,
    }


# 10 class-A rows: 8 correct high-confidence, 2 incorrect low-confidence.
# 10 class-B rows: all correct, but only high-confidence -- used to test
# zero-accepted-support behavior at a high threshold.
CRAFTED_ROWS = (
    [_row(0, 0, 0.95, f"gA{i}") for i in range(8)]
    + [_row(0, 1, 0.55, f"gA{i}") for i in range(8, 10)]
    + [_row(1, 1, 0.60, f"gB{i}") for i in range(10)]
)


def test_evaluate_threshold_matches_hand_computed_stats():
    result = st.evaluate_threshold(CRAFTED_ROWS, 0.9, CLASS_NAMES)
    # At threshold 0.9: only the 8 high-confidence class-A rows are accepted.
    assert result["total_samples"] == 20
    assert result["accepted_count"] == 8
    assert result["rejected_count"] == 12
    assert result["coverage"] == pytest.approx(8 / 20)
    assert result["selective_accuracy"] == pytest.approx(1.0)
    assert result["classes_with_zero_accepted_support"] == ["B"]


def test_selective_macro_metrics_match_sklearn():
    threshold = 0.5
    accepted = [r for r in CRAFTED_ROWS if r["maximum_probability"] >= threshold]
    y_true = [r["true_class_index"] for r in accepted]
    y_pred = [r["predicted_class_index"] for r in accepted]
    p, r, f1, _ = precision_recall_fscore_support(y_true, y_pred, labels=[0, 1], average="macro", zero_division=0)

    result = st.evaluate_threshold(CRAFTED_ROWS, threshold, CLASS_NAMES)
    assert result["selective_macro_precision"] == pytest.approx(p)
    assert result["selective_macro_recall"] == pytest.approx(r)
    assert result["selective_macro_f1"] == pytest.approx(f1)


def test_zero_accepted_class_does_not_crash_and_is_disclosed():
    result = st.evaluate_threshold(CRAFTED_ROWS, threshold=0.9, class_names=CLASS_NAMES)
    assert result["per_class"]["B"]["accepted_count"] == 0
    assert result["per_class"]["B"]["accepted_accuracy"] is None  # no ZeroDivisionError
    assert result["classes_with_zero_accepted_support"] == ["B"]
    assert st.constraints_pass(result) is False


def test_constraints_pass_requires_all_mandatory_rules():
    # threshold=0.5 accepts everything; class B has 10 accepted (>=15 fails).
    result = st.evaluate_threshold(CRAFTED_ROWS, threshold=0.5, class_names=CLASS_NAMES)
    assert st.constraints_pass(result) is False  # min_per_class_accepted_count=15 not met


def test_select_threshold_is_deterministic_across_repeated_calls():
    r1 = st.select_threshold(CRAFTED_ROWS, CLASS_NAMES)
    r2 = st.select_threshold(CRAFTED_ROWS, CLASS_NAMES)
    assert json.dumps(r1, sort_keys=True, default=str) == json.dumps(r2, sort_keys=True, default=str)


def test_select_threshold_blocked_when_no_candidate_passes():
    # This crafted set can never reach 15 accepted-per-class (only 10 rows/class),
    # so every candidate must fail and status must be blocked, with a Pareto frontier.
    result = st.select_threshold(CRAFTED_ROWS, CLASS_NAMES)
    assert result["status"] == "blocked_threshold_selection"
    assert result["selected_threshold"] is None
    assert isinstance(result["pareto_frontier"], list)
    assert len(result["pareto_frontier"]) > 0


def test_select_threshold_picks_lowest_passing_threshold_when_available():
    # Enough rows per class (20 each) so 15-accepted and 80% coverage are reachable.
    rows = (
        [_row(0, 0, 0.95, f"gA{i}") for i in range(18)]
        + [_row(0, 1, 0.55, f"gA{i}") for i in range(18, 20)]
        + [_row(1, 1, 0.90, f"gB{i}") for i in range(20)]
    )
    result = st.select_threshold(rows, CLASS_NAMES, grid=[0.5, 0.6, 0.9, 0.96])
    assert result["status"] == "approved_for_test_application"
    # threshold 0.5 accepts all 40 rows at 38/40=95% accuracy, which fails the
    # 99% mandatory accuracy floor. threshold 0.6 rejects the 2 low-confidence
    # errors, reaching 38/38=100% accepted accuracy -- the lowest passing rung.
    assert result["selected_threshold"] == 0.6


def test_confidence_policy_schema_has_required_fields():
    rows = (
        [_row(0, 0, 0.95, f"gA{i}") for i in range(18)]
        + [_row(0, 1, 0.55, f"gA{i}") for i in range(18, 20)]
        + [_row(1, 1, 0.90, f"gB{i}") for i in range(20)]
    )
    selection = st.select_threshold(rows, CLASS_NAMES, grid=[0.5, 0.6])
    policy = st.build_confidence_policy(selection, "ckpt-hash", "manifest-hash", "2026-01-01T00:00:00Z")

    required_fields = {
        "version", "status", "decision_source", "selection_dataset", "model_architecture",
        "checkpoint_sha256", "validation_manifest_sha256", "confidence_method", "selected_threshold",
        "selection_rule", "mandatory_constraints", "achieved_validation_coverage",
        "achieved_validation_selective_accuracy", "achieved_validation_selective_macro_f1",
        "per_class_validation_coverage", "limitations", "test_labels_used_for_threshold_selection",
        "statement", "created_at_utc",
    }
    assert required_fields.issubset(policy.keys())
    assert policy["status"] in ("approved_for_test_application", "blocked_threshold_selection")
    assert policy["test_labels_used_for_threshold_selection"] is False


def test_select_subcommand_has_no_test_manifest_argument():
    """select_threshold.py `select` must have no way to pass test-set data at all."""
    parser = st.build_arg_parser()
    sub_parser = parser._subparsers._group_actions[0].choices["select"]
    option_strings = {opt for a in sub_parser._actions for opt in a.option_strings}
    assert not any("test" in opt.lower() for opt in option_strings)


def test_apply_threshold_to_test_matches_evaluate_threshold():
    rows = [dict(r, accepted=r["maximum_probability"] >= 0.6) for r in CRAFTED_ROWS]
    applied = st.apply_threshold_to_test(rows, 0.6, CLASS_NAMES)
    direct = st.evaluate_threshold(rows, 0.6, CLASS_NAMES)
    assert applied == direct


def test_apply_threshold_to_test_rejects_inconsistent_accepted_column():
    rows = [dict(r, accepted=True) for r in CRAFTED_ROWS]  # wrong: should depend on 0.6 threshold
    with pytest.raises(st.ThresholdSelectionError, match="integrity failure"):
        st.apply_threshold_to_test(rows, 0.6, CLASS_NAMES)


def test_cmd_apply_rejects_checkpoint_hash_mismatch(tmp_path):
    policy = {
        "status": "approved_for_test_application",
        "selected_threshold": 0.6,
        "checkpoint_sha256": "AAA",
    }
    policy_path = tmp_path / "confidence_policy_v1.json"
    policy_path.write_text(json.dumps(policy))

    eval_hashes = {"checkpoint_sha256": "BBB", "mode": "final-test", "manifest_sha256": "irrelevant"}
    eval_hashes_path = tmp_path / "evaluation_manifest_hashes.json"
    eval_hashes_path.write_text(json.dumps(eval_hashes))

    predictions_path = tmp_path / "test_predictions.csv"
    predictions_path.write_text("path\n")  # never reached; hash check must fail first

    args = argparse.Namespace(
        test_predictions_csv=predictions_path,
        confidence_policy_json=policy_path,
        evaluation_manifest_hashes_json=eval_hashes_path,
        output_dir=tmp_path / "out",
        bootstrap_iterations=10,
        bootstrap_seed=42,
        calibration_bins=5,
    )
    with pytest.raises(st.ThresholdSelectionError, match="checkpoint_sha256 mismatch"):
        st._cmd_apply(args)


def test_cmd_apply_rejects_unapproved_policy_status(tmp_path):
    policy = {"status": "blocked_threshold_selection", "selected_threshold": None, "checkpoint_sha256": "AAA"}
    policy_path = tmp_path / "confidence_policy_v1.json"
    policy_path.write_text(json.dumps(policy))
    eval_hashes_path = tmp_path / "evaluation_manifest_hashes.json"
    eval_hashes_path.write_text(json.dumps({"checkpoint_sha256": "AAA", "mode": "final-test"}))

    args = argparse.Namespace(
        test_predictions_csv=tmp_path / "does_not_matter.csv",
        confidence_policy_json=policy_path,
        evaluation_manifest_hashes_json=eval_hashes_path,
        output_dir=tmp_path / "out",
        bootstrap_iterations=10,
        bootstrap_seed=42,
        calibration_bins=5,
    )
    with pytest.raises(st.ThresholdSelectionError, match="not 'approved_for_test_application'"):
        st._cmd_apply(args)


# ---------------------------------------------------------------------------
# Bootstrap determinism and group-awareness
# ---------------------------------------------------------------------------

def test_bootstrap_image_level_is_deterministic():
    r1 = st.bootstrap_image_level(CRAFTED_ROWS, CLASS_NAMES, "raw_accuracy", n_iterations=200, seed=42)
    r2 = st.bootstrap_image_level(CRAFTED_ROWS, CLASS_NAMES, "raw_accuracy", n_iterations=200, seed=42)
    assert r1 == r2


def test_bootstrap_group_aware_is_deterministic():
    r1 = st.bootstrap_group_aware(CRAFTED_ROWS, CLASS_NAMES, "raw_accuracy", n_iterations=200, seed=42)
    r2 = st.bootstrap_group_aware(CRAFTED_ROWS, CLASS_NAMES, "raw_accuracy", n_iterations=200, seed=42)
    assert r1 == r2


def test_bootstrap_group_aware_widens_ci_under_within_group_correlation():
    """20 groups of 5 perfectly-correlated rows (all-correct or all-wrong per
    group) should give the group-aware bootstrap a visibly wider CI than the
    naive image-level bootstrap, which treats each row as independent."""
    rows = []
    rng = np.random.default_rng(0)
    for g in range(20):
        all_correct = rng.random() > 0.2  # most groups fully correct, a few fully wrong
        for i in range(5):
            true_idx = 0
            pred_idx = 0 if all_correct else 1
            rows.append(_row(true_idx, pred_idx, 0.9, f"corr_g{g}"))

    group_aware = st.bootstrap_group_aware(rows, CLASS_NAMES, "raw_accuracy", n_iterations=1000, seed=42)
    image_level = st.bootstrap_image_level(rows, CLASS_NAMES, "raw_accuracy", n_iterations=1000, seed=42)

    group_width = group_aware["ci_upper_95"] - group_aware["ci_lower_95"]
    image_width = image_level["ci_upper_95"] - image_level["ci_lower_95"]
    assert group_width > image_width


def test_reliability_analysis_handles_all_correct_without_error():
    rows = [_row(0, 0, 0.95, f"g{i}") for i in range(10)]
    result = st.reliability_analysis(rows, num_bins=5)
    assert result["expected_calibration_error"] >= 0.0
    assert result["confidence_distribution_incorrect"]["count"] == 0


# ---------------------------------------------------------------------------
# Tie-break falsy-zero bug fix (m1)
# ---------------------------------------------------------------------------

def test_tie_break_key_preserves_zero_macro_f1():
    """A legitimate selective_macro_f1 of exactly 0.0 must rank strictly
    better than a missing (None) macro-F1, not be conflated with it."""
    zero_f1 = {"coverage": 0.9, "selective_macro_f1": 0.0, "threshold": 0.5}
    none_f1 = {"coverage": 0.9, "selective_macro_f1": None, "threshold": 0.5}
    positive_f1 = {"coverage": 0.9, "selective_macro_f1": 0.2, "threshold": 0.5}

    keyed = sorted([none_f1, zero_f1, positive_f1], key=st._tie_break_key)
    assert keyed == [positive_f1, zero_f1, none_f1]


def test_tie_break_key_ranks_coverage_above_macro_f1():
    higher_coverage_lower_f1 = {"coverage": 0.95, "selective_macro_f1": 0.1, "threshold": 0.5}
    lower_coverage_higher_f1 = {"coverage": 0.90, "selective_macro_f1": 0.9, "threshold": 0.5}
    keyed = sorted([lower_coverage_higher_f1, higher_coverage_lower_f1], key=st._tie_break_key)
    assert keyed[0] is higher_coverage_lower_f1


# ---------------------------------------------------------------------------
# Validation-evaluation integrity verification (C1 fix)
# ---------------------------------------------------------------------------

CLASS_TO_INDEX_AB = {"A": 0, "B": 1}


def _valid_integrity_setup(tmp_path):
    predictions_csv = tmp_path / "validation_predictions.csv"
    _write_predictions_csv(
        predictions_csv,
        [
            {"path": "p1", "true_class_name": "A", "true_class_index": 0, "predicted_class_name": "A",
             "predicted_class_index": 0, "maximum_probability": 0.9, "correct": True, "group_key": "g1"},
            {"path": "p2", "true_class_name": "B", "true_class_index": 1, "predicted_class_name": "B",
             "predicted_class_index": 1, "maximum_probability": 0.8, "correct": True, "group_key": "g2"},
        ],
    )
    integrity_path = _write_integrity(
        tmp_path, predictions_csv, "ckpt-hash", "manifest-hash", CLASS_TO_INDEX_AB,
    )
    with open(integrity_path) as f:
        integrity = json.load(f)
    return predictions_csv, integrity


def test_verify_validation_integrity_accepts_valid_record(tmp_path):
    predictions_csv, integrity = _valid_integrity_setup(tmp_path)
    st.verify_validation_integrity(integrity, predictions_csv, "ckpt-hash", "manifest-hash", CLASS_TO_INDEX_AB)


def test_verify_validation_integrity_rejects_final_test_declared_mode(tmp_path):
    predictions_csv, integrity = _valid_integrity_setup(tmp_path)
    integrity["evaluation_mode"] = "final-test"
    with pytest.raises(st.ThresholdSelectionError, match="evaluation_mode"):
        st.verify_validation_integrity(integrity, predictions_csv, "ckpt-hash", "manifest-hash", CLASS_TO_INDEX_AB)


def test_verify_validation_integrity_rejects_test_output_true(tmp_path):
    predictions_csv, integrity = _valid_integrity_setup(tmp_path)
    integrity["test_output"] = True
    with pytest.raises(st.ThresholdSelectionError, match="test_output"):
        st.verify_validation_integrity(integrity, predictions_csv, "ckpt-hash", "manifest-hash", CLASS_TO_INDEX_AB)


def test_verify_validation_integrity_rejects_predictions_hash_mismatch(tmp_path):
    predictions_csv, integrity = _valid_integrity_setup(tmp_path)
    integrity["predictions_csv_sha256"] = "not-the-real-hash"
    with pytest.raises(st.ThresholdSelectionError, match="predictions_csv_sha256"):
        st.verify_validation_integrity(integrity, predictions_csv, "ckpt-hash", "manifest-hash", CLASS_TO_INDEX_AB)


def test_verify_validation_integrity_rejects_manifest_hash_mismatch(tmp_path):
    predictions_csv, integrity = _valid_integrity_setup(tmp_path)
    with pytest.raises(st.ThresholdSelectionError, match="manifest_sha256"):
        st.verify_validation_integrity(
            integrity, predictions_csv, "ckpt-hash", "a-different-approved-manifest-hash", CLASS_TO_INDEX_AB,
        )


def test_verify_validation_integrity_rejects_checkpoint_hash_mismatch(tmp_path):
    predictions_csv, integrity = _valid_integrity_setup(tmp_path)
    with pytest.raises(st.ThresholdSelectionError, match="checkpoint_sha256"):
        st.verify_validation_integrity(
            integrity, predictions_csv, "a-different-approved-checkpoint-hash", "manifest-hash", CLASS_TO_INDEX_AB,
        )


def test_verify_validation_integrity_rejects_row_count_mismatch(tmp_path):
    predictions_csv, integrity = _valid_integrity_setup(tmp_path)
    integrity["row_count"] = 999
    with pytest.raises(st.ThresholdSelectionError, match="row_count"):
        st.verify_validation_integrity(integrity, predictions_csv, "ckpt-hash", "manifest-hash", CLASS_TO_INDEX_AB)


def test_verify_validation_integrity_rejects_class_mapping_mismatch(tmp_path):
    predictions_csv, integrity = _valid_integrity_setup(tmp_path)
    with pytest.raises(st.ThresholdSelectionError, match="class_to_index"):
        st.verify_validation_integrity(
            integrity, predictions_csv, "ckpt-hash", "manifest-hash", {"A": 0, "B": 1, "C": 2},
        )


def test_cmd_select_rejects_a_final_test_predictions_csv_substituted_as_validation_input(tmp_path):
    """The concrete attack this whole guard exists for: pointing
    --validation-predictions-csv at a final-test (test-derived) CSV must be
    refused, and no output files (least of all confidence_policy_v1.json)
    may be written as a result."""
    test_predictions_csv = tmp_path / "test_predictions.csv"
    _write_predictions_csv(
        test_predictions_csv,
        [
            {"path": "p1", "true_class_name": "A", "true_class_index": 0, "predicted_class_name": "A",
             "predicted_class_index": 0, "maximum_probability": 0.9, "correct": True, "group_key": "g1"},
        ],
    )
    # An integrity file that honestly declares this is test-derived output.
    integrity_path = _write_integrity(
        tmp_path, test_predictions_csv, "ckpt-hash", "manifest-hash", CLASS_TO_INDEX_AB,
        evaluation_mode="final-test", test_output=True,
    )
    class_map_path, model_scope_path = _write_class_map_and_scope(tmp_path, CLASS_TO_INDEX_AB)
    output_dir = tmp_path / "out"
    policy_output = tmp_path / "confidence_policy_v1.json"

    args = argparse.Namespace(
        validation_predictions_csv=test_predictions_csv,
        validation_integrity_json=integrity_path,
        class_map=class_map_path,
        model_scope=model_scope_path,
        checkpoint_sha256="ckpt-hash",
        validation_manifest_sha256="manifest-hash",
        output_dir=output_dir,
        confidence_policy_output=policy_output,
    )
    with pytest.raises(st.ThresholdSelectionError, match="evaluation_mode"):
        st._cmd_select(args)

    assert not output_dir.exists()
    assert not policy_output.exists()


def test_cmd_select_succeeds_with_valid_integrity_record(tmp_path):
    predictions_csv = tmp_path / "validation_predictions.csv"
    rows = (
        [{"path": f"a{i}", "true_class_name": "A", "true_class_index": 0, "predicted_class_name": "A",
          "predicted_class_index": 0, "maximum_probability": 0.95, "correct": True, "group_key": f"ga{i}"}
         for i in range(18)]
        + [{"path": f"a{i}", "true_class_name": "A", "true_class_index": 0, "predicted_class_name": "B",
            "predicted_class_index": 1, "maximum_probability": 0.55, "correct": False, "group_key": f"ga{i}"}
           for i in range(18, 20)]
        + [{"path": f"b{i}", "true_class_name": "B", "true_class_index": 1, "predicted_class_name": "B",
            "predicted_class_index": 1, "maximum_probability": 0.90, "correct": True, "group_key": f"gb{i}"}
           for i in range(20)]
    )
    _write_predictions_csv(predictions_csv, rows)
    integrity_path = _write_integrity(tmp_path, predictions_csv, "ckpt-hash", "manifest-hash", CLASS_TO_INDEX_AB)
    class_map_path, model_scope_path = _write_class_map_and_scope(tmp_path, CLASS_TO_INDEX_AB)
    output_dir = tmp_path / "out"
    policy_output = tmp_path / "confidence_policy_v1.json"

    args = argparse.Namespace(
        validation_predictions_csv=predictions_csv,
        validation_integrity_json=integrity_path,
        class_map=class_map_path,
        model_scope=model_scope_path,
        checkpoint_sha256="ckpt-hash",
        validation_manifest_sha256="manifest-hash",
        output_dir=output_dir,
        confidence_policy_output=policy_output,
    )
    result = st._cmd_select(args)
    assert result["status"] == "approved_for_test_application"
    assert policy_output.exists()
    policy = json.loads(policy_output.read_text())
    assert policy["selected_threshold"] == result["selected_threshold"]


def test_select_subcommand_requires_integrity_and_class_map_arguments():
    parser = st.build_arg_parser()
    sub_parser = parser._subparsers._group_actions[0].choices["select"]
    option_strings = {opt for a in sub_parser._actions for opt in a.option_strings}
    assert "--validation-integrity-json" in option_strings
    assert "--class-map" in option_strings
    assert "--model-scope" in option_strings
