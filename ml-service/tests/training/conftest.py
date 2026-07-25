"""Shared fixtures for M4 training tests.

Uses tiny synthetic in-memory-generated images and manifests only -- never
copies real PlantVillage images into the repo.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "training"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _shared import ACTIVE_CLASSES, CLASS_MAP_8, name_to_index  # noqa: E402


@pytest.fixture
def tiny_env(tmp_path):
    """Builds tiny synthetic class_map.json, model_scope_v1.json, images,
    and manifest rows (2 images per active class) under tmp_path."""
    class_map_path = tmp_path / "class_map.json"
    class_map_path.write_text(json.dumps(CLASS_MAP_8))

    model_scope_path = tmp_path / "model_scope_v1.json"
    model_scope_path.write_text(
        json.dumps({"status": "approved", "active_model_classes": ACTIVE_CLASSES})
    )

    images_dir = tmp_path / "images"
    images_dir.mkdir()

    idx_by_name = name_to_index()
    rows = []
    for name in ACTIVE_CLASSES:
        idx = idx_by_name[name]
        for i in range(2):
            img_path = images_dir / f"{name.replace(' ', '_')}_{i}.png"
            Image.new("RGB", (8, 8), color=((i * 40) % 256, (idx * 30) % 256, 50)).save(img_path)
            rows.append(
                {
                    "path": str(img_path.relative_to(tmp_path)),
                    "class_name": name,
                    "class_index": str(idx),
                    "group_key": f"grp::{name}::{i}",
                    "group_source": "leaf_id",
                    "similarity_guard_group": "",
                    "sha256": "deadbeef",
                }
            )

    return {
        "root": tmp_path,
        "class_map_path": class_map_path,
        "model_scope_path": model_scope_path,
        "images_dir": images_dir,
        "rows": rows,
    }
