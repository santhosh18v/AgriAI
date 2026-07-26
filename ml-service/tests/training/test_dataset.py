"""Tests for training/dataset.py using tiny synthetic images/manifests."""

import torch

from _shared import ACTIVE_CLASSES, name_to_index, write_manifest
from dataset import ManifestImageDataset, ManifestValidationError


def test_valid_manifest_loads_all_rows(tiny_env):
    manifest_path = tiny_env["root"] / "val.csv"
    write_manifest(manifest_path, tiny_env["rows"])

    ds = ManifestImageDataset(
        manifest_path,
        tiny_env["class_map_path"],
        tiny_env["model_scope_path"],
        ml_service_root=tiny_env["root"],
    )
    assert len(ds) == len(tiny_env["rows"])


def test_labels_come_only_from_manifest_not_folder(tiny_env):
    """Images live in one flat folder (no per-class subfolders); labels must
    still resolve correctly purely from the manifest's class_index column."""
    manifest_path = tiny_env["root"] / "val.csv"
    write_manifest(manifest_path, tiny_env["rows"])

    ds = ManifestImageDataset(
        manifest_path,
        tiny_env["class_map_path"],
        tiny_env["model_scope_path"],
        ml_service_root=tiny_env["root"],
    )
    idx_by_name = name_to_index()
    for i, row in enumerate(tiny_env["rows"]):
        _, label = ds[i]
        assert label == idx_by_name[row["class_name"]]


def test_image_tensor_shape_after_transform(tiny_env):
    from torchvision import transforms as T

    manifest_path = tiny_env["root"] / "val.csv"
    write_manifest(manifest_path, tiny_env["rows"])
    transform = T.Compose([T.Resize((224, 224)), T.ToTensor()])

    ds = ManifestImageDataset(
        manifest_path,
        tiny_env["class_map_path"],
        tiny_env["model_scope_path"],
        transform=transform,
        ml_service_root=tiny_env["root"],
    )
    image, label = ds[0]
    assert isinstance(image, torch.Tensor)
    assert image.shape == (3, 224, 224)
    assert isinstance(label, int)


def test_return_path_metadata(tiny_env):
    manifest_path = tiny_env["root"] / "val.csv"
    write_manifest(manifest_path, tiny_env["rows"])

    ds = ManifestImageDataset(
        manifest_path,
        tiny_env["class_map_path"],
        tiny_env["model_scope_path"],
        return_path=True,
        ml_service_root=tiny_env["root"],
    )
    image, label, rel_path = ds[0]
    assert rel_path == tiny_env["rows"][0]["path"]


def test_missing_required_column_rejected(tiny_env):
    manifest_path = tiny_env["root"] / "val.csv"
    import csv

    with open(manifest_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["path", "class_name"])  # missing columns
        writer.writeheader()
        writer.writerow({"path": "x.png", "class_name": "Tomato Healthy"})

    try:
        ManifestImageDataset(
            manifest_path, tiny_env["class_map_path"], tiny_env["model_scope_path"],
            ml_service_root=tiny_env["root"],
        )
        assert False, "expected ManifestValidationError"
    except ManifestValidationError as e:
        assert "missing required column" in str(e)


def test_missing_image_file_rejected(tiny_env):
    rows = list(tiny_env["rows"])
    rows[0] = {**rows[0], "path": "images/does_not_exist.png"}
    manifest_path = tiny_env["root"] / "val.csv"
    write_manifest(manifest_path, rows)

    try:
        ManifestImageDataset(
            manifest_path, tiny_env["class_map_path"], tiny_env["model_scope_path"],
            ml_service_root=tiny_env["root"],
        )
        assert False, "expected ManifestValidationError"
    except ManifestValidationError as e:
        assert "missing on disk" in str(e)


def test_class_index_mismatch_rejected(tiny_env):
    rows = list(tiny_env["rows"])
    rows[0] = {**rows[0], "class_index": "99"}
    manifest_path = tiny_env["root"] / "val.csv"
    write_manifest(manifest_path, rows)

    try:
        ManifestImageDataset(
            manifest_path, tiny_env["class_map_path"], tiny_env["model_scope_path"],
            ml_service_root=tiny_env["root"],
        )
        assert False, "expected ManifestValidationError"
    except ManifestValidationError as e:
        assert "does not match class_map.json" in str(e)


