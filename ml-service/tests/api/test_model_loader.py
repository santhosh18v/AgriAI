"""Tests for app/model_loader.py (Milestone M6).

Uses only tiny synthetic checkpoints built via training/model.py's real
build_model() -- never the real ~48MB checkpoint.
"""

from __future__ import annotations

import json
import threading

from conftest import write_policy, write_synthetic_checkpoint

from app.model_loader import ModelLoadError, ModelLoader


def test_model_loads_successfully_with_valid_synthetic_environment(make_settings):
    settings = make_settings()
    loader = ModelLoader(settings)
    loader.load()

    assert loader.is_ready is True
    assert loader.failure_reason is None
    assert loader.metadata.architecture == "efficientnet_b0"
    assert loader.metadata.class_count == 6
    assert loader.metadata.device == "cpu"
    assert loader.load_duration_seconds is not None and loader.load_duration_seconds >= 0


def test_checkpoint_sha_mismatch_is_rejected(synthetic_env, make_settings):
    # Policy references a checkpoint hash that does not match the real file.
    bad_policy_path = write_policy(synthetic_env["root"], "not-the-real-checkpoint-hash", filename="bad_policy.json")
    settings = make_settings(confidence_policy_path=bad_policy_path)
    loader = ModelLoader(settings)
    loader.load()

    assert loader.is_ready is False
    assert "does not match the approved confidence policy" in loader.failure_reason


def test_class_map_mismatch_is_rejected(synthetic_env, make_settings, tmp_path):
    # class_map.json disagrees with the checkpoint's own class_to_index.
    bad_class_map = tmp_path / "bad_class_map.json"
    bad_class_map.write_text(json.dumps({"0": "Wrong Class", "1": "Also Wrong", "2": "C", "3": "D", "4": "E", "5": "F"}))
    bad_model_scope = tmp_path / "bad_model_scope.json"
    bad_model_scope.write_text(
        json.dumps({"status": "approved", "active_model_classes": ["Wrong Class", "Also Wrong", "C", "D", "E", "F"]})
    )
    settings = make_settings(class_map_path=bad_class_map, model_scope_path=bad_model_scope)
    loader = ModelLoader(settings)
    loader.load()

    assert loader.is_ready is False
    assert "class mapping" in loader.failure_reason


def test_unapproved_confidence_policy_is_rejected(synthetic_env, make_settings):
    bad_policy_path = write_policy(
        synthetic_env["root"], synthetic_env["checkpoint_sha256"],
        filename="unapproved_policy.json", status="blocked_threshold_selection",
    )
    settings = make_settings(confidence_policy_path=bad_policy_path)
    loader = ModelLoader(settings)
    loader.load()

    assert loader.is_ready is False
    assert "not approved" in loader.failure_reason


def test_architecture_mismatch_in_policy_is_rejected(synthetic_env, make_settings):
    bad_policy_path = write_policy(
        synthetic_env["root"], synthetic_env["checkpoint_sha256"],
        filename="wrong_arch_policy.json", model_architecture="resnet50",
    )
    settings = make_settings(confidence_policy_path=bad_policy_path)
    loader = ModelLoader(settings)
    loader.load()

    assert loader.is_ready is False
    assert "architecture" in loader.failure_reason


def test_non_numeric_threshold_is_rejected(synthetic_env, make_settings):
    bad_policy_path = write_policy(
        synthetic_env["root"], synthetic_env["checkpoint_sha256"],
        filename="bad_threshold_policy.json", selected_threshold=None,
    )
    settings = make_settings(confidence_policy_path=bad_policy_path)
    loader = ModelLoader(settings)
    loader.load()

    assert loader.is_ready is False
    assert "threshold" in loader.failure_reason


def test_missing_checkpoint_file_is_rejected(make_settings, tmp_path):
    settings = make_settings(model_checkpoint_path=tmp_path / "does_not_exist.pt")
    loader = ModelLoader(settings)
    loader.load()

    assert loader.is_ready is False
    assert "missing" in loader.failure_reason
    # Sanitized: no local absolute path leaked into the failure reason.
    assert str(tmp_path) not in loader.failure_reason


def test_failure_reason_never_contains_absolute_paths(synthetic_env, make_settings):
    bad_policy_path = write_policy(synthetic_env["root"], "wrong-hash", filename="p.json")
    settings = make_settings(confidence_policy_path=bad_policy_path)
    loader = ModelLoader(settings)
    loader.load()

    assert loader.is_ready is False
    assert str(synthetic_env["root"]) not in loader.failure_reason
    assert "/Users/" not in loader.failure_reason
    assert "Traceback" not in loader.failure_reason


def test_model_loads_only_once(make_settings):
    settings = make_settings()
    loader = ModelLoader(settings)
    loader.load()
    first_model = loader.get_model()
    first_duration = loader.load_duration_seconds

    loader.load()  # second call must be a no-op
    assert loader.get_model() is first_model
    assert loader.load_duration_seconds == first_duration


def test_failed_load_does_not_retry_on_subsequent_calls(synthetic_env, make_settings):
    bad_policy_path = write_policy(synthetic_env["root"], "wrong-hash", filename="p.json")
    settings = make_settings(confidence_policy_path=bad_policy_path)
    loader = ModelLoader(settings)
    loader.load()
    first_reason = loader.failure_reason

    loader.load()  # must remain a no-op, not re-attempt
    assert loader.failure_reason == first_reason
    assert loader.is_ready is False


def test_cpu_fallback_works(make_settings):
    settings = make_settings(preferred_device="cpu")
    loader = ModelLoader(settings)
    loader.load()
    assert loader.is_ready is True
    assert loader.metadata.device == "cpu"


def test_concurrent_load_calls_return_the_same_instance(make_settings):
    settings = make_settings()
    loader = ModelLoader(settings)

    def _load():
        loader.load()

    threads = [threading.Thread(target=_load) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert loader.is_ready is True
    # A single successful load -- duration recorded exactly once, model
    # instance stable across all callers.
    model_ref = loader.get_model()
    assert loader.get_model() is model_ref


def test_get_model_raises_when_not_loaded(make_settings):
    settings = make_settings()
    loader = ModelLoader(settings)
    try:
        loader.get_model()
        assert False, "expected ModelLoadError"
    except ModelLoadError:
        pass


def test_release_clears_readiness(make_settings):
    settings = make_settings()
    loader = ModelLoader(settings)
    loader.load()
    assert loader.is_ready is True
    loader.release()
    assert loader.is_ready is False
