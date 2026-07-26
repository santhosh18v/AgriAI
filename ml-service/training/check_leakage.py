"""Preview leakage/schema validation for train/val/test split manifests
(Milestone M3B-3 / M3B-3A).

This is a PREVIEW check only. Final leakage sign-off is Milestone M3B-4 —
passing every check here does not mark a split as finally approved.

Expected CSV schema (produced by training/build_splits.py, M3B-3A):
    path, class_name, class_index, group_key, group_source,
    similarity_guard_group, sha256

Checks performed once split files exist:
  1. Zero sha256 overlap across the three manifests.
  2. Zero original group_key overlap across the three manifests.
  3. Zero similarity_guard_group overlap across the three manifests
     (empty values, meaning "no guard applies", are ignored).
  4. Every approved similarity guard (training/similarity_guards_v1.json) is
     represented correctly: all its original_group_keys are present, tagged
     with its guard_group_id, and land in exactly one split.
  5. Original group_key values are never overwritten by a guard id -- a
     guarded row's group_key must differ from its similarity_guard_group.
  6. No row belongs to a class outside the approved active scope
     (training/model_scope_v1.json).
  7. No quarantined image (ml-service/data/reports/split_input_integrity.json)
     is present in any manifest.
  8. Every manifest path exists on disk.
  9. Every active-scope class appears in all three splits.
 10. Manifest header/schema is exactly the expected 7 columns, in order.
 11. Potato Healthy satisfies its approved class-specific minimum exception;
     the other five active classes satisfy their unchanged general minimums.

Any failure exits non-zero with a report of the offending rows.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_splits import GENERAL_MIN, POTATO_HEALTHY_MIN  # noqa: E402

SPLIT_NAMES = ("train", "val", "test")
EXPECTED_SCHEMA = [
    "path",
    "class_name",
    "class_index",
    "group_key",
    "group_source",
    "similarity_guard_group",
    "sha256",
]

ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent


def load_split(path: Path, errors: list[str]):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            errors.append(f"{path}: empty file, no header row")
            return rows
        if header != EXPECTED_SCHEMA:
            errors.append(f"{path}: schema mismatch — expected {EXPECTED_SCHEMA}, got {header}")
        for raw in reader:
            rows.append(dict(zip(header, raw)))
    return rows


def check_leakage(splits_dir: Path) -> int:
    missing = [name for name in SPLIT_NAMES if not (splits_dir / f"{name}.csv").exists()]
    if missing:
        print(
            f"No split manifests found for: {', '.join(missing)} under {splits_dir}. "
            "Split generation (Milestone M3B-3A) has not produced manifests here yet.",
            file=sys.stderr,
        )
        return 2

    errors: list[str] = []

    rows_by_split = {}
    for name in SPLIT_NAMES:
        rows_by_split[name] = load_split(splits_dir / f"{name}.csv", errors)

    model_scope_path = ML_SERVICE_ROOT / "training" / "model_scope_v1.json"
    active_classes = set()
    if model_scope_path.exists():
        with open(model_scope_path) as f:
            active_classes = set(json.load(f).get("active_model_classes", []))

    quarantined_paths = set()
    integrity_report_path = ML_SERVICE_ROOT / "data" / "reports" / "split_input_integrity.json"
    if integrity_report_path.exists():
        with open(integrity_report_path) as f:
            integrity_report = json.load(f)
        quarantined_paths = {q["path"] for q in integrity_report.get("quarantined_images", [])}

    guards = []
    guards_path = ML_SERVICE_ROOT / "training" / "similarity_guards_v1.json"
    if guards_path.exists():
        with open(guards_path) as f:
            guards = json.load(f).get("guards", [])

    hash_to_splits: dict[str, set[str]] = defaultdict(set)
    group_to_splits: dict[str, set[str]] = defaultdict(set)
    guard_to_splits: dict[str, set[str]] = defaultdict(set)
    classes_seen_by_split: dict[str, set[str]] = {name: set() for name in SPLIT_NAMES}
    group_key_to_guard_seen: dict[str, str] = {}

    # (class_name, split_name) -> {"images": int, "groups": set(group_key)}
    per_class_split_counts: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"images": 0, "groups": set()}
    )

    for name in SPLIT_NAMES:
        for row in rows_by_split[name]:
            if not row.get("sha256"):
                continue
            hash_to_splits[row["sha256"]].add(name)
            group_to_splits[row["group_key"]].add(name)
            classes_seen_by_split[name].add(row["class_name"])

            guard_id = row.get("similarity_guard_group", "")
            if guard_id:
                guard_to_splits[guard_id].add(name)
                if guard_id == row["group_key"]:
                    errors.append(
                        f"{name}.csv: original group_key overwritten by similarity_guard_group "
                        f"for path={row['path']}"
                    )
                prev = group_key_to_guard_seen.get(row["group_key"])
                if prev is not None and prev != guard_id:
                    errors.append(
                        f"{name}.csv: group_key {row['group_key']!r} tagged with inconsistent "
                        f"similarity_guard_group values ({prev!r} vs {guard_id!r})"
                    )
                group_key_to_guard_seen[row["group_key"]] = guard_id

            key = (row["class_name"], name)
            per_class_split_counts[key]["images"] += 1
            per_class_split_counts[key]["groups"].add(row["group_key"])

            if active_classes and row["class_name"] not in active_classes:
                errors.append(
                    f"{name}.csv: row for out-of-scope class {row['class_name']!r} (path={row['path']})"
                )
            if row["path"] in quarantined_paths:
                errors.append(f"{name}.csv: quarantined image present (path={row['path']})")
            if not (ML_SERVICE_ROOT / row["path"]).exists():
                errors.append(f"{name}.csv: manifest path does not exist on disk: {row['path']}")

    hash_overlaps = {h: s for h, s in hash_to_splits.items() if len(s) > 1}
    group_overlaps = {g: s for g, s in group_to_splits.items() if len(s) > 1}
    guard_overlaps = {g: s for g, s in guard_to_splits.items() if len(s) > 1}

    if hash_overlaps:
        errors.append(f"{len(hash_overlaps)} sha256 values appear in multiple splits")
    if group_overlaps:
        errors.append(f"{len(group_overlaps)} group_key values appear in multiple splits")
    if guard_overlaps:
        errors.append(
            f"{len(guard_overlaps)} similarity_guard_group values appear in multiple splits: "
            f"{guard_overlaps}"
        )

    all_group_keys_seen = set(group_to_splits.keys())
    for guard in guards:
        gid = guard["guard_group_id"]
        expected_keys = set(guard["original_group_keys"])
        missing_keys = expected_keys - all_group_keys_seen
        if missing_keys:
            errors.append(f"guard {gid}: original group_key(s) missing from manifests: {missing_keys}")
            continue
        splits_touched = set()
        for k in expected_keys:
            splits_touched |= group_to_splits[k]
            if group_key_to_guard_seen.get(k) != gid:
                errors.append(
                    f"guard {gid}: group_key {k!r} not tagged with expected "
                    f"similarity_guard_group (found {group_key_to_guard_seen.get(k)!r})"
                )
        if len(splits_touched) != 1:
            errors.append(
                f"guard {gid}: linked group_keys are not all in exactly one split "
                f"(found in {sorted(splits_touched)})"
            )

    if active_classes:
        for name in SPLIT_NAMES:
            missing_classes = active_classes - classes_seen_by_split[name]
            if missing_classes:
                errors.append(f"{name}.csv: missing active class(es) {sorted(missing_classes)}")

    for class_name in sorted(active_classes):
        mins = POTATO_HEALTHY_MIN if class_name == "Potato Healthy" else GENERAL_MIN
        for split_name, req in mins.items():
            counts = per_class_split_counts.get((class_name, split_name), {"images": 0, "groups": set()})
            if counts["images"] < req["images"]:
                errors.append(
                    f"{class_name}/{split_name}: {counts['images']} images < required {req['images']}"
                )
            if len(counts["groups"]) < req["groups"]:
                errors.append(
                    f"{class_name}/{split_name}: {len(counts['groups'])} groups < required {req['groups']}"
                )

    if errors:
        print("LEAKAGE/SCHEMA PREVIEW CHECK FAILED", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1

    print(
        "LEAKAGE/SCHEMA PREVIEW CHECK PASSED: zero hash overlap, zero group_key overlap, zero "
        "similarity_guard_group overlap, all approved guards correctly represented and confined "
        "to one split each, original group keys unmodified, no out-of-scope/quarantined rows, "
        "all paths exist, all active classes present in all splits, schema correct, Potato "
        "Healthy exception and general minimums satisfied. This is a PREVIEW only — final "
        "sign-off is M3B-4."
    )
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--splits-dir", required=True, type=Path)
    args = parser.parse_args()
    sys.exit(check_leakage(args.splits_dir))


if __name__ == "__main__":
    main()
