"""Tests for training/evaluate.py's M5 mode/confirmation/hash-verification
safety rails, plus an end-to-end run against a tiny synthetic checkpoint."""

from __future__ import annotations

import hashlib
import json

import pytest
import torch
from PIL import Image

from _shared import write_manifest
from evaluate import (
    EvaluationRefused,
    build_arg_parser,
    build_validation_integrity_metadata,
    evaluate,
)
from evaluate import main as evaluate_main
from model import build_model
from train import build_transforms, build_checkpoint


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def _make_compatible_checkpoint(tmp_path, tiny_env):
    """Builds a checkpoint whose class_to_index/preprocessing_config match
    tiny_env's class_map/model_scope and evaluate.py's real build_transforms,
    so it passes verify_class_map() and the preprocessing sanity check."""
    from _shared import name_to_index, ACTIVE_CLASSES

    idx_by_name = name_to_index()
    class_to_index = {name: idx_by_name[name] for name in ACTIVE_CLASSES}
    class_names = [name for name, _ in sorted(class_to_index.items(), key=lambda kv: kv[1])]

    model = build_model(num_classes=6, pretrained=False)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4)
    _, _, transform_config = build_transforms()

    ckpt = build_checkpoint(
        model, optimizer, None, epoch=1, best_val_macro_f1=0.9, val_loss=0.1,
        class_names=class_names, class_to_index=class_to_index,
        transform_config=transform_config, run_config={"seed": 42, "transforms": transform_config},
        manifest_hashes={}, seed=42,
    )
    path = tmp_path / "ckpt.pt"
    torch.save(ckpt, path)
    return path


def _write_policy(tmp_path, checkpoint_sha256, validation_manifest_sha256, filename="confidence_policy_v1.json", **overrides):
    policy = {
        "version": 1,
        "status": "approved_for_test_application",
        "selection_dataset": "validation",
        "model_architecture": "efficientnet_b0",
        "checkpoint_sha256": checkpoint_sha256,
        "validation_manifest_sha256": validation_manifest_sha256,
        "confidence_method": "maximum_softmax_probability",
        "selected_threshold": 0.5,
        "test_labels_used_for_threshold_selection": False,
    }
    policy.update(overrides)
    path = tmp_path / filename
    path.write_text(json.dumps(policy))
    return path


BASE_KWARGS = dict(device_arg="cpu", batch_size=4, num_workers=0)


def test_evaluate_refuses_manifest_name_mismatch(tiny_env, tmp_path):
    manifest_path = tiny_env["root"] / "not_val_or_test.csv"
    write_manifest(manifest_path, tiny_env["rows"])
    fake_checkpoint = tmp_path / "does_not_need_to_exist.pt"
    with pytest.raises(EvaluationRefused, match="literally named"):
        evaluate(
            fake_checkpoint, manifest_path, tiny_env["class_map_path"], tiny_env["model_scope_path"],
            mode="validation", expected_manifest_sha256="deadbeef", expected_checkpoint_sha256="deadbeef",
            **BASE_KWARGS,
        )


def test_evaluate_refuses_final_test_without_confirmation(tiny_env, tmp_path):
    manifest_path = tiny_env["root"] / "test.csv"
    write_manifest(manifest_path, tiny_env["rows"])
    fake_checkpoint = tmp_path / "does_not_need_to_exist.pt"
    with pytest.raises(EvaluationRefused, match="confirm-final-test-evaluation"):
        evaluate(
            fake_checkpoint, manifest_path, tiny_env["class_map_path"], tiny_env["model_scope_path"],
            mode="final-test", expected_manifest_sha256="deadbeef", expected_checkpoint_sha256="deadbeef",
            confirm_final_test_evaluation=False,
            **BASE_KWARGS,
        )


