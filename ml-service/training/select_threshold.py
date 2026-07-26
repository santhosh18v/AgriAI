"""M5 confidence-threshold selection and (post-freeze) test-side application.

Two subcommands:

- `select`: reads a validation_predictions.csv (produced by
  `evaluate.py --mode validation`), evaluates a deterministic candidate
  grid using validation labels ONLY, applies a predeclared mandatory-rule
  selection policy, and writes threshold_candidates.json,
  threshold_selection.json, and the tracked confidence_policy_v1.json.
  Test labels are never read, referenced, or accepted as input by this
  subcommand -- it has no test-manifest argument at all. It also requires a
  companion `validation_evaluation_integrity.json` (from the same
  `evaluate.py --mode validation` run) and cryptographically verifies the
  predictions CSV's hash, row count, checkpoint, manifest, and class mapping
  against it before evaluating any candidate -- a schema-compatible CSV from
  elsewhere (including a final-test run) cannot be substituted silently.

- `apply`: given a test_predictions.csv (produced by
  `evaluate.py --mode final-test --apply-threshold <frozen threshold>`)
  and the frozen confidence_policy_v1.json, computes threshold-applied test
  metrics, a raw-confidence calibration analysis, group-aware and
  image-level bootstrap confidence intervals, and a structured error
  analysis. It cross-checks (does not re-derive) that the frozen threshold
  and checkpoint hash match the policy file, and never changes the
  threshold.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from sklearn.metrics import precision_recall_fscore_support

# ---------------------------------------------------------------------------
# Predeclared candidate grid and mandatory selection rule (Section 4/5 of the
# M5 instructions). Fixed grid chosen over "all unique observed confidence
# values" for a stable, reviewable candidate count independent of how many
# distinct softmax values a given run happens to produce.
# ---------------------------------------------------------------------------

CANDIDATE_GRID = [round(0.50 + 0.01 * i, 2) for i in range(50)]  # 0.50 .. 0.99 inclusive

MANDATORY_RULES = {
    "min_accepted_accuracy": 0.99,
    "min_overall_coverage": 0.90,
    "min_per_class_coverage": 0.80,
    "min_per_class_accepted_count": 15,
}

SELECTION_RULE_DESCRIPTION = (
    "Predeclared before viewing test labels. Candidate grid: fixed values "
    "0.50-0.99 in steps of 0.01 (50 candidates), evaluated on validation "
    "predictions only. A threshold passes iff: accepted accuracy >= 99.0%, "
    "overall coverage >= 90%, every class retains >= 80% coverage, every "
    "class retains >= 15 accepted validation images, and no class has zero "
    "accepted support. Among passing thresholds, select by: (1) highest "
    "overall coverage, (2) tie-break higher selective macro-F1, (3) then "
    "lower threshold, (4) then deterministic numeric ordering. If no "
    "threshold passes, no threshold is selected; the Pareto frontier over "
    "(coverage, selective accuracy) is reported instead for explicit user "
    "review."
)


class ThresholdSelectionError(Exception):
    pass


# ---------------------------------------------------------------------------
# Validation-evaluation integrity verification (closes the gap where this
# script could otherwise be pointed at any schema-compatible CSV -- including
# test-derived predictions -- through --validation-predictions-csv with no
# proof of provenance). Kept dependency-light (hashlib/json only, no torch)
# since this script never runs model inference.
# ---------------------------------------------------------------------------

def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_expected_class_to_index(class_map_path: Path, model_scope_path: Path) -> dict:
    with open(class_map_path) as f:
        class_map = json.load(f)
    class_index_by_name = {name: int(idx) for idx, name in class_map.items()}

    with open(model_scope_path) as f:
        model_scope = json.load(f)
    if model_scope.get("status") != "approved":
        raise ThresholdSelectionError(
            f"model_scope status is {model_scope.get('status')!r}, expected 'approved'"
        )
    active = model_scope.get("active_model_classes", [])
    return {name: class_index_by_name[name] for name in active}


def verify_validation_integrity(
    integrity: dict,
    predictions_csv_path: Path,
    expected_checkpoint_sha256: str,
    expected_validation_manifest_sha256: str,
    expected_class_to_index: dict,
) -> None:
    """Verifies a validation_evaluation_integrity.json (produced by
    `evaluate.py --mode validation`) actually ties `predictions_csv_path` to
    the approved frozen validation manifest and checkpoint, before any
    threshold candidate is evaluated. Raises ThresholdSelectionError on any
    mismatch; callers must not write or overwrite confidence_policy_v1.json
    if this raises."""
    if integrity.get("evaluation_mode") != "validation":
        raise ThresholdSelectionError(
            f"validation-integrity file has evaluation_mode={integrity.get('evaluation_mode')!r}, "
            "expected 'validation'. Refusing threshold selection."
        )
    if integrity.get("test_output") is not False:
        raise ThresholdSelectionError(
            "validation-integrity file does not explicitly declare test_output: false. Refusing "
            "to select a threshold from predictions that may be test-derived."
        )
    if integrity.get("checkpoint_sha256") != expected_checkpoint_sha256:
        raise ThresholdSelectionError(
            f"validation-integrity checkpoint_sha256 {integrity.get('checkpoint_sha256')} does not "
            f"match --checkpoint-sha256 {expected_checkpoint_sha256}."
        )
    if integrity.get("manifest_sha256") != expected_validation_manifest_sha256:
        raise ThresholdSelectionError(
            f"validation-integrity manifest_sha256 {integrity.get('manifest_sha256')} does not "
            f"match --validation-manifest-sha256 {expected_validation_manifest_sha256}."
        )
    actual_predictions_sha256 = _sha256_file(predictions_csv_path)
    if integrity.get("predictions_csv_sha256") != actual_predictions_sha256:
        raise ThresholdSelectionError(
            f"validation-integrity predictions_csv_sha256 {integrity.get('predictions_csv_sha256')} "
            f"does not match the actual SHA-256 of {predictions_csv_path} "
            f"({actual_predictions_sha256}). Refusing threshold selection."
        )
    with open(predictions_csv_path, newline="", encoding="utf-8") as f:
        actual_row_count = sum(1 for _ in csv.DictReader(f))
    if integrity.get("row_count") != actual_row_count:
        raise ThresholdSelectionError(
            f"validation-integrity row_count {integrity.get('row_count')} does not match the "
            f"actual predictions row count {actual_row_count}."
        )
    if integrity.get("class_to_index") != expected_class_to_index:
        raise ThresholdSelectionError(
            f"validation-integrity class_to_index {integrity.get('class_to_index')} does not "
            f"match the approved class map/model scope {expected_class_to_index}."
        )
    expected_class_names = [name for name, _ in sorted(expected_class_to_index.items(), key=lambda kv: kv[1])]
    if integrity.get("class_names") != expected_class_names:
        raise ThresholdSelectionError(
            f"validation-integrity class_names {integrity.get('class_names')} does not match the "
            f"expected class order {expected_class_names}."
        )


# ---------------------------------------------------------------------------
# select: validation-only candidate evaluation
# ---------------------------------------------------------------------------

def load_predictions_csv(csv_path: Path) -> list[dict]:
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ThresholdSelectionError(f"{csv_path}: empty or unreadable predictions CSV")
        for row in reader:
            rows.append(
                {
                    "path": row["path"],
                    "true_class_name": row["true_class_name"],
                    "true_class_index": int(row["true_class_index"]),
                    "predicted_class_name": row["predicted_class_name"],
                    "predicted_class_index": int(row["predicted_class_index"]),
                    "maximum_probability": float(row["maximum_probability"]),
                    "correct": row["correct"] in ("True", "true", "1"),
                    "group_key": row["group_key"],
                    "similarity_guard_group": row["similarity_guard_group"],
                }
            )
    if not rows:
        raise ThresholdSelectionError(f"{csv_path}: contains zero rows")
    return rows


def _class_names_from_rows(rows: list[dict]) -> list[str]:
    by_index: dict[int, str] = {}
    for r in rows:
        by_index[r["true_class_index"]] = r["true_class_name"]
    return [by_index[i] for i in sorted(by_index)]


def evaluate_threshold(rows: list[dict], threshold: float, class_names: list[str]) -> dict:
    total = len(rows)
    accepted_rows = [r for r in rows if r["maximum_probability"] >= threshold]
    rejected_rows = [r for r in rows if r["maximum_probability"] < threshold]
    accepted = len(accepted_rows)
    rejected = len(rejected_rows)
    coverage = accepted / total if total else 0.0

    accepted_correct_count = sum(1 for r in accepted_rows if r["correct"])
    selective_accuracy = accepted_correct_count / accepted if accepted else None

    labels = list(range(len(class_names)))
    accepted_support = {i: 0 for i in labels}
    for r in accepted_rows:
        accepted_support[r["true_class_index"]] += 1
    classes_with_zero_accepted_support = [class_names[i] for i in labels if accepted_support[i] == 0]

    if accepted:
        y_true_acc = [r["true_class_index"] for r in accepted_rows]
        y_pred_acc = [r["predicted_class_index"] for r in accepted_rows]
        p, r_, f1, _ = precision_recall_fscore_support(
            y_true_acc, y_pred_acc, labels=labels, average="macro", zero_division=0
        )
        selective_macro_precision, selective_macro_recall, selective_macro_f1 = float(p), float(r_), float(f1)
    else:
        selective_macro_precision = selective_macro_recall = selective_macro_f1 = None

    total_errors = sum(1 for r in rows if not r["correct"])
    rejected_errors = sum(1 for r in rejected_rows if not r["correct"])
    error_rejection_rate = rejected_errors / total_errors if total_errors else None

    total_correct = sum(1 for r in rows if r["correct"])
    rejected_correct = sum(1 for r in rejected_rows if r["correct"])
    correct_rejection_rate = rejected_correct / total_correct if total_correct else None

    per_class = {}
    for i, name in enumerate(class_names):
        class_rows = [r for r in rows if r["true_class_index"] == i]
        class_total = len(class_rows)
        class_accepted_rows = [r for r in class_rows if r["maximum_probability"] >= threshold]
        class_accepted = len(class_accepted_rows)
        class_coverage = class_accepted / class_total if class_total else None
        class_accepted_correct = sum(1 for r in class_accepted_rows if r["correct"])
        class_accepted_accuracy = class_accepted_correct / class_accepted if class_accepted else None
        per_class[name] = {
            "total_validation_samples": class_total,
            "accepted_count": class_accepted,
            "coverage": class_coverage,
            "accepted_accuracy": class_accepted_accuracy,
        }

    accepted_errors = accepted - accepted_correct_count

    return {
        "threshold": threshold,
        "total_samples": total,
        "accepted_count": accepted,
        "rejected_count": rejected,
        "coverage": coverage,
        "selective_accuracy": selective_accuracy,
        "selective_macro_precision": selective_macro_precision,
        "selective_macro_recall": selective_macro_recall,
        "selective_macro_f1": selective_macro_f1,
        "accepted_errors": accepted_errors,
        "error_rejection_rate": error_rejection_rate,
        "correct_rejection_rate": correct_rejection_rate,
        "classes_with_zero_accepted_support": classes_with_zero_accepted_support,
        "per_class": per_class,
    }


def constraints_pass(candidate: dict, rules: dict = MANDATORY_RULES) -> bool:
    if candidate["selective_accuracy"] is None or candidate["selective_accuracy"] < rules["min_accepted_accuracy"]:
        return False
    if candidate["coverage"] < rules["min_overall_coverage"]:
        return False
    if candidate["classes_with_zero_accepted_support"]:
        return False
    for stats in candidate["per_class"].values():
        if stats["coverage"] is None or stats["coverage"] < rules["min_per_class_coverage"]:
            return False
        if stats["accepted_count"] < rules["min_per_class_accepted_count"]:
            return False
    return True


def _pareto_frontier(candidates: list[dict]) -> list[dict]:
    """Non-dominated candidates in (coverage, selective_accuracy) space
    (maximize both). Descriptive only -- never used to auto-select."""
    valid = [c for c in candidates if c["selective_accuracy"] is not None]
    frontier = []
    for c in valid:
        dominated = False
        for other in valid:
            if other is c:
                continue
            if (
                other["coverage"] >= c["coverage"]
                and other["selective_accuracy"] >= c["selective_accuracy"]
                and (other["coverage"] > c["coverage"] or other["selective_accuracy"] > c["selective_accuracy"])
            ):
                dominated = True
                break
        if not dominated:
            frontier.append(
                {
                    "threshold": c["threshold"],
                    "coverage": c["coverage"],
                    "selective_accuracy": c["selective_accuracy"],
                    "selective_macro_f1": c["selective_macro_f1"],
                }
            )
    frontier.sort(key=lambda x: x["threshold"])
    return frontier


def _tie_break_key(c: dict) -> tuple:
    """Deterministic ordered tie-break: (1) highest coverage, (2) higher
    selective macro-F1, (3) lower threshold, (4) numeric order (implied by
    (3), included for explicitness/determinism).

    Uses an explicit `is not None` check rather than `x or -1.0`: macro-F1 of
    exactly 0.0 is a legitimate (if unlikely, given the surrounding mandatory
    constraints) value and must not be treated as falsy/missing -- `0.0 or
    -1.0` would silently evaluate to -1.0 in Python and misrank it as if no
    macro-F1 were available at all.
    """
    macro_f1 = c["selective_macro_f1"]
    macro_f1_component = macro_f1 if macro_f1 is not None else -1.0
    return (-c["coverage"], -macro_f1_component, c["threshold"])


def select_threshold(rows: list[dict], class_names: list[str], grid: list[float] = CANDIDATE_GRID) -> dict:
    candidates = [evaluate_threshold(rows, t, class_names) for t in grid]
    for c in candidates:
        c["passes_mandatory_constraints"] = constraints_pass(c)

    passing = [c for c in candidates if c["passes_mandatory_constraints"]]
    if not passing:
        return {
            "status": "blocked_threshold_selection",
            "candidate_count": len(candidates),
            "candidates": candidates,
            "selected_threshold": None,
            "pareto_frontier": _pareto_frontier(candidates),
        }

    passing_sorted = sorted(passing, key=_tie_break_key)
    chosen = passing_sorted[0]
    return {
        "status": "approved_for_test_application",
        "candidate_count": len(candidates),
        "candidates": candidates,
        "selected_threshold": chosen["threshold"],
        "selected_candidate": chosen,
    }


def build_confidence_policy(
    selection_result: dict,
    checkpoint_sha256: str,
    validation_manifest_sha256: str,
    created_at_utc: str,
) -> dict:
    status = selection_result["status"]
    policy = {
        "version": 1,
        "status": status,
        "decision_source": "predeclared_rule_applied_to_validation_predictions_only",
        "selection_dataset": "validation",
        "model_architecture": "efficientnet_b0",
        "checkpoint_sha256": checkpoint_sha256,
        "validation_manifest_sha256": validation_manifest_sha256,
        "confidence_method": "maximum_softmax_probability",
        "selected_threshold": selection_result.get("selected_threshold"),
        "selection_rule": SELECTION_RULE_DESCRIPTION,
        "mandatory_constraints": MANDATORY_RULES,
        "achieved_validation_coverage": None,
        "achieved_validation_selective_accuracy": None,
        "achieved_validation_selective_macro_f1": None,
        "per_class_validation_coverage": None,
        "limitations": [
            "Potato Healthy validation support is 24 images from only 6 independent "
            "physical-leaf groups; its threshold statistics carry high uncertainty and "
            "are not claimed to be production-calibrated.",
            "Threshold selection used one single global threshold across all 6 classes; "
            "no class-specific threshold was selected in M5.",
            "Candidate grid is a fixed 0.50-0.99 step-0.01 grid, not every unique observed "
            "confidence value.",
            "Softmax confidence is a model score, not a guaranteed true probability; it must not "
            "be presented as certainty.",
            "This threshold and model are not production-calibrated; no production-readiness "
            "claim is made.",
        ],
        "test_labels_used_for_threshold_selection": False,
        "statement": (
            "Test labels were not used, read, or referenced at any point during threshold "
            "selection. Threshold selection used validation predictions only."
        ),
        "created_at_utc": created_at_utc,
    }
    if status == "approved_for_test_application":
        chosen = selection_result["selected_candidate"]
        policy["achieved_validation_coverage"] = chosen["coverage"]
        policy["achieved_validation_selective_accuracy"] = chosen["selective_accuracy"]
        policy["achieved_validation_selective_macro_f1"] = chosen["selective_macro_f1"]
        policy["per_class_validation_coverage"] = {
            name: stats["coverage"] for name, stats in chosen["per_class"].items()
        }
    return policy


# ---------------------------------------------------------------------------
# apply: frozen-threshold application to test predictions + analysis
# ---------------------------------------------------------------------------

def load_test_predictions_csv(csv_path: Path) -> list[dict]:
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if "accepted" not in (reader.fieldnames or []):
            raise ThresholdSelectionError(
                f"{csv_path}: missing 'accepted' column -- was evaluate.py run with "
                "--apply-threshold?"
            )
        for row in reader:
            rows.append(
                {
                    "path": row["path"],
                    "true_class_name": row["true_class_name"],
                    "true_class_index": int(row["true_class_index"]),
                    "predicted_class_name": row["predicted_class_name"],
                    "predicted_class_index": int(row["predicted_class_index"]),
                    "maximum_probability": float(row["maximum_probability"]),
                    "accepted": row["accepted"] in ("True", "true", "1"),
                    "correct": row["correct"] in ("True", "true", "1"),
                    "group_key": row["group_key"],
                    "similarity_guard_group": row["similarity_guard_group"],
                    "probabilities": json.loads(row["probabilities"]),
                }
            )
    if not rows:
        raise ThresholdSelectionError(f"{csv_path}: contains zero rows")
    return rows


def apply_threshold_to_test(rows: list[dict], threshold: float, class_names: list[str]) -> dict:
    """Recomputes accepted from maximum_probability and cross-checks it
    against the CSV's own 'accepted' column (integrity check), then reuses
    the same candidate-metric logic as validation selection (test labels are
    read here only for descriptive reporting -- never for choosing or
    changing the threshold, which is passed in already frozen)."""
    for r in rows:
        recomputed = r["maximum_probability"] >= threshold
        if recomputed != r["accepted"]:
            raise ThresholdSelectionError(
                f"accepted-column integrity failure for {r['path']!r}: CSV says "
                f"{r['accepted']} but recomputing against frozen threshold {threshold} gives "
                f"{recomputed}"
            )
    return evaluate_threshold(rows, threshold, class_names)


# ---------------------------------------------------------------------------
# Calibration analysis (raw softmax confidence only; Section 7)
# ---------------------------------------------------------------------------

def reliability_analysis(rows: list[dict], num_bins: int = 10) -> dict:
    confidences = np.array([r["maximum_probability"] for r in rows], dtype=float)
    correctness = np.array([1.0 if r["correct"] else 0.0 for r in rows], dtype=float)

    bin_edges = np.linspace(0.0, 1.0, num_bins + 1)
    bin_indices = np.clip(np.digitize(confidences, bin_edges[1:-1], right=True), 0, num_bins - 1)

    bins = []
    ece = 0.0
    mce = 0.0
    n = len(rows)
    for b in range(num_bins):
        mask = bin_indices == b
        count = int(mask.sum())
        if count == 0:
            bins.append(
                {
                    "bin_lower": float(bin_edges[b]),
                    "bin_upper": float(bin_edges[b + 1]),
                    "count": 0,
                    "avg_confidence": None,
                    "avg_accuracy": None,
                    "gap": None,
                }
            )
            continue
        avg_conf = float(confidences[mask].mean())
        avg_acc = float(correctness[mask].mean())
        gap = abs(avg_conf - avg_acc)
        ece += (count / n) * gap
        mce = max(mce, gap)
        bins.append(
            {
                "bin_lower": float(bin_edges[b]),
                "bin_upper": float(bin_edges[b + 1]),
                "count": count,
                "avg_confidence": avg_conf,
                "avg_accuracy": avg_acc,
                "gap": gap,
            }
        )

    brier = float(np.mean((confidences - correctness) ** 2))

    correct_conf = confidences[correctness == 1.0]
    incorrect_conf = confidences[correctness == 0.0]

    def _dist(arr: np.ndarray) -> dict:
        if arr.size == 0:
            return {"count": 0, "mean": None, "min": None, "max": None, "median": None}
        return {
            "count": int(arr.size),
            "mean": float(arr.mean()),
            "min": float(arr.min()),
            "max": float(arr.max()),
            "median": float(np.median(arr)),
        }

    return {
        "method": "raw_softmax_confidence_no_calibration",
        "num_bins": num_bins,
        "reliability_bins": bins,
        "expected_calibration_error": ece,
        "maximum_calibration_error": mce,
        "brier_score": brier,
        "confidence_distribution_correct": _dist(correct_conf),
        "confidence_distribution_incorrect": _dist(incorrect_conf),
        "note": (
            "Raw maximum-softmax-probability confidence only. No temperature scaling or "
            "other calibration was fitted or applied in M5; this is the simplest defensible "
            "baseline per the M5 instructions."
        ),
    }


# ---------------------------------------------------------------------------
# Bootstrap confidence intervals (Section 12)
# ---------------------------------------------------------------------------

def _accuracy(rows: list[dict]) -> float:
    return sum(1 for r in rows if r["correct"]) / len(rows) if rows else float("nan")


def _macro_f1(rows: list[dict], class_names: list[str]) -> float:
    labels = list(range(len(class_names)))
    y_true = [r["true_class_index"] for r in rows]
    y_pred = [r["predicted_class_index"] for r in rows]
    _, _, f1, _ = precision_recall_fscore_support(y_true, y_pred, labels=labels, average="macro", zero_division=0)
    return float(f1)


def _selective_accuracy(rows: list[dict]) -> float:
    accepted = [r for r in rows if r["accepted"]]
    return _accuracy(accepted) if accepted else float("nan")


def _coverage(rows: list[dict]) -> float:
    return sum(1 for r in rows if r["accepted"]) / len(rows) if rows else float("nan")


METRIC_FUNCTIONS = {
    "raw_accuracy": lambda rows, class_names: _accuracy(rows),
    "raw_macro_f1": _macro_f1,
    "thresholded_selective_accuracy": lambda rows, class_names: _selective_accuracy(rows),
    "thresholded_coverage": lambda rows, class_names: _coverage(rows),
}


def bootstrap_image_level(rows: list[dict], class_names: list[str], metric_name: str, n_iterations: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    n = len(rows)
    metric_fn = METRIC_FUNCTIONS[metric_name]
    values = []
    for _ in range(n_iterations):
        idx = rng.integers(0, n, size=n)
        sample = [rows[i] for i in idx]
        values.append(metric_fn(sample, class_names))
    values = np.array(values, dtype=float)
    return _summarize_bootstrap(values, metric_name, "image_level", n_iterations, seed)


def bootstrap_group_aware(rows: list[dict], class_names: list[str], metric_name: str, n_iterations: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r["group_key"], []).append(r)
    group_keys = sorted(groups.keys())  # deterministic order before RNG draws
    n_groups = len(group_keys)
    metric_fn = METRIC_FUNCTIONS[metric_name]
    values = []
    for _ in range(n_iterations):
        idx = rng.integers(0, n_groups, size=n_groups)
        sample: list[dict] = []
        for i in idx:
            sample.extend(groups[group_keys[i]])
        values.append(metric_fn(sample, class_names))
    values = np.array(values, dtype=float)
    return _summarize_bootstrap(values, metric_name, "group_aware", n_iterations, seed, n_groups=n_groups)


def _summarize_bootstrap(values: np.ndarray, metric_name: str, method: str, n_iterations: int, seed: int, n_groups: int | None = None) -> dict:
    result = {
        "metric": metric_name,
        "method": method,
        "n_iterations": n_iterations,
        "seed": seed,
        "point_estimate_mean_of_resamples": float(np.mean(values)),
        "ci_lower_95": float(np.percentile(values, 2.5)),
        "ci_upper_95": float(np.percentile(values, 97.5)),
    }
    if n_groups is not None:
        result["n_groups"] = n_groups
    return result


def compute_all_bootstrap_intervals(
    raw_rows: list[dict], thresholded_rows: list[dict], class_names: list[str], n_iterations: int, seed: int
) -> dict:
    specs = [
        ("raw_accuracy", raw_rows),
        ("raw_macro_f1", raw_rows),
        ("thresholded_selective_accuracy", thresholded_rows),
        ("thresholded_coverage", thresholded_rows),
    ]
    out = {"group_aware": {}, "image_level": {}}
    for metric_name, rows in specs:
        out["group_aware"][metric_name] = bootstrap_group_aware(rows, class_names, metric_name, n_iterations, seed)
        out["image_level"][metric_name] = bootstrap_image_level(rows, class_names, metric_name, n_iterations, seed)
    out["note"] = (
        "Group-aware intervals resample group_key as the unit (each bootstrap draw keeps "
        "every image in a sampled group together) and are the more meaningful result because "
        "images within a physical-leaf group are correlated. Image-level intervals resample "
        "individual rows independently and are reported alongside for comparison only."
    )
    return out


# ---------------------------------------------------------------------------
# Error analysis (Section 13)
# ---------------------------------------------------------------------------

def error_analysis(raw_rows: list[dict], thresholded_rows: list[dict]) -> dict:
    raw_errors = [r for r in raw_rows if not r["correct"]]
    accepted_errors = [r for r in thresholded_rows if r["accepted"] and not r["correct"]]
    rejected_errors = [r for r in thresholded_rows if not r["accepted"] and not r["correct"]]
    rejected_correct = [r for r in thresholded_rows if not r["accepted"] and r["correct"]]

    confusion_pairs: dict[str, int] = {}
    for r in raw_errors:
        key = f"{r['true_class_name']} -> {r['predicted_class_name']}"
        confusion_pairs[key] = confusion_pairs.get(key, 0) + 1
    confusion_pairs_sorted = sorted(confusion_pairs.items(), key=lambda kv: (-kv[1], kv[0]))

    lowest_confidence_correct = sorted(
        (r for r in raw_rows if r["correct"]), key=lambda r: r["maximum_probability"]
    )[:10]
    highest_confidence_incorrect = sorted(raw_errors, key=lambda r: -r["maximum_probability"])[:10]

    per_class_errors: dict[str, int] = {}
    for r in raw_errors:
        per_class_errors[r["true_class_name"]] = per_class_errors.get(r["true_class_name"], 0) + 1

    error_groups: dict[str, int] = {}
    for r in raw_errors:
        error_groups[r["group_key"]] = error_groups.get(r["group_key"], 0) + 1
    groups_with_multiple_errors = {g: c for g, c in error_groups.items() if c > 1}

    guard_groups_seen: dict[str, set[bool]] = {}
    for r in thresholded_rows:
        guard = r.get("similarity_guard_group") or ""
        if not guard:
            continue
        guard_groups_seen.setdefault(guard, set()).add(r["correct"])
    inconsistent_guard_groups = [g for g, outcomes in guard_groups_seen.items() if len(outcomes) > 1]

    def _slim(r: dict) -> dict:
        return {
            "path": r["path"],
            "true_class_name": r["true_class_name"],
            "predicted_class_name": r["predicted_class_name"],
            "maximum_probability": r["maximum_probability"],
            "group_key": r["group_key"],
        }

    return {
        "raw_error_count": len(raw_errors),
        "accepted_error_count": len(accepted_errors),
        "errors_correctly_rejected_as_uncertain": len(rejected_errors),
        "correct_predictions_incorrectly_rejected": len(rejected_correct),
        "confusion_pairs": [{"pair": k, "count": v} for k, v in confusion_pairs_sorted],
        "lowest_confidence_correct_predictions": [_slim(r) for r in lowest_confidence_correct],
        "highest_confidence_incorrect_predictions": [_slim(r) for r in highest_confidence_incorrect],
        "per_class_error_counts": per_class_errors,
        "leaf_groups_with_multiple_errors": groups_with_multiple_errors,
        "similarity_guard_groups_with_inconsistent_correctness": inconsistent_guard_groups,
        "note": (
            "Confusion pairs, confidence rankings, and group concentration are reported "
            "descriptively from the observed images/predictions only; no biological or "
            "clinical interpretation beyond what is directly visible in these numbers is made."
        ),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _write_json(path: Path, data) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True, default=str)


def _cmd_select(args: argparse.Namespace) -> dict:
    with open(args.validation_integrity_json) as f:
        integrity = json.load(f)
    expected_class_to_index = _load_expected_class_to_index(args.class_map, args.model_scope)
    verify_validation_integrity(
        integrity,
        args.validation_predictions_csv,
        args.checkpoint_sha256,
        args.validation_manifest_sha256,
        expected_class_to_index,
    )

    rows = load_predictions_csv(args.validation_predictions_csv)
    class_names = _class_names_from_rows(rows)
    result = select_threshold(rows, class_names, CANDIDATE_GRID)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        args.output_dir / "threshold_candidates.json",
        {"candidate_count": result["candidate_count"], "candidates": result["candidates"], "grid": CANDIDATE_GRID},
    )
    _write_json(
        args.output_dir / "threshold_selection.json",
        {
            "status": result["status"],
            "selection_rule": SELECTION_RULE_DESCRIPTION,
            "mandatory_constraints": MANDATORY_RULES,
            "selected_threshold": result["selected_threshold"],
            "selected_candidate": result.get("selected_candidate"),
            "pareto_frontier": result.get("pareto_frontier"),
        },
    )

    import time

    policy = build_confidence_policy(
        result, args.checkpoint_sha256, args.validation_manifest_sha256, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    )
    _write_json(args.confidence_policy_output, policy)

    print(json.dumps({"status": result["status"], "selected_threshold": result["selected_threshold"]}, indent=2))
    return result


def _cmd_apply(args: argparse.Namespace) -> dict:
    with open(args.confidence_policy_json) as f:
        policy = json.load(f)
    if policy.get("status") != "approved_for_test_application":
        raise ThresholdSelectionError(
            f"confidence_policy status is {policy.get('status')!r}, not "
            "'approved_for_test_application'; refusing to apply an unapproved/blocked threshold."
        )
    threshold = policy["selected_threshold"]
    if threshold is None:
        raise ThresholdSelectionError("confidence_policy has no selected_threshold")

    with open(args.evaluation_manifest_hashes_json) as f:
        eval_hashes = json.load(f)
    if eval_hashes.get("checkpoint_sha256") != policy.get("checkpoint_sha256"):
        raise ThresholdSelectionError(
            "checkpoint_sha256 mismatch between test evaluation run and frozen confidence_policy"
        )
    if eval_hashes.get("mode") != "final-test":
        raise ThresholdSelectionError("evaluation_manifest_hashes.json is not from a final-test run")

    rows = load_test_predictions_csv(args.test_predictions_csv)
    class_names = _class_names_from_rows(rows)

    thresholded = apply_threshold_to_test(rows, threshold, class_names)
    calibration = reliability_analysis(rows, num_bins=args.calibration_bins)
    bootstrap = compute_all_bootstrap_intervals(rows, rows, class_names, args.bootstrap_iterations, args.bootstrap_seed)
    errors = error_analysis(rows, rows)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        args.output_dir / "test_metrics_thresholded.json",
        {"threshold": threshold, **{k: v for k, v in thresholded.items() if k != "per_class"}, "per_class": thresholded["per_class"]},
    )
    _write_json(args.output_dir / "confidence_analysis.json", calibration)

    potato_disclosure = (
        "Potato Healthy test set contains 24 images from only 6 independent leaf groups. "
        "Its per-class test metrics have high uncertainty; a perfect score would not prove "
        "production-level generalization, and macro-F1 remains sensitive to this small class."
    )

    summary = {
        "m5_status": "m5_complete",
        "frozen_threshold": threshold,
        "confidence_policy_status": policy.get("status"),
        "checkpoint_sha256": eval_hashes.get("checkpoint_sha256"),
        "test_manifest_sha256": eval_hashes.get("manifest_sha256"),
        "num_test_samples": len(rows),
        "threshold_applied_after_test_evaluation": True,
        "threshold_changed_after_seeing_test_results": False,
        "thresholded_test_metrics": thresholded,
        "confidence_analysis": calibration,
        "bootstrap_confidence_intervals": bootstrap,
        "error_analysis": errors,
        "potato_healthy_disclosure": potato_disclosure,
        "m6_started": False,
        "production_readiness_claim": "none",
    }
    _write_json(args.output_dir / "m5_summary.json", summary)

    print(
        json.dumps(
            {
                "threshold": threshold,
                "coverage": thresholded["coverage"],
                "selective_accuracy": thresholded["selective_accuracy"],
            },
            indent=2,
        )
    )
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M5 confidence-threshold selection (validation-only) and test-side application")
    sub = p.add_subparsers(dest="command", required=True)

    sel = sub.add_parser("select", help="Select a threshold from validation predictions only")
    sel.add_argument("--validation-predictions-csv", required=True, type=Path)
    sel.add_argument(
        "--validation-integrity-json", required=True, type=Path,
        help="validation_evaluation_integrity.json produced by `evaluate.py --mode validation`. "
             "Cryptographically ties --validation-predictions-csv to the approved frozen "
             "validation manifest and checkpoint; required, not optional.",
    )
    sel.add_argument("--class-map", required=True, type=Path)
    sel.add_argument("--model-scope", required=True, type=Path)
    sel.add_argument("--checkpoint-sha256", required=True, type=str)
    sel.add_argument("--validation-manifest-sha256", required=True, type=str)
    sel.add_argument("--output-dir", required=True, type=Path)
    sel.add_argument("--confidence-policy-output", required=True, type=Path)
    sel.set_defaults(func=_cmd_select)

    app = sub.add_parser("apply", help="Apply the frozen threshold to test predictions and analyze")
    app.add_argument("--test-predictions-csv", required=True, type=Path)
    app.add_argument("--confidence-policy-json", required=True, type=Path)
    app.add_argument("--evaluation-manifest-hashes-json", required=True, type=Path)
    app.add_argument("--output-dir", required=True, type=Path)
    app.add_argument("--bootstrap-iterations", type=int, default=2000)
    app.add_argument("--bootstrap-seed", type=int, default=42)
    app.add_argument("--calibration-bins", type=int, default=10)
    app.set_defaults(func=_cmd_apply)

    return p


def main(argv=None):
    args = build_arg_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    main()
