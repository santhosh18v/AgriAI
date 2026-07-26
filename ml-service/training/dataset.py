"""Manifest-driven image dataset for the M4 EfficientNet-B0 baseline.

Loads exactly what the approved M3B-4 split manifests (`train.csv`,
`val.csv`, `test.csv`) record -- nothing is inferred from folder names or
recomputed. Labels come only from each row's `class_name`/`class_index`;
`class_index` is validated against `training/class_map.json`, and
`class_name` is validated against the approved active scope in
`training/model_scope_v1.json`. `test.csv` is refused unless the caller
explicitly opts in with `allow_test=True` -- during M4 nothing does.
"""

from __future__ import annotations

import csv
from pathlib import Path

from PIL import Image
from torch.utils.data import Dataset

ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent

REQUIRED_COLUMNS = [
    "path",
    "class_name",
    "class_index",
    "group_key",
    "group_source",
    "similarity_guard_group",
    "sha256",
]

CORN_CLASSES = {"Corn Healthy", "Corn Common Rust"}


class ManifestValidationError(Exception):
    """Raised when a manifest or its rows violate an approved-policy invariant."""


def load_class_index_by_name(class_map_path: Path) -> dict[str, int]:
    import json

    with open(class_map_path) as f:
        class_map = json.load(f)
    return {name: int(idx) for idx, name in class_map.items()}


def load_active_classes(model_scope_path: Path) -> list[str]:
    import json

    with open(model_scope_path) as f:
        model_scope = json.load(f)
    active = model_scope.get("active_model_classes", [])
    if model_scope.get("status") != "approved":
        raise ManifestValidationError(
            f"model_scope_v1.json status is {model_scope.get('status')!r}, expected 'approved'"
        )
    if len(active) != 6:
        raise ManifestValidationError(
            f"M4 requires exactly 6 active classes, found {len(active)}: {active}"
        )
    if not set(active).isdisjoint(CORN_CLASSES):
        raise ManifestValidationError(f"active scope must not include Corn classes: {active}")
    return active


class ManifestImageDataset(Dataset):
    """torch Dataset backed by one approved split manifest CSV.

    Returns (image_tensor, class_index) by default, or
    (image_tensor, class_index, relative_path) when `return_path=True`.
    """

    def __init__(
        self,
        manifest_path: str | Path,
        class_map_path: str | Path,
        model_scope_path: str | Path,
        transform=None,
        return_path: bool = False,
        allow_test: bool = False,
        ml_service_root: Path | None = None,
    ):
        manifest_path = Path(manifest_path)
        self.manifest_path = manifest_path
        self.transform = transform
        self.return_path = return_path
        self.ml_service_root = ml_service_root or ML_SERVICE_ROOT

        if manifest_path.name == "test.csv" and not allow_test:
            raise ManifestValidationError(
                "test.csv must not be loaded during M4 (training, validation, early "
                "stopping, model selection, and threshold selection are all "
                "forbidden from using the test manifest). Pass allow_test=True "
                "only from an explicit, later M5 evaluation mode."
            )

        class_index_by_name = load_class_index_by_name(Path(class_map_path))
        active_classes = load_active_classes(Path(model_scope_path))
        self.class_index_by_name = class_index_by_name
        self.active_classes = active_classes

        if not manifest_path.exists():
            raise FileNotFoundError(f"manifest not found: {manifest_path}")

        self.samples: list[tuple[str, int, str]] = []
        seen_paths: set[str] = set()

        with open(manifest_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            header = reader.fieldnames or []
            missing_cols = [c for c in REQUIRED_COLUMNS if c not in header]
            if missing_cols:
                raise ManifestValidationError(
                    f"{manifest_path}: missing required column(s) {missing_cols}; "
                    f"found columns {header}"
                )

            for row_num, row in enumerate(reader, start=2):  # header is line 1
                rel_path = row["path"]
                class_name = row["class_name"]

                if rel_path in seen_paths:
                    raise ManifestValidationError(
                        f"{manifest_path}:{row_num}: duplicate path in manifest: {rel_path}"
                    )
                seen_paths.add(rel_path)

                if class_name in CORN_CLASSES:
                    raise ManifestValidationError(
                        f"{manifest_path}:{row_num}: Corn class {class_name!r} present "
                        f"in manifest; Corn is out of scope for M4"
                    )
                if class_name not in active_classes:
                    raise ManifestValidationError(
                        f"{manifest_path}:{row_num}: class {class_name!r} is not in "
                        f"the approved active scope {active_classes}"
                    )

                expected_index = class_index_by_name.get(class_name)
                if expected_index is None:
                    raise ManifestValidationError(
                        f"{manifest_path}:{row_num}: class {class_name!r} not found in class_map.json"
                    )
                try:
                    row_index = int(row["class_index"])
                except (TypeError, ValueError) as e:
                    raise ManifestValidationError(
                        f"{manifest_path}:{row_num}: class_index {row['class_index']!r} is not an integer"
                    ) from e
                if row_index != expected_index:
                    raise ManifestValidationError(
                        f"{manifest_path}:{row_num}: class_index {row_index} for "
                        f"{class_name!r} does not match class_map.json's index "
                        f"{expected_index}"
                    )

                abs_path = self.ml_service_root / rel_path
                if not abs_path.is_file():
                    raise ManifestValidationError(
                        f"{manifest_path}:{row_num}: image file missing on disk: {abs_path}"
                    )

                self.samples.append((str(abs_path), row_index, rel_path))

        if not self.samples:
            raise ManifestValidationError(f"{manifest_path}: contains zero usable rows")

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int):
        abs_path, label, rel_path = self.samples[idx]
        try:
            with Image.open(abs_path) as img:
                image = img.convert("RGB")
        except Exception as e:
            raise RuntimeError(f"failed to load/decode image {abs_path}: {e}") from e

        if self.transform is not None:
            image = self.transform(image)

        if self.return_path:
            return image, label, rel_path
        return image, label

    def class_counts(self) -> dict[str, int]:
        name_by_index = {v: k for k, v in self.class_index_by_name.items()}
        counts: dict[str, int] = {name: 0 for name in self.active_classes}
        for _, label, _ in self.samples:
            counts[name_by_index[label]] += 1
        return counts