def test_evaluate_refuses_final_test_without_confidence_policy(tiny_env, tmp_path):
    manifest_path = tiny_env["root"] / "test.csv"
    write_manifest(manifest_path, tiny_env["rows"])
    fake_checkpoint = tmp_path / "does_not_need_to_exist.pt"
    with pytest.raises(EvaluationRefused, match="confidence-policy-json"):
        evaluate(
            fake_checkpoint, manifest_path, tiny_env["class_map_path"], tiny_env["model_scope_path"],
            mode="final-test", expected_manifest_sha256="deadbeef", expected_checkpoint_sha256="deadbeef",
            confirm_final_test_evaluation=True, confidence_policy_path=None,
            **BASE_KWARGS,
        )


def test_evaluate_refuses_final_test_without_expected_validation_manifest_hash(tiny_env, tmp_path):
    manifest_path = tiny_env["root"] / "test.csv"
    write_manifest(manifest_path, tiny_env["rows"])
    fake_checkpoint = tmp_path / "does_not_need_to_exist.pt"
    policy_path = _write_policy(tmp_path, "some-checkpoint-hash", "some-manifest-hash")
    with pytest.raises(EvaluationRefused, match="expected-validation-manifest-sha256"):
        evaluate(
            fake_checkpoint, manifest_path, tiny_env["class_map_path"], tiny_env["model_scope_path"],
            mode="final-test", expected_manifest_sha256="deadbeef", expected_checkpoint_sha256="deadbeef",
            confirm_final_test_evaluation=True, confidence_policy_path=policy_path,
            expected_validation_manifest_sha256=None,
            **BASE_KWARGS,
        )


def test_evaluate_refuses_final_test_with_unapproved_policy_status(tiny_env, tmp_path):
    manifest_path = tiny_env["root"] / "test.csv"
    write_manifest(manifest_path, tiny_env["rows"])
    fake_checkpoint = tmp_path / "does_not_need_to_exist.pt"
    policy_path = _write_policy(
        tmp_path, "ckpt-hash", "manifest-hash", status="blocked_threshold_selection", selected_threshold=None,
    )
    with pytest.raises(EvaluationRefused, match="not 'approved_for_test_application'"):
        evaluate(
            fake_checkpoint, manifest_path, tiny_env["class_map_path"], tiny_env["model_scope_path"],
            mode="final-test", expected_manifest_sha256="deadbeef", expected_checkpoint_sha256="deadbeef",
            confirm_final_test_evaluation=True, confidence_policy_path=policy_path,
            expected_validation_manifest_sha256="manifest-hash",
            **BASE_KWARGS,
        )


def test_evaluate_refuses_final_test_with_wrong_validation_manifest_hash_in_policy(tiny_env, tmp_path):
    manifest_path = tiny_env["root"] / "test.csv"
    write_manifest(manifest_path, tiny_env["rows"])
    fake_checkpoint = tmp_path / "does_not_need_to_exist.pt"
    policy_path = _write_policy(tmp_path, "ckpt-hash", "manifest-hash-in-policy")
    with pytest.raises(EvaluationRefused, match="does not match --expected-validation-manifest-sha256"):
        evaluate(
            fake_checkpoint, manifest_path, tiny_env["class_map_path"], tiny_env["model_scope_path"],
            mode="final-test", expected_manifest_sha256="deadbeef", expected_checkpoint_sha256="deadbeef",
            confirm_final_test_evaluation=True, confidence_policy_path=policy_path,
            expected_validation_manifest_sha256="a-different-approved-hash",
            **BASE_KWARGS,
        )


def test_evaluate_refuses_final_test_with_non_numeric_threshold_in_policy(tiny_env, tmp_path):
    manifest_path = tiny_env["root"] / "test.csv"
    write_manifest(manifest_path, tiny_env["rows"])
    fake_checkpoint = tmp_path / "does_not_need_to_exist.pt"
    policy_path = _write_policy(tmp_path, "ckpt-hash", "manifest-hash", selected_threshold=None)
    with pytest.raises(EvaluationRefused, match="not numeric"):
        evaluate(
            fake_checkpoint, manifest_path, tiny_env["class_map_path"], tiny_env["model_scope_path"],
            mode="final-test", expected_manifest_sha256="deadbeef", expected_checkpoint_sha256="deadbeef",
            confirm_final_test_evaluation=True, confidence_policy_path=policy_path,
            expected_validation_manifest_sha256="manifest-hash",
            **BASE_KWARGS,
        )


