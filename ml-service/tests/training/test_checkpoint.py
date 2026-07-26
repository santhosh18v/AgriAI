"""Tests for checkpoint save/load and incompatible-checkpoint rejection."""

import torch

from model import build_model
from train import build_checkpoint, validate_resume_checkpoint

CLASS_NAMES = [
    "Tomato Healthy",
    "Tomato Early Blight",
    "Tomato Late Blight",
    "Potato Healthy",
    "Potato Early Blight",
    "Potato Late Blight",
]
CLASS_TO_INDEX = {name: i for i, name in enumerate(CLASS_NAMES)}
MANIFEST_HASHES = {"train_manifest_sha256": "abc", "val_manifest_sha256": "def"}
RUN_CONFIG = {"seed": 42, "transforms": {"image_size": 224}}


def _make_checkpoint(tmp_path):
    model = build_model(num_classes=6, pretrained=False)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4)
    ckpt = build_checkpoint(
        model, optimizer, None, epoch=3, best_val_macro_f1=0.9, val_loss=0.2,
        class_names=CLASS_NAMES, class_to_index=CLASS_TO_INDEX,
        transform_config=RUN_CONFIG["transforms"], run_config=RUN_CONFIG,
        manifest_hashes=MANIFEST_HASHES, seed=42,
    )
    path = tmp_path / "ckpt.pt"
    torch.save(ckpt, path)
    return path, model


def test_checkpoint_round_trip(tmp_path):
    path, original_model = _make_checkpoint(tmp_path)
    loaded = torch.load(path, map_location="cpu", weights_only=False)

    assert loaded["epoch"] == 3
    assert loaded["class_names"] == CLASS_NAMES
    assert loaded["architecture"] == "efficientnet_b0"

    rebuilt = build_model(num_classes=6, pretrained=False)
    rebuilt.load_state_dict(loaded["model_state_dict"])
    for p1, p2 in zip(original_model.parameters(), rebuilt.parameters()):
        assert torch.equal(p1, p2)


def test_validate_resume_checkpoint_accepts_matching_config(tmp_path):
    path, _ = _make_checkpoint(tmp_path)
    ckpt = torch.load(path, map_location="cpu", weights_only=False)
    problems = validate_resume_checkpoint(ckpt, CLASS_NAMES, CLASS_TO_INDEX, MANIFEST_HASHES, RUN_CONFIG)
    assert problems == []


def test_validate_resume_checkpoint_rejects_manifest_hash_mismatch(tmp_path):
    path, _ = _make_checkpoint(tmp_path)
    ckpt = torch.load(path, map_location="cpu", weights_only=False)
    different_hashes = {"train_manifest_sha256": "CHANGED", "val_manifest_sha256": "def"}
    problems = validate_resume_checkpoint(ckpt, CLASS_NAMES, CLASS_TO_INDEX, different_hashes, RUN_CONFIG)
    assert any("manifest_hashes mismatch" in p for p in problems)


def test_validate_resume_checkpoint_rejects_class_names_mismatch(tmp_path):
    path, _ = _make_checkpoint(tmp_path)
    ckpt = torch.load(path, map_location="cpu", weights_only=False)
    different_names = CLASS_NAMES[:-1] + ["Corn Healthy"]
    problems = validate_resume_checkpoint(ckpt, different_names, CLASS_TO_INDEX, MANIFEST_HASHES, RUN_CONFIG)
    assert any("class_names mismatch" in p for p in problems)


def test_validate_resume_checkpoint_rejects_seed_mismatch(tmp_path):
    path, _ = _make_checkpoint(tmp_path)
    ckpt = torch.load(path, map_location="cpu", weights_only=False)
    different_run_config = {**RUN_CONFIG, "seed": 999}
    problems = validate_resume_checkpoint(ckpt, CLASS_NAMES, CLASS_TO_INDEX, MANIFEST_HASHES, different_run_config)
    assert any("seed mismatch" in p for p in problems)
