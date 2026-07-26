"""Shared fixtures for M6 API tests.

Builds a tiny synthetic checkpoint via training/model.py's real
build_model() (random weights, no download, well under a second) plus a
matching synthetic class_map/model_scope/confidence_policy. No automated
test in this suite loads the real ~48MB EfficientNet-B0 checkpoint --
that is exercised once, manually, outside pytest (see docs/API_FOUNDATION.md).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest
import torch

TRAINING_DIR = Path(__file__).resolve().parents[2] / "training"
if str(TRAINING_DIR) not in sys.path:
    sys.path.insert(0, str(TRAINING_DIR))

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from model import build_model  # noqa: E402
from train import build_checkpoint, build_transforms  # noqa: E402

CLASS_NAMES = [
    "Tomato Healthy",
    "Tomato Early Blight",
    "Tomato Late Blight",
    "Potato Healthy",
    "Potato Early Blight",
    "Potato Late Blight",
]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_synthetic_checkpoint(path: Path, class_names=CLASS_NAMES) -> str:
    class_to_index = {name: i for i, name in enumerate(class_names)}
    model = build_model(num_classes=len(class_names), pretrained=False)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4)
    _, _, transform_config = build_transforms()
    ckpt = build_checkpoint(
        model, optimizer, None, epoch=1, best_val_macro_f1=0.9, val_loss=0.1,
        class_names=class_names, class_to_index=class_to_index,
        transform_config=transform_config, run_config={"seed": 42, "transforms": transform_config},
        manifest_hashes={}, seed=42,
    )
    torch.save(ckpt, path)
    return _sha256_file(path)


def write_synthetic_class_map_and_scope(tmp_path: Path, class_names=CLASS_NAMES):
    class_map_path = tmp_path / "class_map.json"
    class_map_path.write_text(json.dumps({str(i): name for i, name in enumerate(class_names)}))
    model_scope_path = tmp_path / "model_scope_v1.json"
    model_scope_path.write_text(
        json.dumps({"status": "approved", "active_model_classes": class_names})
    )
    return class_map_path, model_scope_path


def write_policy(tmp_path: Path, checkpoint_sha256: str, filename="confidence_policy_v1.json", **overrides) -> Path:
    policy = {
        "version": 1,
        "status": "approved_for_test_application",
        "selection_dataset": "validation",
        "model_architecture": "efficientnet_b0",
        "checkpoint_sha256": checkpoint_sha256,
        "confidence_method": "maximum_softmax_probability",
        "selected_threshold": 0.5,
        "test_labels_used_for_threshold_selection": False,
    }
    policy.update(overrides)
    path = tmp_path / filename
    path.write_text(json.dumps(policy))
    return path


@pytest.fixture
def synthetic_env(tmp_path):
    """A complete, self-consistent, valid synthetic environment: checkpoint,
    class_map, model_scope, confidence_policy, all cross-referencing
    correctly. Individual tests mutate copies to introduce a single
    deliberate mismatch."""
    checkpoint_path = tmp_path / "checkpoint.pt"
    checkpoint_sha256 = write_synthetic_checkpoint(checkpoint_path)
    class_map_path, model_scope_path = write_synthetic_class_map_and_scope(tmp_path)
    policy_path = write_policy(tmp_path, checkpoint_sha256)

    return {
        "root": tmp_path,
        "checkpoint_path": checkpoint_path,
        "checkpoint_sha256": checkpoint_sha256,
        "class_map_path": class_map_path,
        "model_scope_path": model_scope_path,
        "policy_path": policy_path,
        "class_names": CLASS_NAMES,
    }


@pytest.fixture
def make_settings(synthetic_env):
    """Factory for a Settings instance pointed at the synthetic environment.
    Bypasses environment variables/.env entirely (explicit kwargs only)."""
    from app.config import Settings

    def _make(**overrides):
        kwargs = dict(
            model_checkpoint_path=synthetic_env["checkpoint_path"],
            confidence_policy_path=synthetic_env["policy_path"],
            class_map_path=synthetic_env["class_map_path"],
            model_scope_path=synthetic_env["model_scope_path"],
            preferred_device="cpu",
            eager_model_load=False,
        )
        kwargs.update(overrides)
        return Settings(**kwargs)

    return _make


@pytest.fixture
def app_client(make_settings):
    """A TestClient wired to a fresh FastAPI app instance built directly
    from a given Settings object (not the process-wide get_settings()
    cache), so each test gets full control and isolation."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    def _make(settings):
        app = create_app(settings)
        return TestClient(app)

    return _make