def test_evaluate_refuses_final_test_when_policy_does_not_disclaim_test_label_use(tiny_env, tmp_path):
    manifest_path = tiny_env["root"] / "test.csv"
    write_manifest(manifest_path, tiny_env["rows"])
    fake_checkpoint = tmp_path / "does_not_need_to_exist.pt"
    policy_path = _write_policy(
        tmp_path, "ckpt-hash", "manifest-hash", test_labels_used_for_threshold_selection=True,
    )
    with pytest.raises(EvaluationRefused, match="test_labels_used_for_threshold_selection"):
        evaluate(
            fake_checkpoint, manifest_path, tiny_env["class_map_path"], tiny_env["model_scope_path"],
            mode="final-test", expected_manifest_sha256="deadbeef", expected_checkpoint_sha256="deadbeef",
            confirm_final_test_evaluation=True, confidence_policy_path=policy_path,
            expected_validation_manifest_sha256="manifest-hash",
            **BASE_KWARGS,
        )


def test_evaluate_refuses_final_test_when_checkpoint_does_not_match_policy(tiny_env, tmp_path):
    manifest_path = tiny_env["root"] / "test.csv"
    write_manifest(manifest_path, tiny_env["rows"])
    checkpoint_path = _make_compatible_checkpoint(tmp_path, tiny_env)
    # Policy references a *different* checkpoint hash than the one actually being evaluated.
    policy_path = _write_policy(tmp_path, "a-completely-different-checkpoint-hash", "manifest-hash")
    with pytest.raises(EvaluationRefused, match="does not match the frozen confidence policy's checkpoint_sha256"):
        evaluate(
            checkpoint_path, manifest_path, tiny_env["class_map_path"], tiny_env["model_scope_path"],
            mode="final-test", expected_manifest_sha256=_sha256(manifest_path),
            expected_checkpoint_sha256=_sha256(checkpoint_path),
            confirm_final_test_evaluation=True, confidence_policy_path=policy_path,
            expected_validation_manifest_sha256="manifest-hash",
            ml_service_root=tiny_env["root"],
            **BASE_KWARGS,
        )


def test_evaluate_refuses_final_test_when_apply_threshold_conflicts_with_policy(tiny_env, tmp_path):
    manifest_path = tiny_env["root"] / "test.csv"
    write_manifest(manifest_path, tiny_env["rows"])
    fake_checkpoint = tmp_path / "does_not_need_to_exist.pt"
    policy_path = _write_policy(tmp_path, "ckpt-hash", "manifest-hash", selected_threshold=0.5)
    with pytest.raises(EvaluationRefused, match="does not match the frozen confidence-policy threshold"):
        evaluate(
            fake_checkpoint, manifest_path, tiny_env["class_map_path"], tiny_env["model_scope_path"],
            mode="final-test", expected_manifest_sha256="deadbeef", expected_checkpoint_sha256="deadbeef",
            confirm_final_test_evaluation=True, confidence_policy_path=policy_path,
            expected_validation_manifest_sha256="manifest-hash",
            apply_threshold=0.9,  # deliberately conflicts with the policy's 0.5
            **BASE_KWARGS,
        )


def test_evaluate_refuses_manifest_hash_mismatch(tiny_env, tmp_path):
    manifest_path = tiny_env["root"] / "val.csv"
    write_manifest(manifest_path, tiny_env["rows"])
    fake_checkpoint = tmp_path / "does_not_need_to_exist.pt"
    with pytest.raises(EvaluationRefused, match="does not match"):
        evaluate(
            fake_checkpoint, manifest_path, tiny_env["class_map_path"], tiny_env["model_scope_path"],
            mode="validation", expected_manifest_sha256="wrong-hash", expected_checkpoint_sha256="deadbeef",
            **BASE_KWARGS,
        )


