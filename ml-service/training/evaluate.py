"""M5 evaluation utility -- explicit validation and final-test modes.

Two modes only, chosen with --mode:

- "validation": may evaluate val.csv. Used for repeated, iterative
  reporting (and, via select_threshold.py, for threshold selection). Writes
  a companion validation_evaluation_integrity.json cryptographically tying
  its predictions CSV to the exact manifest and checkpoint that produced it,
  so select_threshold.py can verify -- not just trust -- its input.
- "final-test": may evaluate test.csv. This is a ONE-TIME frozen
  evaluation set. It refuses to run without an explicit
  --confirm-final-test-evaluation flag, and refuses to run without an
  already-frozen, approved --confidence-policy-json (the threshold is
  derived from that policy, not accepted as a free-form value). It also
  refuses to overwrite a prior final-test run's outputs unless
  --allow-repeat-final-test-evaluation is explicitly passed, in which case
  it writes to a new timestamped subdirectory instead of overwriting the
  original.

There is no generic mode that accepts an arbitrary manifest: each mode
requires the manifest passed via --manifest to be literally named
val.csv/test.csv respectively, and its SHA-256 must match the caller's
--expected-manifest-sha256. This program never selects, tunes, or
searches over a threshold using test labels -- for final-test mode it only
*applies* an already-frozen, policy-verified threshold value to compute a
derived "accepted" column.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import platform
import sys
import time
from pathlib import Path

import torch
from sklearn.metrics import confusion_matrix
from torch.utils.data import DataLoader

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dataset import ManifestImageDataset, load_active_classes, load_class_index_by_name
from model import ARCHITECTURE_NAME, build_model, select_device
from train import (
    IMAGENET_MEAN,
    IMAGENET_STD,
    IMAGE_SIZE,
    POTATO_HEALTHY_DISCLOSURE,
    _git_commit,
    _sha256_file,
    _write_json,
    build_transforms,
    compute_metrics,
    compute_per_class_metrics,
)

EXPECTED_MANIFEST_BASENAME = {"validation": "val.csv", "final-test": "test.csv"}
SUPPORTED_CONFIDENCE_METHODS = {"maximum_softmax_probability"}
FINAL_TEST_OUTPUT_MARKERS = [
    "test_predictions.csv",
    "test_metrics_raw.json",
    "test_metrics_thresholded.json",
    "test_confusion_matrix.json",
    "test_per_class_metrics.json",
]


class EvaluationRefused(Exception):
    pass


def load_checkpoint_and_model(checkpoint_path: Path, device: torch.device):
    ckpt = torch.load(checkpoint_path, map_location=device, weights_only=False)
    if ckpt.get("architecture") != ARCHITECTURE_NAME:
        raise EvaluationRefused(
            f"checkpoint architecture {ckpt.get('architecture')!r} != expected {ARCHITECTURE_NAME!r}"
        )
    class_names = ckpt["class_names"]
    if len(class_names) != 6:
        raise EvaluationRefused(f"checkpoint has {len(class_names)} classes, expected 6")

    model = build_model(num_classes=len(class_names), pretrained=False)
    model.load_state_dict(ckpt["model_state_dict"])  # state_dict only, never a pickled full model
    model.to(device)
    model.eval()
    return model, ckpt


def verify_class_map(ckpt: dict, class_map_path: Path, model_scope_path: Path) -> None:
    class_index_by_name = load_class_index_by_name(class_map_path)
    active_classes = load_active_classes(model_scope_path)
    expected_class_to_index = {name: class_index_by_name[name] for name in active_classes}
    if ckpt.get("class_to_index") != expected_class_to_index:
        raise EvaluationRefused(
            f"checkpoint class_to_index {ckpt.get('class_to_index')} does not match "
            f"current approved policy {expected_class_to_index}"
        )


def _load_manifest_metadata(manifest_path: Path) -> dict[str, dict]:
    with open(manifest_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {
            row["path"]: {
                "group_key": row["group_key"],
                "similarity_guard_group": row["similarity_guard_group"],
            }
            for row in reader
        }


def _run_inference(model, dataset, device, batch_size, num_workers, class_names):
    """Single forward pass over `dataset` (built with return_path=True).

    Returns (records, avg_loss). Loss uses an unweighted CrossEntropyLoss --
    this intentionally differs from training's inverse-frequency-weighted
    loss (see docs/MODEL_TRAINING.md's disclosed weighted-vs-unweighted-loss
    note); classification metrics (accuracy/precision/recall/F1), which are
    unaffected by that distinction, are the metrics compared against M4.
    """
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers=num_workers)
    criterion = torch.nn.CrossEntropyLoss()
    records = []
    total_loss = 0.0
    n = 0
    model.eval()
    with torch.no_grad():
        for images, labels, rel_paths in loader:
            images = images.to(device)
            labels_t = labels.to(device)
            outputs = model(images)
            loss = criterion(outputs, labels_t)
            batch_n = labels_t.size(0)
            total_loss += loss.item() * batch_n
            n += batch_n
            probs = torch.softmax(outputs, dim=1).detach().cpu()
            preds = probs.argmax(dim=1)
            for i in range(len(rel_paths)):
                true_idx = int(labels[i])
                pred_idx = int(preds[i].item())
                prob_vec = [float(x) for x in probs[i].tolist()]
                records.append(
                    {
                        "path": rel_paths[i],
                        "true_class_index": true_idx,
                        "true_class_name": class_names[true_idx],
                        "predicted_class_index": pred_idx,
                        "predicted_class_name": class_names[pred_idx],
                        "maximum_probability": prob_vec[pred_idx],
                        "probabilities": prob_vec,
                        "correct": true_idx == pred_idx,
                    }
                )
    avg_loss = total_loss / n if n else float("nan")
    return records, avg_loss


# ---------------------------------------------------------------------------
# Validation-evaluation integrity metadata (closes the gap where
# select_threshold.py could otherwise be pointed at any schema-compatible
# CSV, including test-derived predictions, without proof of provenance).
# ---------------------------------------------------------------------------

def _preprocessing_config_sha256(preprocessing_config: dict) -> str:
    return hashlib.sha256(json.dumps(preprocessing_config, sort_keys=True).encode("utf-8")).hexdigest()


def build_validation_integrity_metadata(
    manifest_path: Path,
    manifest_sha256: str,
    checkpoint_path: Path,
    checkpoint_sha256: str,
    predictions_csv_path: Path,
    class_names: list[str],
    class_to_index: dict[str, int],
    preprocessing_config: dict,
) -> dict:
    """Cryptographically ties a validation_predictions.csv to the exact
    manifest, checkpoint, and class mapping that produced it. Reads the
    predictions CSV only to hash it and count its rows -- never re-runs
    inference, so this can be (and was) built from an already-existing
    predictions file without recomputing any model predictions."""
    predictions_csv_sha256 = _sha256_file(predictions_csv_path)
    with open(predictions_csv_path, newline="", encoding="utf-8") as f:
        row_count = sum(1 for _ in csv.DictReader(f))
    return {
        "evaluation_mode": "validation",
        "test_output": False,
        "checkpoint": str(checkpoint_path),
        "checkpoint_sha256": checkpoint_sha256,
        "manifest_path": str(manifest_path),
        "manifest_sha256": manifest_sha256,
        "predictions_csv_path": str(predictions_csv_path),
        "predictions_csv_sha256": predictions_csv_sha256,
        "row_count": row_count,
        "class_names": class_names,
        "class_to_index": class_to_index,
        "preprocessing_config_sha256": _preprocessing_config_sha256(preprocessing_config),
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


# ---------------------------------------------------------------------------
# Frozen confidence-policy verification (closes the gap where final-test
# mode could otherwise run with any free-form --apply-threshold value,
# without proof that it came from an approved validation-only selection).
# ---------------------------------------------------------------------------

def _load_confidence_policy(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def verify_confidence_policy_for_final_test(policy: dict, expected_validation_manifest_sha256: str) -> float:
    """Verifies the frozen policy is trustworthy for final-test application
    and returns the threshold to apply. Never mutates or re-derives the
    threshold -- only validates it and hands it back unchanged."""
    if policy.get("status") != "approved_for_test_application":
        raise EvaluationRefused(
            f"confidence policy status is {policy.get('status')!r}, not "
            "'approved_for_test_application'. Refusing final-test evaluation without an "
            "approved, frozen threshold policy."
        )
    if policy.get("selection_dataset") != "validation":
        raise EvaluationRefused(
            f"confidence policy selection_dataset is {policy.get('selection_dataset')!r}, expected "
            "'validation'."
        )
    if policy.get("model_architecture") != ARCHITECTURE_NAME:
        raise EvaluationRefused(
            f"confidence policy model_architecture {policy.get('model_architecture')!r} != expected "
            f"{ARCHITECTURE_NAME!r}."
        )
    if policy.get("confidence_method") not in SUPPORTED_CONFIDENCE_METHODS:
        raise EvaluationRefused(
            f"confidence policy confidence_method {policy.get('confidence_method')!r} is not a "
            f"supported method ({sorted(SUPPORTED_CONFIDENCE_METHODS)})."
        )
    threshold = policy.get("selected_threshold")
    if threshold is None or isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise EvaluationRefused(f"confidence policy selected_threshold {threshold!r} is not numeric.")
    if policy.get("test_labels_used_for_threshold_selection") is not False:
        raise EvaluationRefused(
            "confidence policy does not explicitly state "
            "test_labels_used_for_threshold_selection: false. Refusing to trust this policy."
        )
    if policy.get("validation_manifest_sha256") != expected_validation_manifest_sha256:
        raise EvaluationRefused(
            f"confidence policy validation_manifest_sha256 {policy.get('validation_manifest_sha256')} "
            f"does not match --expected-validation-manifest-sha256 {expected_validation_manifest_sha256}."
        )
    return float(threshold)


def _final_test_outputs_exist(output_dir: Path) -> list[Path]:
    return [output_dir / name for name in FINAL_TEST_OUTPUT_MARKERS if (output_dir / name).exists()]


def evaluate(
    checkpoint_path: Path,
    manifest_path: Path,
    class_map_path: Path,
    model_scope_path: Path,
    device_arg: str,
    batch_size: int,
    num_workers: int,
    mode: str,
    expected_manifest_sha256: str,
    expected_checkpoint_sha256: str,
    confirm_final_test_evaluation: bool = False,
    apply_threshold: float | None = None,
    confidence_policy_path: Path | None = None,
    expected_validation_manifest_sha256: str | None = None,
    ml_service_root: Path | None = None,
):
    log = logging.getLogger("evaluate")

    if mode not in EXPECTED_MANIFEST_BASENAME:
        raise EvaluationRefused(f"unknown mode {mode!r}; evaluate.py only supports 'validation' or 'final-test'")

    expected_name = EXPECTED_MANIFEST_BASENAME[mode]
    if manifest_path.name != expected_name:
        raise EvaluationRefused(
            f"--mode {mode} requires a manifest literally named {expected_name!r}, got "
            f"{manifest_path.name!r}. evaluate.py refuses to evaluate an arbitrary manifest "
            "under any mode."
        )

    policy: dict | None = None
    frozen_threshold: float | None = None

    if mode == "final-test":
        if not confirm_final_test_evaluation:
            raise EvaluationRefused(
                "--mode final-test requires --confirm-final-test-evaluation. test.csv is a "
                "one-time frozen evaluation set and is refused without explicit acknowledgement."
            )
        if confidence_policy_path is None:
            raise EvaluationRefused(
                "--mode final-test requires --confidence-policy-json pointing at the frozen, "
                "approved confidence_policy_v1.json. This program never accepts a free-form "
                "threshold for the frozen test set -- the threshold must already be selected "
                "and frozen via select_threshold.py before test.csv is evaluated."
            )
        if expected_validation_manifest_sha256 is None:
            raise EvaluationRefused(
                "--mode final-test requires --expected-validation-manifest-sha256, used to verify "
                "the confidence policy was selected from the approved frozen validation manifest."
            )
        # Load and verify the policy before opening test.csv.
        policy = _load_confidence_policy(confidence_policy_path)
        frozen_threshold = verify_confidence_policy_for_final_test(policy, expected_validation_manifest_sha256)
        if apply_threshold is not None and abs(apply_threshold - frozen_threshold) > 1e-9:
            raise EvaluationRefused(
                f"--apply-threshold {apply_threshold} does not match the frozen confidence-policy "
                f"threshold {frozen_threshold}. Refusing to evaluate test.csv with a threshold that "
                "was not validation-selected."
            )
        log.warning(
            "FINAL-TEST MODE: evaluating the frozen test manifest %s using the approved, frozen "
            "confidence-policy threshold %.4f. This is intended as a ONE-TIME evaluation. These "
            "results must not be used to change the model, checkpoint, or confidence threshold.",
            manifest_path, frozen_threshold,
        )

    actual_manifest_sha256 = _sha256_file(manifest_path)
    if actual_manifest_sha256 != expected_manifest_sha256:
        raise EvaluationRefused(
            f"{manifest_path} SHA-256 {actual_manifest_sha256} does not match "
            f"--expected-manifest-sha256 {expected_manifest_sha256}. Refusing to evaluate a "
            "manifest that does not match the caller's declared frozen value."
        )

    actual_checkpoint_sha256 = _sha256_file(checkpoint_path)
    if actual_checkpoint_sha256 != expected_checkpoint_sha256:
        raise EvaluationRefused(
            f"{checkpoint_path} SHA-256 {actual_checkpoint_sha256} does not match "
            f"--expected-checkpoint-sha256 {expected_checkpoint_sha256}."
        )
    if mode == "final-test" and actual_checkpoint_sha256 != policy.get("checkpoint_sha256"):
        raise EvaluationRefused(
            f"checkpoint SHA-256 {actual_checkpoint_sha256} does not match the frozen confidence "
            f"policy's checkpoint_sha256 {policy.get('checkpoint_sha256')}. Refusing to apply a "
            "threshold selected for a different checkpoint."
        )

    device = select_device(device_arg)
    model, ckpt = load_checkpoint_and_model(checkpoint_path, device)
    verify_class_map(ckpt, class_map_path, model_scope_path)

    class_names = ckpt["class_names"]
    _, val_transform, transform_config = build_transforms()

    # Deterministic transform sanity check against the checkpoint's recorded config.
    recorded = ckpt.get("preprocessing_config", {})
    if recorded and (
        recorded.get("image_size") != IMAGE_SIZE
        or recorded.get("normalization", {}).get("mean") != IMAGENET_MEAN
        or recorded.get("normalization", {}).get("std") != IMAGENET_STD
    ):
        raise EvaluationRefused("checkpoint preprocessing_config does not match this evaluator's transforms")

    allow_test = mode == "final-test"
    dataset = ManifestImageDataset(
        manifest_path, class_map_path, model_scope_path, transform=val_transform,
        return_path=True, allow_test=allow_test, ml_service_root=ml_service_root,
    )
    manifest_metadata = _load_manifest_metadata(manifest_path)

    records, avg_loss = _run_inference(model, dataset, device, batch_size, num_workers, class_names)

    effective_threshold = frozen_threshold if mode == "final-test" else apply_threshold

    seen_paths = set()
    for r in records:
        if r["path"] in seen_paths:
            raise EvaluationRefused(f"prediction row reconciliation failure: duplicate path {r['path']!r}")
        seen_paths.add(r["path"])
        meta = manifest_metadata.get(r["path"])
        if meta is None:
            raise EvaluationRefused(
                f"prediction row reconciliation failure: path {r['path']!r} not found in manifest"
            )
        r["group_key"] = meta["group_key"]
        r["similarity_guard_group"] = meta["similarity_guard_group"]
        if effective_threshold is not None:
            r["accepted"] = r["maximum_probability"] >= effective_threshold

    if len(records) != len(manifest_metadata):
        raise EvaluationRefused(
            f"prediction row reconciliation failure: {len(records)} predictions but "
            f"{len(manifest_metadata)} manifest rows"
        )

    y_true = [r["true_class_index"] for r in records]
    y_pred = [r["predicted_class_index"] for r in records]
    metrics = compute_metrics(y_true, y_pred, class_names)
    metrics["loss"] = avg_loss
    per_class = compute_per_class_metrics(y_true, y_pred, class_names)
    cm = confusion_matrix(y_true, y_pred, labels=list(range(len(class_names))))

    return {
        "mode": mode,
        "manifest": str(manifest_path),
        "manifest_sha256": actual_manifest_sha256,
        "checkpoint": str(checkpoint_path),
        "checkpoint_sha256": actual_checkpoint_sha256,
        "checkpoint_epoch": ckpt.get("epoch"),
        "device": str(device),
        "num_samples": len(dataset),
        "class_names": class_names,
        "class_to_index": ckpt.get("class_to_index"),
        "preprocessing_config": transform_config,
        "metrics": metrics,
        "per_class_metrics": per_class,
        "confusion_matrix": {"class_order": class_names, "matrix": cm.tolist()},
        "potato_healthy_disclosure": POTATO_HEALTHY_DISCLOSURE,
        "test_set_used": mode == "final-test",
        "predictions": records,
        "applied_threshold": effective_threshold,
    }


def _write_predictions_csv(path: Path, records: list[dict], apply_threshold: float | None) -> None:
    fieldnames = [
        "path", "true_class_name", "true_class_index",
        "predicted_class_name", "predicted_class_index",
        "maximum_probability",
    ]
    if apply_threshold is not None:
        fieldnames.append("accepted")
    fieldnames += ["probabilities", "correct", "group_key", "similarity_guard_group"]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            row = {
                "path": r["path"],
                "true_class_name": r["true_class_name"],
                "true_class_index": r["true_class_index"],
                "predicted_class_name": r["predicted_class_name"],
                "predicted_class_index": r["predicted_class_index"],
                "maximum_probability": r["maximum_probability"],
                "probabilities": json.dumps(r["probabilities"]),
                "correct": r["correct"],
                "group_key": r.get("group_key", ""),
                "similarity_guard_group": r.get("similarity_guard_group", ""),
            }
            if apply_threshold is not None:
                row["accepted"] = r["accepted"]
            writer.writerow(row)


def _environment_snapshot(result: dict) -> dict:
    return {
        "python_version": platform.python_version(),
        "os": platform.platform(),
        "machine_architecture": platform.machine(),
        "torch_version": torch.__version__,
        "torchvision_version": __import__("torchvision").__version__,
        "pillow_version": __import__("PIL").__version__,
        "scikit_learn_version": __import__("sklearn").__version__,
        "device": result["device"],
        "mode": result["mode"],
        "checkpoint": result["checkpoint"],
        "checkpoint_sha256": result["checkpoint_sha256"],
        "checkpoint_epoch": result["checkpoint_epoch"],
        "manifest": result["manifest"],
        "manifest_sha256": result["manifest_sha256"],
        "applied_threshold": result["applied_threshold"],
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agriai_repo_commit": _git_commit(),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="M5 evaluation: explicit --mode validation (val.csv) or final-test (test.csv, one-time)"
    )
    p.add_argument("--mode", required=True, choices=["validation", "final-test"])
    p.add_argument("--checkpoint", required=True, type=Path)
    p.add_argument(
        "--manifest", required=True, type=Path,
        help="Must be named val.csv (--mode validation) or test.csv (--mode final-test)",
    )
    p.add_argument("--class-map", required=True, type=Path)
    p.add_argument("--model-scope", required=True, type=Path)
    p.add_argument(
        "--expected-manifest-sha256", required=True, type=str,
        help="Manifest SHA-256 must match this value or evaluation is refused",
    )
    p.add_argument(
        "--expected-checkpoint-sha256", required=True, type=str,
        help="Checkpoint SHA-256 must match this value or evaluation is refused",
    )
    p.add_argument("--output-dir", required=True, type=Path)
    p.add_argument(
        "--ml-service-root", type=Path, default=None,
        help="Override the root manifest paths resolve against (default: ml-service/). "
             "Exists for test isolation; production runs should omit it.",
    )
    p.add_argument("--device", type=str, default="auto")
    p.add_argument("--batch-size", type=int, default=16)
    p.add_argument("--num-workers", type=int, default=0)
    p.add_argument(
        "--confirm-final-test-evaluation", action="store_true", default=False,
        help="Required for --mode final-test. Refused without it. No other flag bypasses this.",
    )
    p.add_argument(
        "--confidence-policy-json", type=Path, default=None,
        help="Required for --mode final-test: path to the frozen, approved "
             "confidence_policy_v1.json. The applied threshold is derived from this file's "
             "selected_threshold, not from a free-form CLI value.",
    )
    p.add_argument(
        "--expected-validation-manifest-sha256", type=str, default=None,
        help="Required for --mode final-test: the approved frozen val.csv SHA-256, used to "
             "verify the confidence policy was selected from the approved validation manifest.",
    )
    p.add_argument(
        "--apply-threshold", type=float, default=None,
        help="Optional. For --mode final-test this is only accepted as a cross-check: if given, "
             "it must equal the frozen confidence-policy threshold exactly or evaluation is "
             "refused. Never used to select, tune, or override the frozen threshold.",
    )
    p.add_argument(
        "--allow-repeat-final-test-evaluation", action="store_true", default=False,
        help="Discouraged. Allows --mode final-test to run again when prior final-test outputs "
             "already exist in --output-dir. Repeated exposure to the frozen test set risks "
             "post-hoc, test-informed threshold or model tuning and undermines frozen-test "
             "discipline. When used, outputs are written to a new timestamped "
             "repeat-<UTC>/ subdirectory rather than overwriting the original frozen run.",
    )
    return p


def main(argv=None):
    args = build_arg_parser().parse_args(argv)

    output_dir = args.output_dir
    if args.mode == "final-test":
        existing = _final_test_outputs_exist(output_dir)
        if existing and not args.allow_repeat_final_test_evaluation:
            raise EvaluationRefused(
                "Refusing to run --mode final-test: prior final-test outputs already exist in "
                f"{output_dir} ({sorted(p.name for p in existing)}). test.csv is a one-time "
                "frozen evaluation set; re-running risks post-hoc, test-informed threshold or "
                "model tuning. Pass --allow-repeat-final-test-evaluation to override "
                "(discouraged; writes to a separate timestamped repeat directory instead of "
                "overwriting the original)."
            )
        if existing and args.allow_repeat_final_test_evaluation:
            output_dir = output_dir / f"repeat-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"

    output_dir.mkdir(parents=True, exist_ok=True)

    log_path = output_dir / "evaluation.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path, mode="a"), logging.StreamHandler(sys.stdout)],
        force=True,
    )
    log = logging.getLogger("evaluate")
    if args.mode == "final-test" and output_dir != args.output_dir:
        log.warning(
            "REPEAT FINAL-TEST EVALUATION explicitly allowed via "
            "--allow-repeat-final-test-evaluation. Writing to repeat directory %s instead of "
            "overwriting the original frozen outputs in %s. This is discouraged and should only "
            "be used for a documented, approved reason.",
            output_dir, args.output_dir,
        )
    log.info("Starting evaluate.py mode=%s manifest=%s checkpoint=%s", args.mode, args.manifest, args.checkpoint)

    result = evaluate(
        checkpoint_path=args.checkpoint,
        manifest_path=args.manifest,
        class_map_path=args.class_map,
        model_scope_path=args.model_scope,
        device_arg=args.device,
        batch_size=args.batch_size,
        num_workers=args.num_workers,
        mode=args.mode,
        expected_manifest_sha256=args.expected_manifest_sha256,
        expected_checkpoint_sha256=args.expected_checkpoint_sha256,
        confirm_final_test_evaluation=args.confirm_final_test_evaluation,
        apply_threshold=args.apply_threshold,
        confidence_policy_path=args.confidence_policy_json,
        expected_validation_manifest_sha256=args.expected_validation_manifest_sha256,
        ml_service_root=args.ml_service_root,
    )

    prefix = "validation" if args.mode == "validation" else "test"
    metrics_filename = "validation_metrics.json" if args.mode == "validation" else "test_metrics_raw.json"

    _write_json(
        output_dir / metrics_filename,
        {
            **result["metrics"],
            "num_samples": result["num_samples"],
            "checkpoint_epoch": result["checkpoint_epoch"],
            "mode": result["mode"],
            "test_set_used": result["test_set_used"],
        },
    )
    _write_json(output_dir / f"{prefix}_confusion_matrix.json", result["confusion_matrix"])
    _write_json(
        output_dir / f"{prefix}_per_class_metrics.json",
        {"per_class": result["per_class_metrics"], "potato_healthy_disclosure": POTATO_HEALTHY_DISCLOSURE},
    )
    predictions_csv_path = output_dir / f"{prefix}_predictions.csv"
    _write_predictions_csv(predictions_csv_path, result["predictions"], apply_threshold=result["applied_threshold"])
    _write_json(output_dir / "evaluation_environment.json", _environment_snapshot(result))
    _write_json(
        output_dir / "evaluation_manifest_hashes.json",
        {
            "mode": result["mode"],
            "manifest": result["manifest"],
            "manifest_sha256": result["manifest_sha256"],
            "checkpoint": result["checkpoint"],
            "checkpoint_sha256": result["checkpoint_sha256"],
        },
    )

    if args.mode == "validation":
        integrity = build_validation_integrity_metadata(
            manifest_path=args.manifest,
            manifest_sha256=result["manifest_sha256"],
            checkpoint_path=args.checkpoint,
            checkpoint_sha256=result["checkpoint_sha256"],
            predictions_csv_path=predictions_csv_path,
            class_names=result["class_names"],
            class_to_index=result["class_to_index"],
            preprocessing_config=result["preprocessing_config"],
        )
        _write_json(output_dir / "validation_evaluation_integrity.json", integrity)

    log.info(
        "Evaluation complete: mode=%s num_samples=%d accuracy=%.6f macro_f1=%.6f loss=%.6f",
        result["mode"], result["num_samples"], result["metrics"]["accuracy"],
        result["metrics"]["macro_f1"], result["metrics"]["loss"],
    )
    print(json.dumps({"mode": result["mode"], "metrics": result["metrics"], "num_samples": result["num_samples"]}, indent=2))
    return result


if __name__ == "__main__":
    main()
