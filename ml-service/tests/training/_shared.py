"""Shared constants/helpers for M4 training tests (plain module, not a
pytest conftest, so test files can `from _shared import ...` directly)."""

from __future__ import annotations

import csv

CLASS_MAP_8 = {
    "0": "Tomato Healthy",
    "1": "Tomato Early Blight",
    "2": "Tomato Late Blight",
    "3": "Potato Healthy",
    "4": "Potato Early Blight",
    "5": "Potato Late Blight",
    "6": "Corn Healthy",
    "7": "Corn Common Rust",
}
ACTIVE_CLASSES = [
    "Tomato Healthy",
    "Tomato Early Blight",
    "Tomato Late Blight",
    "Potato Healthy",
    "Potato Early Blight",
    "Potato Late Blight",
]
MANIFEST_COLUMNS = [
    "path",
    "class_name",
    "class_index",
    "group_key",
    "group_source",
    "similarity_guard_group",
    "sha256",
]


def name_to_index() -> dict[str, int]:
    return {v: int(k) for k, v in CLASS_MAP_8.items()}


def write_manifest(path, rows) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