def test_corn_class_rejected(tiny_env):
    rows = list(tiny_env["rows"])
    rows[0] = {**rows[0], "class_name": "Corn Healthy", "class_index": "6"}
    manifest_path = tiny_env["root"] / "val.csv"
    write_manifest(manifest_path, rows)

    try:
        ManifestImageDataset(
            manifest_path, tiny_env["class_map_path"], tiny_env["model_scope_path"],
            ml_service_root=tiny_env["root"],
        )
        assert False, "expected ManifestValidationError"
    except ManifestValidationError as e:
        assert "Corn" in str(e)


def test_out_of_scope_class_rejected(tiny_env):
    rows = list(tiny_env["rows"])
    rows[0] = {**rows[0], "class_name": "Pepper Healthy"}
    manifest_path = tiny_env["root"] / "val.csv"
    write_manifest(manifest_path, rows)

    try:
        ManifestImageDataset(
            manifest_path, tiny_env["class_map_path"], tiny_env["model_scope_path"],
            ml_service_root=tiny_env["root"],
        )
        assert False, "expected ManifestValidationError"
    except ManifestValidationError as e:
        assert "not in the approved active scope" in str(e)


def test_duplicate_path_rejected(tiny_env):
    rows = list(tiny_env["rows"])
    rows.append(rows[0])
    manifest_path = tiny_env["root"] / "val.csv"
    write_manifest(manifest_path, rows)

    try:
        ManifestImageDataset(
            manifest_path, tiny_env["class_map_path"], tiny_env["model_scope_path"],
            ml_service_root=tiny_env["root"],
        )
        assert False, "expected ManifestValidationError"
    except ManifestValidationError as e:
        assert "duplicate path" in str(e)


def test_test_manifest_refused_by_default(tiny_env):
    manifest_path = tiny_env["root"] / "test.csv"
    write_manifest(manifest_path, tiny_env["rows"])

    try:
        ManifestImageDataset(
            manifest_path, tiny_env["class_map_path"], tiny_env["model_scope_path"],
            ml_service_root=tiny_env["root"],
        )
        assert False, "expected ManifestValidationError"
    except ManifestValidationError as e:
        assert "test.csv must not be loaded" in str(e)


def test_test_manifest_allowed_with_explicit_opt_in(tiny_env):
    manifest_path = tiny_env["root"] / "test.csv"
    write_manifest(manifest_path, tiny_env["rows"])

    ds = ManifestImageDataset(
        manifest_path, tiny_env["class_map_path"], tiny_env["model_scope_path"],
        allow_test=True, ml_service_root=tiny_env["root"],
    )
    assert len(ds) == len(tiny_env["rows"])


def test_similarity_guard_group_does_not_affect_label(tiny_env):
    """Two rows for the same class, one with a similarity_guard_group value
    and one without, must produce the identical label -- the column is a
    split-safety marker only and must never influence class assignment."""
    base_rows = [r for r in tiny_env["rows"] if r["class_name"] == ACTIVE_CLASSES[0]]
    unguarded, guarded_source = base_rows[0], base_rows[1]
    guarded = {**guarded_source, "similarity_guard_group": "similarity-guard-phash-9999"}
    assert unguarded["class_name"] == guarded["class_name"]
    assert unguarded["similarity_guard_group"] != guarded["similarity_guard_group"]

    rows = [unguarded, guarded]
    manifest_path = tiny_env["root"] / "val.csv"
    write_manifest(manifest_path, rows)

    ds = ManifestImageDataset(
        manifest_path, tiny_env["class_map_path"], tiny_env["model_scope_path"],
        ml_service_root=tiny_env["root"],
    )
    _, label_unguarded = ds[0]
    _, label_guarded = ds[1]
    assert label_unguarded == label_guarded == name_to_index()[unguarded["class_name"]]


def test_class_counts_matches_manifest(tiny_env):
    manifest_path = tiny_env["root"] / "val.csv"
    write_manifest(manifest_path, tiny_env["rows"])

    ds = ManifestImageDataset(
        manifest_path, tiny_env["class_map_path"], tiny_env["model_scope_path"],
        ml_service_root=tiny_env["root"],
    )
    counts = ds.class_counts()
    assert counts == {name: 2 for name in ACTIVE_CLASSES}