def test_evaluate_refuses_checkpoint_hash_mismatch(tiny_env, tmp_path):
    manifest_path = tiny_env["root"] / "val.csv"
    write_manifest(manifest_path, tiny_env["rows"])
    checkpoint_path = _make_compatible_checkpoint(tmp_path, tiny_env)
    actual_manifest_hash = _sha256(manifest_path)
    with pytest.raises(EvaluationRefused, match="does not match"):
        evaluate(
            checkpoint_path, manifest_path, tiny_env["class_map_path"], tiny_env["model_scope_path"],
            mode="validation", expected_manifest_sha256=actual_manifest_hash,
            expected_checkpoint_sha256="wrong-checkpoint-hash",
            **BASE_KWARGS,
        )


def test_evaluate_validation_mode_end_to_end(tiny_env, tmp_path):
    manifest_path = tiny_env["root"] / "val.csv"
    write_manifest(manifest_path, tiny_env["rows"])
    checkpoint_path = _make_compatible_checkpoint(tmp_path, tiny_env)

    result = evaluate(
        checkpoint_path, manifest_path, tiny_env["class_map_path"], tiny_env["model_scope_path"],
        mode="validation",
        expected_manifest_sha256=_sha256(manifest_path),
        expected_checkpoint_sha256=_sha256(checkpoint_path),
        ml_service_root=tiny_env["root"],
        **BASE_KWARGS,
    )

    assert result["mode"] == "validation"
    assert result["test_set_used"] is False
    assert result["num_samples"] == len(tiny_env["rows"])
    assert len(result["predictions"]) == len(tiny_env["rows"])
    for r in result["predictions"]:
        assert "accepted" not in r
        assert r["group_key"]
        assert abs(sum(r["probabilities"]) - 1.0) < 1e-4
        assert 0.0 <= r["maximum_probability"] <= 1.0


def test_evaluate_final_test_mode_end_to_end_derives_threshold_from_policy(tiny_env, tmp_path):
    manifest_path = tiny_env["root"] / "test.csv"
    write_manifest(manifest_path, tiny_env["rows"])
    checkpoint_path = _make_compatible_checkpoint(tmp_path, tiny_env)
    checkpoint_sha256 = _sha256(checkpoint_path)
    policy_path = _write_policy(tmp_path, checkpoint_sha256, "manifest-hash", selected_threshold=0.3)

    result = evaluate(
        checkpoint_path, manifest_path, tiny_env["class_map_path"], tiny_env["model_scope_path"],
        mode="final-test",
        expected_manifest_sha256=_sha256(manifest_path),
        expected_checkpoint_sha256=checkpoint_sha256,
        confirm_final_test_evaluation=True,
        confidence_policy_path=policy_path,
        expected_validation_manifest_sha256="manifest-hash",
        ml_service_root=tiny_env["root"],
        **BASE_KWARGS,
    )

    assert result["mode"] == "final-test"
    assert result["test_set_used"] is True
    assert result["applied_threshold"] == 0.3
    for r in result["predictions"]:
        assert r["accepted"] == (r["maximum_probability"] >= 0.3)


def test_evaluate_final_test_accepts_matching_apply_threshold_as_cross_check(tiny_env, tmp_path):
    """--apply-threshold may still be passed for final-test, but only as a
    cross-check that must equal the frozen policy threshold exactly."""
    manifest_path = tiny_env["root"] / "test.csv"
    write_manifest(manifest_path, tiny_env["rows"])
    checkpoint_path = _make_compatible_checkpoint(tmp_path, tiny_env)
    checkpoint_sha256 = _sha256(checkpoint_path)
    policy_path = _write_policy(tmp_path, checkpoint_sha256, "manifest-hash", selected_threshold=0.3)

    result = evaluate(
        checkpoint_path, manifest_path, tiny_env["class_map_path"], tiny_env["model_scope_path"],
        mode="final-test",
        expected_manifest_sha256=_sha256(manifest_path),
        expected_checkpoint_sha256=checkpoint_sha256,
        confirm_final_test_evaluation=True,
        confidence_policy_path=policy_path,
        expected_validation_manifest_sha256="manifest-hash",
        apply_threshold=0.3,
        ml_service_root=tiny_env["root"],
        **BASE_KWARGS,
    )
    assert result["applied_threshold"] == 0.3


