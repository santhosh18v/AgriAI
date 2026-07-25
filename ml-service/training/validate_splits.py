"""Independent final leakage validation and split sign-off (Milestone M3B-4).

READ-ONLY validator. This script NEVER writes to, regenerates, or modifies
`ml-service/data/splits/{train,val,test}.csv`. It independently reconstructs
the expected class/group/guard assignment for every eligible image directly
from source evidence -- `leaf-map.json` (M3A), `exact_hash_report.json`
(M3A), `tomato_filename_group_candidates.json` (M3B-2A/M3B-2) -- and from
the approved policy files (`model_scope_v1.json`,
`tomato_grouping_policy_v1.json`, `similarity_guards_v1.json`), rather than
trusting `build_splits.py`'s own generated intermediate reports as ground
truth. The point of an independent M3B-4 sign-off is that a latent defect
in `build_splits.py`'s own bookkeeping would still be caught here.

Determinism is checked separately by the completion-report workflow (backup
the existing manifests/reports, regenerate via `build_splits.py` in place,
compare hashes, restore the backup) -- this script does not perform that
step itself, since it must never touch the manifests it is validating.

Exit code: 0 if every mandatory check passes, non-zero otherwise.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
TRAINING_DIR = ML_SERVICE_ROOT / "training"
REPORTS_DIR = ML_SERVICE_ROOT / "data" / "reports"
SPLITS_DIR = ML_SERVICE_ROOT / "data" / "splits"
SOURCE_ROOT = ML_SERVICE_ROOT / "data" / "raw" / "plantvillage-source"
COLOR_ROOT = SOURCE_ROOT / "raw" / "color"
LEAF_MAP_PATH = SOURCE_ROOT / "leaf-map.json"

SPLIT_NAMES = ("train", "val", "test")
EXPECTED_ROW_COUNTS = {"train": 4642, "val": 1001, "test": 991}
EXPECTED_TOTAL_ROWS = 6634
EXPECTED_MANIFEST_SHA256 = {
    "train": "3bec912c0efb7a22eb66b388c364be6ab784ce3e8637ffe716c0804655b99a79",
    "val": "85f86dec9e81566b19d0654559f6b56c11d4b7086f3d5b8d244e00cae91dd91f",
    "test": "3d0ee43d9edc836eefadb71bf178d55d3e60817053efa5f9f5a52cd04c284abb",
}
REQUIRED_COLUMNS = {
    "path",
    "class_name",
    "class_index",
    "group_key",
    "group_source",
    "sha256",
    "similarity_guard_group",
}

CLASS_NAME_TO_FOLDER = {
    "Tomato Healthy": "Tomato___healthy",
    "Tomato Early Blight": "Tomato___Early_blight",
    "Tomato Late Blight": "Tomato___Late_blight",
    "Potato Healthy": "Potato___healthy",
    "Potato Early Blight": "Potato___Early_blight",
    "Potato Late Blight": "Potato___Late_blight",
    "Corn Healthy": "Corn_(maize)___healthy",
    "Corn Common Rust": "Corn_(maize)___Common_rust_",
}
EXPECTED_8_CLASSES = [
    "Tomato Healthy",
    "Tomato Early Blight",
    "Tomato Late Blight",
    "Potato Healthy",
    "Potato Early Blight",
    "Potato Late Blight",
    "Corn Healthy",
    "Corn Common Rust",
]
CORN_CLASSES = {"Corn Healthy", "Corn Common Rust"}

GENERAL_MIN = {
    "val": {"images": 30, "groups": 15},
    "test": {"images": 30, "groups": 15},
}
POTATO_HEALTHY_MIN = {
    "train": {"images": 100, "groups": 15},
    "val": {"images": 20, "groups": 6},
    "test": {"images": 20, "groups": 6},
}
EXPECTED_POTATO_HEALTHY_ALLOCATION = {
    "train": {"images": 104, "groups": 26},
    "val": {"images": 24, "groups": 6},
    "test": {"images": 24, "groups": 6},
}

UUID_PREFIX_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}___"
)

GUARD_IDS_EXPECTED = {
    "similarity-guard-phash-2623",
    "similarity-guard-phash-4306",
    "similarity-guard-phash-6432",
}


class Recorder:
    """Collects (name, status, blocking, detail) check results."""

    def __init__(self):
        self.checks = []
        self.blocking_failed = False

    def check(self, name, ok, detail=None, blocking=True):
        entry = {"check": name, "status": "PASS" if ok else "FAIL", "blocking": blocking}
        if detail is not None:
            entry["detail"] = detail
        self.checks.append(entry)
        if blocking and not ok:
            self.blocking_failed = True
        return ok


def _load_json(path: Path):
    with open(path) as f:
        return json.load(f)


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _normalize_for_leaf_map(filename_no_ext: str) -> str:
    stripped = UUID_PREFIX_RE.sub("", filename_no_ext)
    return stripped.lower().strip()


def _iter_class_files(class_name: str):
    folder = CLASS_NAME_TO_FOLDER[class_name]
    for path in sorted((COLOR_ROOT / folder).glob("*")):
        if path.is_file():
            yield path


def _rel(path: Path) -> str:
    return str(path.relative_to(ML_SERVICE_ROOT))


# ---------------------------------------------------------------------------
# Independent policy loading
# ---------------------------------------------------------------------------

def load_policies(rec: Recorder):
    class_map = _load_json(TRAINING_DIR / "class_map.json")
    class_map_names = [class_map.get(str(i)) for i in range(8)]
    rec.check(
        "class_map.json defines all 8 original classes, unchanged",
        len(class_map) == 8 and class_map_names == EXPECTED_8_CLASSES,
        class_map_names,
    )

    model_scope = _load_json(TRAINING_DIR / "model_scope_v1.json")
    rec.check("model_scope_v1.json status is approved", model_scope.get("status") == "approved")
    active_classes = model_scope.get("active_model_classes", [])
    rec.check(
        "active scope is exactly the 6 approved classes, no Corn",
        len(active_classes) == 6 and set(active_classes).isdisjoint(CORN_CLASSES),
        active_classes,
    )

    grouping_policy = _load_json(TRAINING_DIR / "tomato_grouping_policy_v1.json")
    rec.check(
        "tomato_grouping_policy_v1.json status is approved",
        grouping_policy.get("status") == "approved",
    )

    guards_policy = _load_json(TRAINING_DIR / "similarity_guards_v1.json")
    rec.check(
        "similarity_guards_v1.json status is approved", guards_policy.get("status") == "approved"
    )
    guard_ids = {g["guard_group_id"] for g in guards_policy.get("guards", [])}
    rec.check(
        "exactly the 3 expected similarity guards are present",
        guard_ids == GUARD_IDS_EXPECTED,
        sorted(guard_ids),
    )

    return class_map, model_scope, active_classes, grouping_policy, guards_policy


# ---------------------------------------------------------------------------
# Independent reconstruction of the expected grouping/quarantine ledger
# ---------------------------------------------------------------------------

def build_expected_index(rec: Recorder, active_classes, grouping_policy):
    exact_hash_report = _load_json(REPORTS_DIR / "exact_hash_report.json")
    rec.check(
        "no unresolved cross-class exact-hash conflict exists",
        exact_hash_report.get("cross_class_conflict_group_count") == 0,
    )
    duplicate_paths = set()
    duplicate_group_detail = []
    for grp in exact_hash_report.get("same_class_duplicate_groups", []):
        duplicate_paths.update(grp["duplicates"])
        duplicate_group_detail.append(grp)

    leaf_map = _load_json(LEAF_MAP_PATH)
    path_to_leaf_id = {}
    for class_name in active_classes:
        folder = CLASS_NAME_TO_FOLDER[class_name]
        for path in _iter_class_files(class_name):
            rel = _rel(path)
            key = _normalize_for_leaf_map(path.stem)
            for candidate in leaf_map.get(key) or []:
                if candidate.startswith(folder + ":::"):
                    path_to_leaf_id[rel] = candidate
                    break

    candidates = _load_json(REPORTS_DIR / "tomato_filename_group_candidates.json")
    path_to_filename_group = {}
    th_groups = candidates.get("tomato_healthy_groups", {})
    tlb_groups = candidates.get("tomato_late_blight_groups", {})
    for group_id, entries in th_groups.items():
        for e in entries:
            path_to_filename_group[e["path"]] = group_id
    for group_id, entries in tlb_groups.items():
        for e in entries:
            path_to_filename_group[e["path"]] = group_id

    th_policy = grouping_policy["tomato_healthy"]
    tlb_policy = grouping_policy["tomato_late_blight"]
    rec.check(
        "Tomato Healthy candidate groups/images match approved policy counts",
        len(th_groups) == th_policy["approved_group_count"]
        and sum(len(v) for v in th_groups.values()) == th_policy["approved_image_count"],
        {"groups": len(th_groups), "images": sum(len(v) for v in th_groups.values())},
    )
    rec.check(
        "Tomato Late Blight candidate groups/images match approved policy counts",
        len(tlb_groups) == tlb_policy["approved_group_count"]
        and sum(len(v) for v in tlb_groups.values()) == tlb_policy["approved_image_count"],
        {"groups": len(tlb_groups), "images": sum(len(v) for v in tlb_groups.values())},
    )

    expected = {}  # path -> {class_name, group_key, group_source}
    quarantined_paths = set()
    per_class_group_sizes = defaultdict(lambda: defaultdict(int))  # class -> group_key -> size

    for class_name in active_classes:
        for path in _iter_class_files(class_name):
            rel = _rel(path)
            if rel in duplicate_paths:
                continue
            leaf_id = path_to_leaf_id.get(rel)
            fg = path_to_filename_group.get(rel)
            if leaf_id:
                group_key, group_source = leaf_id, "leaf_id"
            elif fg:
                group_key, group_source = fg, "tomato_filename_group"
            else:
                quarantined_paths.add(rel)
                continue
            expected[rel] = {
                "class_name": class_name,
                "group_key": group_key,
                "group_source": group_source,
            }
            per_class_group_sizes[class_name][group_key] += 1

    rec.check(
        "total independently-reconstructed quarantined images == 4",
        len(quarantined_paths) == 4,
        len(quarantined_paths),
    )

    return expected, quarantined_paths, duplicate_paths, per_class_group_sizes, duplicate_group_detail


def build_guard_index(rec: Recorder, guards_policy, active_classes, expected):
    """Independently validate similarity_guards_v1.json against the
    reconstructed expected index, then build group_key -> guard_group_id."""
    class_groups_present = defaultdict(set)
    for info in expected.values():
        class_groups_present[info["class_name"]].add(info["group_key"])

    group_key_to_guard = {}
    guards_by_id = {}
    for guard in guards_policy.get("guards", []):
        gid = guard["guard_group_id"]
        cname = guard["class_name"]
        keys = guard["original_group_keys"]
        guards_by_id[gid] = guard

        rec.check(f"guard {gid} class is in active scope", cname in active_classes, cname)

        missing = [k for k in keys if k not in class_groups_present[cname]]
        rec.check(f"guard {gid} original_group_keys exist for its class", not missing, missing)

        cross_hit = [
            k
            for other_class, other_keys in class_groups_present.items()
            if other_class != cname
            for k in keys
            if k in other_keys
        ]
        rec.check(f"guard {gid} does not cross class boundaries", not cross_hit, cross_hit)

        for k in keys:
            if k in group_key_to_guard and group_key_to_guard[k] != gid:
                rec.check(
                    "no original group_key claimed by multiple guards",
                    False,
                    {"group_key": k, "guards": [group_key_to_guard[k], gid]},
                )
            group_key_to_guard[k] = gid

    rec.check("no original group_key claimed by multiple guards", True)
    return group_key_to_guard, guards_by_id


# ---------------------------------------------------------------------------
# Manifest loading (read-only)
# ---------------------------------------------------------------------------

def load_manifest(name: str):
    path = SPLITS_DIR / f"{name}.csv"
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = [dict(zip(header, r)) for r in reader]
    return header, rows


# ---------------------------------------------------------------------------
# Main validation
# ---------------------------------------------------------------------------

def main():
    rec = Recorder()

    class_map, model_scope, active_classes, grouping_policy, guards_policy = load_policies(rec)
    class_index_by_name = {class_map[str(i)]: i for i in range(8)}

    expected, expected_quarantined, expected_duplicates, per_class_group_sizes, duplicate_detail = (
        build_expected_index(rec, active_classes, grouping_policy)
    )
    group_key_to_guard, guards_by_id = build_guard_index(rec, guards_policy, active_classes, expected)

    # --- Manifest hashes + row counts (section 3 / 7) ---
    manifest_hashes = {}
    manifests = {}
    for name in SPLIT_NAMES:
        manifest_path = SPLITS_DIR / f"{name}.csv"
        rec.check(f"{name}.csv exists", manifest_path.exists())
        actual_hash = _sha256_file(manifest_path)
        manifest_hashes[name] = actual_hash
        rec.check(
            f"{name}.csv SHA-256 matches expected committed hash",
            actual_hash == EXPECTED_MANIFEST_SHA256[name],
            {"expected": EXPECTED_MANIFEST_SHA256[name], "actual": actual_hash},
        )
        header, rows = load_manifest(name)
        manifests[name] = rows
        rec.check(
            f"{name}.csv schema contains all required columns",
            REQUIRED_COLUMNS.issubset(set(header)),
            {"header": header, "required": sorted(REQUIRED_COLUMNS)},
        )
        if header != [
            "path", "class_name", "class_index", "group_key", "group_source",
            "similarity_guard_group", "sha256",
        ]:
            rec.check(
                f"{name}.csv column order matches the M3B-3A generator (informational)",
                False,
                header,
                blocking=False,
            )
        rec.check(
            f"{name}.csv row count matches expected ({EXPECTED_ROW_COUNTS[name]})",
            len(rows) == EXPECTED_ROW_COUNTS[name],
            {"expected": EXPECTED_ROW_COUNTS[name], "actual": len(rows)},
        )

    total_rows = sum(len(manifests[n]) for n in SPLIT_NAMES)
    rec.check(
        "manifest total is exactly 6634 rows",
        total_rows == EXPECTED_TOTAL_ROWS,
        {"expected": EXPECTED_TOTAL_ROWS, "actual": total_rows},
    )

    # --- Row-level checks (section 3 + 5) ---
    missing_path_count = 0
    sha256_mismatch_count = 0
    class_index_mismatch_count = 0
    out_of_scope_class_count = 0
    corn_row_count = 0
    quarantined_row_count = 0
    duplicate_row_count = 0
    group_key_mismatch_count = 0
    group_source_mismatch_count = 0
    guard_mismatch_count = 0
    guard_overwrite_count = 0
    unresolved_path_count = 0
    row_mismatches = []

    duplicate_row_count_within_split = defaultdict(int)
    seen_paths_within_split = defaultdict(set)
    duplicate_row_within_manifest = 0

    path_to_split = {}
    path_first_seen = {}

    for name in SPLIT_NAMES:
        for row in manifests[name]:
            path = row["path"]
            abs_path = ML_SERVICE_ROOT / path

            if path in seen_paths_within_split[name]:
                duplicate_row_within_manifest += 1
            seen_paths_within_split[name].add(path)

            if not abs_path.exists():
                missing_path_count += 1
                continue

            actual_sha = _sha256_file(abs_path)
            if actual_sha != row["sha256"]:
                sha256_mismatch_count += 1

            if row["class_name"] not in active_classes:
                out_of_scope_class_count += 1
            if row["class_name"] in CORN_CLASSES:
                corn_row_count += 1
            if str(class_index_by_name.get(row["class_name"])) != row["class_index"]:
                class_index_mismatch_count += 1
            if path in expected_quarantined:
                quarantined_row_count += 1
            if path in expected_duplicates:
                duplicate_row_count += 1

            exp = expected.get(path)
            if exp is None:
                unresolved_path_count += 1
            else:
                if exp["group_key"] != row["group_key"]:
                    group_key_mismatch_count += 1
                    row_mismatches.append(
                        {
                            "path": path,
                            "field": "group_key",
                            "expected": exp["group_key"],
                            "actual": row["group_key"],
                        }
                    )
                if exp["group_source"] != row["group_source"]:
                    group_source_mismatch_count += 1
                    row_mismatches.append(
                        {
                            "path": path,
                            "field": "group_source",
                            "expected": exp["group_source"],
                            "actual": row["group_source"],
                        }
                    )
                expected_guard = group_key_to_guard.get(row["group_key"], "")
                if row.get("similarity_guard_group", "") != expected_guard:
                    guard_mismatch_count += 1
                    row_mismatches.append(
                        {
                            "path": path,
                            "field": "similarity_guard_group",
                            "expected": expected_guard,
                            "actual": row.get("similarity_guard_group", ""),
                        }
                    )
                if row.get("similarity_guard_group") and row.get("similarity_guard_group") == row["group_key"]:
                    guard_overwrite_count += 1

            path_to_split[path] = name

    rec.check("zero missing manifest paths", missing_path_count == 0, missing_path_count)
    rec.check("zero SHA-256 mismatches vs actual files", sha256_mismatch_count == 0, sha256_mismatch_count)
    rec.check("zero class_index mismatches vs class_map.json", class_index_mismatch_count == 0, class_index_mismatch_count)
    rec.check("zero out-of-scope-class rows", out_of_scope_class_count == 0, out_of_scope_class_count)
    rec.check("zero Corn rows", corn_row_count == 0, corn_row_count)
    rec.check("zero quarantined rows present", quarantined_row_count == 0, quarantined_row_count)
    rec.check("zero exact-duplicate rows present", duplicate_row_count == 0, duplicate_row_count)
    rec.check("zero unresolved manifest paths (every row independently reconstructable)", unresolved_path_count == 0, unresolved_path_count)
    rec.check("zero duplicate rows within a single manifest", duplicate_row_within_manifest == 0, duplicate_row_within_manifest)
    rec.check("zero group_key mismatches vs independently reconstructed policy", group_key_mismatch_count == 0, group_key_mismatch_count)
    rec.check("zero group_source mismatches vs independently reconstructed policy", group_source_mismatch_count == 0, group_source_mismatch_count)
    rec.check("zero similarity_guard_group mismatches vs approved guard policy", guard_mismatch_count == 0, guard_mismatch_count)
    rec.check("zero rows where similarity_guard_group overwrote the original group_key", guard_overwrite_count == 0, guard_overwrite_count)

    # --- Cross-split leakage checks (section 4) ---
    path_sets = {name: {row["path"] for row in manifests[name]} for name in SPLIT_NAMES}
    sha_sets = {name: {row["sha256"] for row in manifests[name]} for name in SPLIT_NAMES}
    group_sets = {name: {row["group_key"] for row in manifests[name]} for name in SPLIT_NAMES}
    guard_sets = {
        name: {row["similarity_guard_group"] for row in manifests[name] if row.get("similarity_guard_group")}
        for name in SPLIT_NAMES
    }

    def pairwise_overlaps(sets_by_split):
        overlaps = {}
        names = list(sets_by_split.keys())
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                a, b = names[i], names[j]
                overlaps[f"{a}_vs_{b}"] = sorted(sets_by_split[a] & sets_by_split[b])
        return overlaps

    path_overlaps = pairwise_overlaps(path_sets)
    sha_overlaps = pairwise_overlaps(sha_sets)
    group_overlaps = pairwise_overlaps(group_sets)
    guard_overlaps = pairwise_overlaps(guard_sets)

    path_overlap_count = sum(len(v) for v in path_overlaps.values())
    sha_overlap_count = sum(len(v) for v in sha_overlaps.values())
    group_overlap_count = sum(len(v) for v in group_overlaps.values())
    guard_overlap_count = sum(len(v) for v in guard_overlaps.values())

    rec.check("zero identical file-path overlap across splits", path_overlap_count == 0, path_overlap_count)
    rec.check("zero SHA-256 overlap across splits", sha_overlap_count == 0, sha_overlap_count)
    rec.check("zero original group_key overlap across splits", group_overlap_count == 0, group_overlap_count)
    rec.check("zero similarity_guard_group overlap across splits", guard_overlap_count == 0, guard_overlap_count)

    # Physical-leaf / Tomato-filename group crossing, split by group_source.
    group_key_to_source = {info["group_key"]: info["group_source"] for info in expected.values()}
    leaf_id_group_overlap = 0
    filename_group_overlap = 0
    for keys in group_overlaps.values():
        for k in keys:
            source = group_key_to_source.get(k)
            if source == "leaf_id":
                leaf_id_group_overlap += 1
            elif source == "tomato_filename_group":
                filename_group_overlap += 1
    rec.check("no approved physical-leaf (leaf_id) group crosses splits", leaf_id_group_overlap == 0, leaf_id_group_overlap)
    rec.check("no approved Tomato filename group crosses splits", filename_group_overlap == 0, filename_group_overlap)

    # --- Similarity guard specific checks (section 6) ---
    guard_split_findings = {}
    for gid, guard in guards_by_id.items():
        splits_seen = {path_to_split.get(m["path"]) for m in guard["members"]}
        splits_seen.discard(None)
        ok = len(splits_seen) == 1
        guard_split_findings[gid] = {"splits_seen": sorted(splits_seen), "single_split": ok}
        rec.check(f"guard {gid} confined to exactly one split", ok, sorted(splits_seen))

    phash6432 = guards_by_id.get("similarity-guard-phash-6432")
    if phash6432:
        splits_seen = {path_to_split.get(m["path"]) for m in phash6432["members"]}
        rec.check(
            "phash-6432 no longer split between train and validation",
            not ({"train", "val"}.issubset(splits_seen)),
            sorted(splits_seen),
        )

    # --- Potato Healthy exception + general minimums (section 7) ---
    per_class_split_counts = defaultdict(lambda: defaultdict(lambda: {"images": 0, "groups": set()}))
    for name in SPLIT_NAMES:
        for row in manifests[name]:
            c = per_class_split_counts[row["class_name"]][name]
            c["images"] += 1
            c["groups"].add(row["group_key"])

    minimum_results = {}
    for class_name in sorted(active_classes):
        mins = POTATO_HEALTHY_MIN if class_name == "Potato Healthy" else GENERAL_MIN
        class_result = {}
        for split_name, req in mins.items():
            counts = per_class_split_counts[class_name][split_name]
            img_ok = counts["images"] >= req["images"]
            grp_ok = len(counts["groups"]) >= req["groups"]
            ok = img_ok and grp_ok
            class_result[split_name] = {
                "required_images": req["images"],
                "achieved_images": counts["images"],
                "required_groups": req["groups"],
                "achieved_groups": len(counts["groups"]),
                "status": "PASS" if ok else "FAIL",
            }
            rec.check(f"{class_name}/{split_name} meets its minimum", ok, class_result[split_name])
        minimum_results[class_name] = class_result

    ph_actual = {
        s: {
            "images": per_class_split_counts["Potato Healthy"][s]["images"],
            "groups": len(per_class_split_counts["Potato Healthy"][s]["groups"]),
        }
        for s in SPLIT_NAMES
    }
    rec.check(
        "Potato Healthy exact allocation matches approved Option A",
        ph_actual == EXPECTED_POTATO_HEALTHY_ALLOCATION,
        {"expected": EXPECTED_POTATO_HEALTHY_ALLOCATION, "actual": ph_actual},
    )

    # ------------------------------------------------------------------
    # Reports
    # ------------------------------------------------------------------
    approved_for_training = not rec.blocking_failed

    final_split_validation = {
        "milestone": "M3B-4",
        "validated_at_utc": datetime.now(timezone.utc).isoformat(),
        "validation_status": "approved_for_training" if approved_for_training else "blocked_validation_failure",
        "manifest_hashes": manifest_hashes,
        "expected_manifest_hashes": EXPECTED_MANIFEST_SHA256,
        "row_counts": {n: len(manifests[n]) for n in SPLIT_NAMES},
        "expected_row_counts": EXPECTED_ROW_COUNTS,
        "total_rows": total_rows,
        "missing_path_count": missing_path_count,
        "sha256_mismatch_count": sha256_mismatch_count,
        "class_index_mismatch_count": class_index_mismatch_count,
        "out_of_scope_class_row_count": out_of_scope_class_count,
        "corn_row_count": corn_row_count,
        "quarantined_row_count": quarantined_row_count,
        "duplicate_row_count": duplicate_row_count,
        "group_key_mismatch_count": group_key_mismatch_count,
        "group_source_mismatch_count": group_source_mismatch_count,
        "similarity_guard_mismatch_count": guard_mismatch_count,
        "similarity_guard_overwrite_count": guard_overwrite_count,
        "minimum_check_results": minimum_results,
        "potato_healthy_exact_allocation": ph_actual,
        "similarity_guard_results": guard_split_findings,
        "known_limitations": [
            "Potato Healthy has only 38 authoritative physical-leaf groups; "
            "validation and test each contain only 6 independent leaf groups. "
            "Per-class precision/recall/F1 for this class carry high "
            "uncertainty, and macro-F1 must be interpreted cautiously "
            "whenever Potato Healthy is included.",
            "similarity_guard_group entries are a split-safety constraint "
            "only; they do not assert that guarded images share one "
            "physical leaf.",
            "Determinism re-verification (backup/regenerate/compare/restore) "
            "is performed by the M3B-4 workflow, not by this script, since "
            "this script must never write to the manifests it validates.",
        ],
        "all_checks": rec.checks,
    }
    _write_json(REPORTS_DIR / "final_split_validation.json", final_split_validation)

    final_leakage_matrix = {
        "milestone": "M3B-4",
        "path_overlaps": {"counts": {k: len(v) for k, v in path_overlaps.items()}, "total": path_overlap_count, "detail": path_overlaps},
        "sha256_overlaps": {"counts": {k: len(v) for k, v in sha_overlaps.items()}, "total": sha_overlap_count, "detail": sha_overlaps},
        "group_key_overlaps": {"counts": {k: len(v) for k, v in group_overlaps.items()}, "total": group_overlap_count, "detail": group_overlaps},
        "similarity_guard_overlaps": {"counts": {k: len(v) for k, v in guard_overlaps.items()}, "total": guard_overlap_count, "detail": guard_overlaps},
        "leaf_id_group_crossing_count": leaf_id_group_overlap,
        "tomato_filename_group_crossing_count": filename_group_overlap,
    }
    _write_json(REPORTS_DIR / "final_leakage_matrix.json", final_leakage_matrix)

    final_group_integrity = {
        "milestone": "M3B-4",
        "group_key_mismatch_count": group_key_mismatch_count,
        "group_source_mismatch_count": group_source_mismatch_count,
        "similarity_guard_mismatch_count": guard_mismatch_count,
        "similarity_guard_overwrite_count": guard_overwrite_count,
        "unresolved_path_count": unresolved_path_count,
        "row_mismatches": row_mismatches,
        "similarity_guards_checked": sorted(guards_by_id.keys()),
        "similarity_guard_results": guard_split_findings,
    }
    _write_json(REPORTS_DIR / "final_group_integrity.json", final_group_integrity)

    print(
        json.dumps(
            {
                "validation_status": final_split_validation["validation_status"],
                "total_rows": total_rows,
                "blocking_checks_failed": rec.blocking_failed,
            },
            indent=2,
        )
    )
    return 0 if approved_for_training else 1


if __name__ == "__main__":
    sys.exit(main())