def test_evaluate_cli_only_exposes_the_declared_final_test_flags():
    """No hidden generic bypass -- the only CLI flags mentioning 'test' are
    the two declared, explicit ones."""
    parser = build_arg_parser()
    option_strings = {a for action in parser._actions for a in action.option_strings}
    test_related = {opt for opt in option_strings if "test" in opt.lower()}
    assert test_related == {"--confirm-final-test-evaluation", "--allow-repeat-final-test-evaluation"}


def test_evaluate_cli_requires_confidence_policy_args():
    parser = build_arg_parser()
    option_strings = {a for action in parser._actions for a in action.option_strings}
    assert "--confidence-policy-json" in option_strings
    assert "--expected-validation-manifest-sha256" in option_strings
    # Not unconditionally required at parse time (validation mode doesn't need them);
    # evaluate() enforces the requirement conditionally for --mode final-test.
    required = {a.dest for a in parser._actions if getattr(a, "required", False)}
    assert "confidence_policy_json" not in required
    assert "expected_validation_manifest_sha256" not in required


# ---------------------------------------------------------------------------
# Validation-evaluation integrity metadata (C1 fix)
# ---------------------------------------------------------------------------

def test_build_validation_integrity_metadata_describes_existing_predictions_csv(tmp_path):
    """The integrity builder must work purely by hashing/describing an
    already-existing predictions CSV -- no model inference involved."""
    predictions_csv = tmp_path / "validation_predictions.csv"
    predictions_csv.write_text("path,true_class_name\nrow1,A\nrow2,B\nrow3,A\n")

    metadata = build_validation_integrity_metadata(
        manifest_path=tmp_path / "val.csv",
        manifest_sha256="manifest-hash-abc",
        checkpoint_path=tmp_path / "ckpt.pt",
        checkpoint_sha256="checkpoint-hash-xyz",
        predictions_csv_path=predictions_csv,
        class_names=["A", "B"],
        class_to_index={"A": 0, "B": 1},
        preprocessing_config={"image_size": 224},
    )

    assert metadata["evaluation_mode"] == "validation"
    assert metadata["test_output"] is False
    assert metadata["row_count"] == 3
    assert metadata["predictions_csv_sha256"] == _sha256(predictions_csv)
    assert metadata["manifest_sha256"] == "manifest-hash-abc"
    assert metadata["checkpoint_sha256"] == "checkpoint-hash-xyz"
    assert metadata["class_names"] == ["A", "B"]
    assert metadata["class_to_index"] == {"A": 0, "B": 1}
    assert "preprocessing_config_sha256" in metadata


def test_main_validation_mode_writes_integrity_metadata_matching_predictions_csv(tiny_env, tmp_path):
    manifest_path = tiny_env["root"] / "val.csv"
    write_manifest(manifest_path, tiny_env["rows"])
    checkpoint_path = _make_compatible_checkpoint(tmp_path, tiny_env)
    output_dir = tmp_path / "run"

    argv = [
        "--mode", "validation",
        "--checkpoint", str(checkpoint_path),
        "--manifest", str(manifest_path),
        "--class-map", str(tiny_env["class_map_path"]),
        "--model-scope", str(tiny_env["model_scope_path"]),
        "--expected-manifest-sha256", _sha256(manifest_path),
        "--expected-checkpoint-sha256", _sha256(checkpoint_path),
        "--output-dir", str(output_dir),
        "--ml-service-root", str(tiny_env["root"]),
        "--device", "cpu", "--batch-size", "4", "--num-workers", "0",
    ]
    evaluate_main(argv)

    integrity_path = output_dir / "validation_evaluation_integrity.json"
    assert integrity_path.exists()
    integrity = json.loads(integrity_path.read_text())
    assert integrity["evaluation_mode"] == "validation"
    assert integrity["test_output"] is False
    assert integrity["predictions_csv_sha256"] == _sha256(output_dir / "validation_predictions.csv")
    assert integrity["row_count"] == len(tiny_env["rows"])


# ---------------------------------------------------------------------------
# Final-test idempotency guard (M1 fix)
# ---------------------------------------------------------------------------

def test_main_refuses_repeat_final_test_when_outputs_exist(tmp_path):
    output_dir = tmp_path / "run"
    output_dir.mkdir()
    (output_dir / "test_predictions.csv").write_text("already here")

    argv = [
        "--mode", "final-test", "--confirm-final-test-evaluation",
        "--checkpoint", str(tmp_path / "does_not_matter.pt"),
        "--manifest", str(tmp_path / "test.csv"),
        "--class-map", str(tmp_path / "class_map.json"),
        "--model-scope", str(tmp_path / "model_scope.json"),
        "--expected-manifest-sha256", "x", "--expected-checkpoint-sha256", "x",
        "--confidence-policy-json", str(tmp_path / "policy.json"),
        "--expected-validation-manifest-sha256", "x",
        "--output-dir", str(output_dir),
    ]
    with pytest.raises(EvaluationRefused, match="prior final-test outputs already exist"):
        evaluate_main(argv)

    # The pre-existing file must be untouched by the refused attempt.
    assert (output_dir / "test_predictions.csv").read_text() == "already here"


def test_main_allows_repeat_final_test_with_override_and_uses_new_subdirectory(tiny_env, tmp_path):
    manifest_path = tiny_env["root"] / "test.csv"
    write_manifest(manifest_path, tiny_env["rows"])
    checkpoint_path = _make_compatible_checkpoint(tmp_path, tiny_env)
    checkpoint_sha256 = _sha256(checkpoint_path)
    policy_path = _write_policy(tmp_path, checkpoint_sha256, "manifest-hash", selected_threshold=0.3)
    output_dir = tmp_path / "run"

    base_argv = [
        "--mode", "final-test", "--confirm-final-test-evaluation",
        "--checkpoint", str(checkpoint_path),
        "--manifest", str(manifest_path),
        "--class-map", str(tiny_env["class_map_path"]),
        "--model-scope", str(tiny_env["model_scope_path"]),
        "--expected-manifest-sha256", _sha256(manifest_path),
        "--expected-checkpoint-sha256", checkpoint_sha256,
        "--confidence-policy-json", str(policy_path),
        "--expected-validation-manifest-sha256", "manifest-hash",
        "--output-dir", str(output_dir),
        "--ml-service-root", str(tiny_env["root"]),
        "--device", "cpu", "--batch-size", "4", "--num-workers", "0",
    ]

    evaluate_main(base_argv)  # first run: creates the original outputs
    original_predictions = (output_dir / "test_predictions.csv").read_text()

    # Second run without override must still refuse.
    with pytest.raises(EvaluationRefused, match="prior final-test outputs already exist"):
        evaluate_main(base_argv)

    # Second run with the explicit override must succeed, writing to a
    # separate repeat-<UTC>/ subdirectory rather than overwriting the original.
    evaluate_main(base_argv + ["--allow-repeat-final-test-evaluation"])

    repeat_dirs = [p for p in output_dir.iterdir() if p.is_dir() and p.name.startswith("repeat-")]
    assert len(repeat_dirs) == 1
    assert (repeat_dirs[0] / "test_predictions.csv").exists()

    # The original outputs must remain exactly as they were.
    assert (output_dir / "test_predictions.csv").read_text() == original_predictions


def test_evaluate_cli_requires_hash_arguments():
    parser = build_arg_parser()
    option_strings = {a for action in parser._actions for a in action.option_strings}
    assert "--expected-manifest-sha256" in option_strings
    assert "--expected-checkpoint-sha256" in option_strings
    required = {a.dest for a in parser._actions if getattr(a, "required", False)}
    assert "expected_manifest_sha256" in required
    assert "expected_checkpoint_sha256" in required
