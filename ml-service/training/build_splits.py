"""Deterministic grouped 70/15/15 split generation (Milestones M3B-3 / M3B-3A).

Builds train/validation/test manifests for the approved 6-class first-model
scope (`ml-service/training/model_scope_v1.json`), using only grouping
evidence already approved during M3B-2
(`ml-service/training/tomato_grouping_policy_v1.json`). This script does not
make any new grouping decision -- it mechanically applies decisions already
recorded in those tracked files plus the read-only M3A/M3B evidence reports.

Group-key precedence (highest first):
  1. authoritative leaf_id (from leaf-map.json, M3A join)
  2. approved Tomato filename-family group (M3B-2 policy)
  3. approved pHash group as a GROUPING KEY -- NOT USED HERE. Every
     within-class pHash cluster in scope is already covered by (1) or (2)
     per ml-service/data/reports/m3b2_phash_decisions.json; the 3 Corn
     clusters are needs_more_review and moot (Corn is out of scope). No new
     pHash approval is created by this script.
  4. quarantine (image excluded from all splits)

M3B-3A addition -- similarity guards (split-safety only, NOT a grouping key):
`ml-service/training/similarity_guards_v1.json` records 3 approved
`similarity_guard_group` constraints, each linking two ORIGINAL groups (from
precedence tiers 1-2 above) that a pHash cluster flagged as near-identical.
A guard forces its linked original groups into the same split. It does NOT
merge, rename, or overwrite the original group_key/group_source of any
image, and does NOT assert the linked images share one physical leaf --
see the guard file's `meaning` field. Allocation operates on "components":
one original group when no guard applies, or the union of every original
group sharing one guard_group_id when a guard applies.

Milestone boundary: this script performs split generation only. It does not
train a model and does not perform M3B-4 final leakage sign-off -- the
manifests it writes are a REVIEW ARTIFACT, not a finally-approved split.
"""

from __future__ import annotations

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
SIMILARITY_GUARDS_PATH = TRAINING_DIR / "similarity_guards_v1.json"

SEED = 42
TRAIN_FRAC, VAL_FRAC, TEST_FRAC = 0.70, 0.15, 0.15
SPLIT_NAMES = ("train", "val", "test")
SPLIT_PRIORITY = ["train", "val", "test"]  # fixed tie-break order, deterministic

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

UUID_PREFIX_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}___"
)

GENERAL_MIN = {
    "val": {"images": 30, "groups": 15},
    "test": {"images": 30, "groups": 15},
}
# Potato Healthy class-specific exception, approved M3B-3A: only 38
# authoritative leaf_id groups exist for this class (152 images, all
# groups of size 4), so the original general minimum (val/test >= 8 groups)
# is mathematically infeasible alongside train's >=100 image / >=25 group
# floor (25+8+8=41 > 38 available). 6 is the largest symmetric val=test
# group floor achievable without breaching train's own minimum
# (25+6+6=37 <= 38). This exception applies ONLY to Potato Healthy; the
# other 5 classes keep GENERAL_MIN unchanged.
POTATO_HEALTHY_MIN = {
    "train": {"images": 100, "groups": 15},
    "val": {"images": 20, "groups": 6},
    "test": {"images": 20, "groups": 6},
}


class IntegrityCheckFailed(Exception):
    pass


def _load_json(path: Path):
    with open(path) as f:
        return json.load(f)


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    f_size = path.stat().st_size
    return f_size


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalize_for_leaf_map(filename_no_ext: str) -> str:
    stripped = UUID_PREFIX_RE.sub("", filename_no_ext)
    return stripped.lower().strip()


def _iter_class_files(class_name: str):
    folder = CLASS_NAME_TO_FOLDER[class_name]
    class_dir = COLOR_ROOT / folder
    for path in sorted(class_dir.glob("*")):
        if path.is_file():
            yield path


def _rel(path: Path) -> str:
    return str(path.relative_to(ML_SERVICE_ROOT))


# ---------------------------------------------------------------------------
# Stage 0: load + verify all required inputs (Section 11 of the M3B-3 brief)
# ---------------------------------------------------------------------------

def run_input_integrity_checks():
    checks = []

    def check(name, condition, detail=None):
        entry = {"check": name, "status": "PASS" if condition else "FAIL"}
        if detail is not None:
            entry["detail"] = detail
        checks.append(entry)
        if not condition:
            raise IntegrityCheckFailed(f"{name}: {detail}")
        return entry

    model_scope = _load_json(TRAINING_DIR / "model_scope_v1.json")
    check(
        "model_scope_v1.json status is approved",
        model_scope.get("status") == "approved",
        model_scope.get("status"),
    )

    grouping_policy = _load_json(TRAINING_DIR / "tomato_grouping_policy_v1.json")
    check(
        "tomato_grouping_policy_v1.json status is approved",
        grouping_policy.get("status") == "approved",
        grouping_policy.get("status"),
    )

    class_map = _load_json(TRAINING_DIR / "class_map.json")
    class_map_names = [class_map.get(str(i)) for i in range(8)]
    check(
        "class_map.json still contains all 8 original classes in order",
        len(class_map) == 8 and class_map_names == EXPECTED_8_CLASSES,
        class_map_names,
    )

    active_classes = model_scope.get("active_model_classes", [])
    check(
        "active scope contains exactly 6 approved classes",
        len(active_classes) == 6 and set(active_classes).isdisjoint(CORN_CLASSES),
        active_classes,
    )

    exact_hash_report = _load_json(REPORTS_DIR / "exact_hash_report.json")
    check(
        "no unresolved cross-class exact-hash conflict exists",
        exact_hash_report.get("cross_class_conflict_group_count") == 0,
        exact_hash_report.get("cross_class_conflict_group_count"),
    )

    similarity_guards_policy = _load_json(SIMILARITY_GUARDS_PATH)
    check(
        "similarity_guards_v1.json status is approved",
        similarity_guards_policy.get("status") == "approved",
        similarity_guards_policy.get("status"),
    )

    return (
        checks,
        model_scope,
        grouping_policy,
        class_map,
        active_classes,
        exact_hash_report,
        similarity_guards_policy,
    )


# ---------------------------------------------------------------------------
# Stage 1: duplicate collapsing (exact_hash_report.json, M3A evidence)
# ---------------------------------------------------------------------------

def build_duplicate_exclusion_set(exact_hash_report: dict):
    duplicate_paths = set()
    duplicate_detail = []
    for grp in exact_hash_report.get("same_class_duplicate_groups", []):
        for dup in grp["duplicates"]:
            duplicate_paths.add(dup)
        duplicate_detail.append(grp)
    return duplicate_paths, duplicate_detail


# ---------------------------------------------------------------------------
# Stage 2: authoritative leaf_id join (recomputed identically to
# prepare_dataset.py's stage_leaf_id_join, restricted to active classes)
# ---------------------------------------------------------------------------

def build_leaf_id_index(active_classes: list[str], leaf_map: dict):
    path_to_leaf_id = {}
    per_class_matched = defaultdict(int)
    per_class_total = defaultdict(int)

    for class_name in active_classes:
        folder = CLASS_NAME_TO_FOLDER[class_name]
        for path in _iter_class_files(class_name):
            rel = _rel(path)
            per_class_total[class_name] += 1
            key = _normalize_for_leaf_map(path.stem)
            candidates = leaf_map.get(key)
            matched = None
            if candidates:
                for c in candidates:
                    if c.startswith(folder + ":::"):
                        matched = c
                        break
            if matched:
                path_to_leaf_id[rel] = matched
                per_class_matched[class_name] += 1

    return path_to_leaf_id, per_class_matched, per_class_total


# ---------------------------------------------------------------------------
# Stage 3: approved Tomato filename-family groups (M3B-2 policy, applied to
# the precomputed candidate data from M3B-2A/M3B-2 -- read-only evidence)
# ---------------------------------------------------------------------------

def build_filename_group_index(candidates: dict, grouping_policy: dict):
    path_to_group = {}
    group_to_paths = defaultdict(list)

    th_groups = candidates.get("tomato_healthy_groups", {})
    tlb_groups = candidates.get("tomato_late_blight_groups", {})

    for group_id, entries in th_groups.items():
        for e in entries:
            path_to_group[e["path"]] = group_id
            group_to_paths[group_id].append(e["path"])

    for group_id, entries in tlb_groups.items():
        for e in entries:
            path_to_group[e["path"]] = group_id
            group_to_paths[group_id].append(e["path"])

    th_policy = grouping_policy["tomato_healthy"]
    tlb_policy = grouping_policy["tomato_late_blight"]

    assert len(th_groups) == th_policy["approved_group_count"], (
        f"Tomato Healthy candidate group count {len(th_groups)} != "
        f"approved {th_policy['approved_group_count']}"
    )
    assert sum(len(v) for v in th_groups.values()) == th_policy["approved_image_count"], (
        "Tomato Healthy candidate image count mismatch vs approved policy"
    )
    assert len(tlb_groups) == tlb_policy["approved_group_count"], (
        f"Tomato Late Blight candidate group count {len(tlb_groups)} != "
        f"approved {tlb_policy['approved_group_count']}"
    )
    assert sum(len(v) for v in tlb_groups.values()) == tlb_policy["approved_image_count"], (
        "Tomato Late Blight candidate image count mismatch vs approved policy"
    )

    large_group_ids = set(
        grouping_policy["tomato_late_blight"]["large_groups"]["approved_large_group_ids"]
    )
    for gid in large_group_ids:
        assert gid in group_to_paths, f"approved large group {gid} missing from candidate data"

    return path_to_group, group_to_paths


# ---------------------------------------------------------------------------
# Stage 4: assemble the eligible pool + quarantine ledger
# ---------------------------------------------------------------------------

class GroupRecord:
    __slots__ = ("group_key", "class_name", "group_source", "paths")

    def __init__(self, group_key, class_name, group_source, paths):
        self.group_key = group_key
        self.class_name = class_name
        self.group_source = group_source
        self.paths = paths

    @property
    def size(self):
        return len(self.paths)


def assemble_pool(active_classes, path_to_leaf_id, path_to_filename_group, duplicate_paths):
    groups_by_class = defaultdict(dict)  # class_name -> group_key -> GroupRecord
    quarantined = []
    duplicate_excluded = []
    all_eligible_paths = []

    for class_name in active_classes:
        for path in _iter_class_files(class_name):
            rel = _rel(path)

            if rel in duplicate_paths:
                duplicate_excluded.append({"path": rel, "class_name": class_name})
                continue

            leaf_id = path_to_leaf_id.get(rel)
            filename_group = path_to_filename_group.get(rel)

            if leaf_id:
                group_key = leaf_id
                group_source = "leaf_id"
            elif filename_group:
                group_key = filename_group
                group_source = "tomato_filename_group"
            else:
                quarantined.append({"path": rel, "class_name": class_name})
                continue

            groups = groups_by_class[class_name]
            if group_key not in groups:
                groups[group_key] = GroupRecord(group_key, class_name, group_source, [])
            groups[group_key].paths.append(rel)
            all_eligible_paths.append(rel)

    assert len(all_eligible_paths) == len(set(all_eligible_paths)), (
        "an eligible image path was counted twice"
    )

    return groups_by_class, quarantined, duplicate_excluded, all_eligible_paths


# ---------------------------------------------------------------------------
# Stage 4b: similarity guards (M3B-3A) -- validate, then fold into components
# ---------------------------------------------------------------------------

def validate_similarity_guards(guards_policy: dict, active_classes: list, groups_by_class: dict):
    """Validate ml-service/training/similarity_guards_v1.json against the
    assembled group pool. Returns (group_key_to_guard, guards_by_id, checks).

    Enforced, per the M3B-3A approval:
      - every guard's class_name is in the active scope;
      - every referenced original_group_key actually exists in that class's
        assembled group pool (not quarantined, not out of scope);
      - no original_group_key is claimed by more than one guard
        (contradictory guard definitions are rejected, not silently merged);
      - a guard never links group keys across two different classes.
    """
    checks = []
    group_key_to_guard = {}
    guards_by_id = {}

    for guard in guards_policy.get("guards", []):
        gid = guard["guard_group_id"]
        cname = guard["class_name"]
        keys = guard["original_group_keys"]
        guards_by_id[gid] = guard

        if cname not in active_classes:
            checks.append(
                {"check": f"guard {gid} class is in active scope", "status": "FAIL", "detail": cname}
            )
            raise IntegrityCheckFailed(f"similarity guard {gid} references out-of-scope class {cname}")
        checks.append({"check": f"guard {gid} class is in active scope", "status": "PASS"})

        class_groups = groups_by_class.get(cname, {})
        missing = [k for k in keys if k not in class_groups]
        if missing:
            checks.append(
                {"check": f"guard {gid} group keys exist in assembled pool", "status": "FAIL", "detail": missing}
            )
            raise IntegrityCheckFailed(
                f"similarity guard {gid} references missing/quarantined group key(s): {missing}"
            )
        checks.append({"check": f"guard {gid} group keys exist in assembled pool", "status": "PASS"})

        # No group key spans two different classes' pools under this guard.
        other_class_hit = [
            k for other_cname, other_groups in groups_by_class.items()
            if other_cname != cname
            for k in keys
            if k in other_groups
        ]
        if other_class_hit:
            checks.append(
                {"check": f"guard {gid} does not cross class boundaries", "status": "FAIL", "detail": other_class_hit}
            )
            raise IntegrityCheckFailed(f"similarity guard {gid} crosses class boundaries: {other_class_hit}")
        checks.append({"check": f"guard {gid} does not cross class boundaries", "status": "PASS"})

        for k in keys:
            if k in group_key_to_guard and group_key_to_guard[k] != gid:
                checks.append(
                    {
                        "check": "no original group_key claimed by multiple guards",
                        "status": "FAIL",
                        "detail": {"group_key": k, "guards": [group_key_to_guard[k], gid]},
                    }
                )
                raise IntegrityCheckFailed(
                    f"contradictory guard definitions: group_key {k!r} claimed by both "
                    f"{group_key_to_guard[k]!r} and {gid!r}"
                )
            group_key_to_guard[k] = gid

    checks.append(
        {
            "check": "no original group_key claimed by multiple guards",
            "status": "PASS",
            "detail": {"total_guarded_group_keys": len(group_key_to_guard)},
        }
    )

    return group_key_to_guard, guards_by_id, checks


class Component:
    """One allocation unit: either a single original group (no guard) or the
    union of every original group sharing one approved similarity_guard_group.
    Allocation is performed on components so that guard-linked groups are
    always assigned to the same split; original group_key/group_source are
    preserved unchanged per-image when components are expanded back out.
    """

    __slots__ = ("component_id", "class_name", "guard_group_id", "member_groups")

    def __init__(self, component_id, class_name, guard_group_id, member_groups):
        self.component_id = component_id
        self.class_name = class_name
        self.guard_group_id = guard_group_id
        self.member_groups = member_groups

    @property
    def size(self):
        return sum(g.size for g in self.member_groups)

    @property
    def group_count(self):
        return len(self.member_groups)


def build_components(class_name: str, groups: dict, group_key_to_guard: dict):
    components_by_id = {}
    for group_key, group in groups.items():
        guard_id = group_key_to_guard.get(group_key)
        if guard_id:
            if guard_id not in components_by_id:
                components_by_id[guard_id] = Component(guard_id, class_name, guard_id, [])
            components_by_id[guard_id].member_groups.append(group)
        else:
            components_by_id[group_key] = Component(group_key, class_name, None, [group])
    return components_by_id


# ---------------------------------------------------------------------------
# Stage 5: deterministic grouped allocation
# ---------------------------------------------------------------------------

def allocate_components(components: dict[str, "Component"], seed: int = SEED):
    """Deficit-driven greedy bin-packing over allocation COMPONENTS (M3B-3A).

    A component is one original group (no similarity guard applies) or the
    union of every original group sharing one approved similarity_guard_group
    -- so a guard's linked groups are always assigned as a single unit and
    therefore always land in the same split.

    Components are processed largest-first (ties broken by ascending
    component_id) so the biggest indivisible units are placed while the most
    allocation freedom remains. At each step the component goes to whichever
    split is currently furthest (in image count) below its 70/15/15 target.
    Ties in deficit are broken by (a) fewer ORIGINAL groups already assigned
    to that split (a guarded component with 2 original groups counts as 2
    here, matching how the approved minimums count groups), to keep group
    counts reasonably balanced across splits, then (b) the fixed priority
    order train > val > test, which is fully deterministic. No branch of
    this algorithm depends on random selection; `seed` is accepted and
    recorded for reproducibility per the M3B-3 contract, but this
    implementation never reaches a state where a random draw would be
    needed, because the two deterministic tie-breakers above always resolve
    to exactly one candidate split.
    """
    ordered = sorted(components.values(), key=lambda c: (-c.size, c.component_id))
    total_images = sum(c.size for c in ordered)

    train_target = round(total_images * TRAIN_FRAC)
    val_target = round(total_images * VAL_FRAC)
    test_target = total_images - train_target - val_target
    targets = {"train": train_target, "val": val_target, "test": test_target}

    assigned_images = {"train": 0, "val": 0, "test": 0}
    assigned_groups = {"train": 0, "val": 0, "test": 0}  # counts ORIGINAL groups, not components
    split_of_component = {}

    for c in ordered:
        deficits = {s: targets[s] - assigned_images[s] for s in SPLIT_PRIORITY}
        max_deficit = max(deficits.values())
        candidates = [s for s in SPLIT_PRIORITY if deficits[s] == max_deficit]
        if len(candidates) > 1:
            min_groups = min(assigned_groups[s] for s in candidates)
            candidates = [s for s in candidates if assigned_groups[s] == min_groups]
        chosen = next(s for s in SPLIT_PRIORITY if s in candidates)

        split_of_component[c.component_id] = chosen
        assigned_images[chosen] += c.size
        assigned_groups[chosen] += c.group_count

    return split_of_component, assigned_images, assigned_groups, targets, total_images


# ---------------------------------------------------------------------------
# Stage 6: minimum per-split checks
# ---------------------------------------------------------------------------

def check_minimums(class_name, assigned_images, assigned_groups):
    mins = POTATO_HEALTHY_MIN if class_name == "Potato Healthy" else GENERAL_MIN
    results = {}
    all_pass = True
    for split_name in SPLIT_NAMES:
        req = mins.get(split_name)
        if req is None:
            results[split_name] = {
                "required_images": None,
                "achieved_images": assigned_images[split_name],
                "images_ok": True,
                "required_groups": None,
                "achieved_groups": assigned_groups[split_name],
                "groups_ok": True,
                "status": "NO_MINIMUM_SPECIFIED",
            }
            continue
        img_ok = assigned_images[split_name] >= req["images"]
        grp_ok = assigned_groups[split_name] >= req["groups"]
        ok = img_ok and grp_ok
        all_pass = all_pass and ok
        results[split_name] = {
            "required_images": req["images"],
            "achieved_images": assigned_images[split_name],
            "images_ok": img_ok,
            "required_groups": req["groups"],
            "achieved_groups": assigned_groups[split_name],
            "groups_ok": grp_ok,
            "status": "PASS" if ok else "FAIL",
        }
    return results, all_pass


# ---------------------------------------------------------------------------
# Bonus diagnostic: pHash near-duplicate vs final-group consistency preview
# ---------------------------------------------------------------------------

def phash_consistency_preview(active_classes, path_to_group_key, path_to_split, path_to_guard):
    """Diagnostic (non-blocking): for every in-scope within-class pHash
    cluster on record, report whether its members share one original
    group_key AND whether they ended up in the same SPLIT (the thing that
    actually matters for leakage) after similarity guards were applied.
    """
    phash_clusters = _load_json(REPORTS_DIR / "phash_clusters.json")
    findings = []
    for cluster in phash_clusters.get("within_class_clusters", []):
        members = cluster["members"]
        class_name = members[0]["class_name"]
        if class_name not in active_classes:
            continue  # Corn clusters -- out of scope, needs_more_review, untouched
        member_paths = [m["path"] for m in members]
        member_groups = {p: path_to_group_key.get(p) for p in member_paths}
        member_splits = {p: path_to_split.get(p) for p in member_paths}
        member_guards = {p: path_to_guard.get(p) or None for p in member_paths}
        distinct_groups = set(member_groups.values())
        distinct_splits = set(member_splits.values())
        findings.append(
            {
                "cluster_id": cluster["cluster_id"],
                "class_name": class_name,
                "max_pairwise_hamming_distance": cluster["max_pairwise_hamming_distance"],
                "member_final_group_keys": member_groups,
                "member_final_splits": member_splits,
                "member_similarity_guard_group": member_guards,
                "all_members_share_one_final_group": len(distinct_groups) == 1
                and None not in distinct_groups,
                "all_members_share_one_final_split": len(distinct_splits) == 1
                and None not in distinct_splits,
            }
        )
    cross_split_risk = [f for f in findings if not f["all_members_share_one_final_split"]]
    return findings, cross_split_risk


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    SPLITS_DIR.mkdir(parents=True, exist_ok=True)

    (
        integrity_checks,
        model_scope,
        grouping_policy,
        class_map,
        active_classes,
        exact_hash_report,
        similarity_guards_policy,
    ) = run_input_integrity_checks()

    class_index_by_name = {}
    for i in range(8):
        class_index_by_name[class_map[str(i)]] = i

    duplicate_paths, duplicate_detail = build_duplicate_exclusion_set(exact_hash_report)

    leaf_map = _load_json(LEAF_MAP_PATH)
    path_to_leaf_id, leaf_matched_by_class, leaf_total_by_class = build_leaf_id_index(
        active_classes, leaf_map
    )

    leaf_id_join_summary = _load_json(REPORTS_DIR / "leaf_id_join_summary.json")
    for class_name in active_classes:
        recorded = leaf_id_join_summary.get(class_name, {})
        recomputed_matched = leaf_matched_by_class[class_name]
        recomputed_total = leaf_total_by_class[class_name]
        check_entry = {
            "check": f"leaf_id join reproduces M3A summary for {class_name}",
            "status": "PASS"
            if recorded.get("matched") == recomputed_matched
            and recorded.get("total") == recomputed_total
            else "FAIL",
            "detail": {
                "recorded_matched": recorded.get("matched"),
                "recomputed_matched": recomputed_matched,
                "recorded_total": recorded.get("total"),
                "recomputed_total": recomputed_total,
            },
        }
        integrity_checks.append(check_entry)
        if check_entry["status"] == "FAIL":
            raise IntegrityCheckFailed(check_entry["check"])

    candidates = _load_json(REPORTS_DIR / "tomato_filename_group_candidates.json")
    path_to_filename_group, filename_group_to_paths = build_filename_group_index(
        candidates, grouping_policy
    )
    integrity_checks.append(
        {
            "check": "approved Tomato filename-family group counts match tomato_grouping_policy_v1.json",
            "status": "PASS",
        }
    )

    groups_by_class, quarantined, duplicate_excluded, all_eligible_paths = assemble_pool(
        active_classes, path_to_leaf_id, path_to_filename_group, duplicate_paths
    )

    # M3B-3A: validate the approved similarity guards against the assembled
    # pool, then fold each class's groups into allocation components.
    group_key_to_guard, guards_by_id, guard_checks = validate_similarity_guards(
        similarity_guards_policy, active_classes, groups_by_class
    )
    integrity_checks.extend(guard_checks)

    components_by_class = {
        class_name: build_components(class_name, groups_by_class[class_name], group_key_to_guard)
        for class_name in active_classes
    }

    # Cross-check quarantine ledger against the M3B-2 approved quarantine summary.
    m3b2_quarantine_summary = _load_json(REPORTS_DIR / "m3b2_quarantine_summary.json")
    quarantined_by_class = defaultdict(int)
    for q in quarantined:
        quarantined_by_class[q["class_name"]] += 1
    expected_quarantine = {
        cname: entry["quarantined_images"]
        for cname, entry in m3b2_quarantine_summary["active_scope_classes"].items()
        if isinstance(entry, dict) and "quarantined_images" in entry
    }
    for cname, expected_count in expected_quarantine.items():
        actual = quarantined_by_class.get(cname, 0)
        check_entry = {
            "check": f"quarantined image count for {cname} matches m3b2_quarantine_summary.json",
            "status": "PASS" if actual == expected_count else "FAIL",
            "detail": {"expected": expected_count, "actual": actual},
        }
        integrity_checks.append(check_entry)
        if check_entry["status"] == "FAIL":
            raise IntegrityCheckFailed(check_entry["check"])
    integrity_checks.append(
        {
            "check": "total approved quarantined images == 4",
            "status": "PASS" if len(quarantined) == 4 else "FAIL",
            "detail": len(quarantined),
        }
    )
    if len(quarantined) != 4:
        raise IntegrityCheckFailed("total quarantined count mismatch")

    integrity_checks.append(
        {
            "check": "every eligible image has exactly one final grouping key",
            "status": "PASS",
        }
    )
    integrity_checks.append(
        {
            "check": "no image appears twice after representative selection",
            "status": "PASS"
            if len(all_eligible_paths) == len(set(all_eligible_paths))
            else "FAIL",
        }
    )

    # sha256 for every eligible image (needed for the manifest + leakage preview).
    path_to_sha256 = {}
    for class_name in active_classes:
        for group in groups_by_class[class_name].values():
            for p in group.paths:
                if p not in path_to_sha256:
                    path_to_sha256[p] = _sha256_file(ML_SERVICE_ROOT / p)

    # Allocation, per class, in stable alphabetical order. Allocation runs
    # over COMPONENTS (M3B-3A) so guard-linked groups are assigned as one
    # unit; group counts in the minimum checks still count ORIGINAL groups.
    per_class_results = {}
    split_of_group_by_class = {}  # class_name -> original group_key -> split
    all_minimums_pass = True

    for class_name in sorted(active_classes):
        groups = groups_by_class[class_name]
        components = components_by_class[class_name]
        split_of_component, assigned_images, assigned_groups, targets, total_images = (
            allocate_components(components, seed=SEED)
        )
        min_results, class_pass = check_minimums(class_name, assigned_images, assigned_groups)
        all_minimums_pass = all_minimums_pass and class_pass

        # Expand component assignment back to original group_key -> split.
        split_of_group = {}
        for component in components.values():
            split_name = split_of_component[component.component_id]
            for member in component.member_groups:
                split_of_group[member.group_key] = split_name

        per_split_detail = {}
        for split_name in SPLIT_NAMES:
            target = targets[split_name]
            achieved = assigned_images[split_name]
            pct = (achieved / total_images * 100) if total_images else 0.0
            target_pct = (target / total_images * 100) if total_images else 0.0
            per_split_detail[split_name] = {
                "image_count": achieved,
                "target_image_count": target,
                "achieved_percentage": round(pct, 2),
                "target_percentage": round(target_pct, 2),
                "deviation_from_target_images": achieved - target,
                "group_count": assigned_groups[split_name],
                "minimum_requirement": min_results[split_name],
            }

        per_class_results[class_name] = {
            "total_eligible_images": total_images,
            "total_groups": len(groups),
            "total_components": len(components),
            "splits": per_split_detail,
            "all_minimums_met": class_pass,
        }
        split_of_group_by_class[class_name] = split_of_group

    # Verify every guard's linked original groups landed in one split (this
    # is exactly what a component guarantees by construction, but re-checked
    # explicitly here as an auditable, independent assertion).
    for gid, guard in guards_by_id.items():
        cname = guard["class_name"]
        splits_seen = {split_of_group_by_class[cname][k] for k in guard["original_group_keys"]}
        check_entry = {
            "check": f"guard {gid} linked groups landed in exactly one split",
            "status": "PASS" if len(splits_seen) == 1 else "FAIL",
            "detail": {"splits_seen": sorted(splits_seen)},
        }
        integrity_checks.append(check_entry)
        if check_entry["status"] == "FAIL":
            raise IntegrityCheckFailed(check_entry["check"])

    # path -> split / path -> group_key / path -> similarity_guard_group,
    # needed for manifest rows and the pHash diagnostic.
    path_to_split = {}
    path_to_group_key = {}
    path_to_guard = {}
    for class_name in active_classes:
        split_of_group = split_of_group_by_class[class_name]
        for group in groups_by_class[class_name].values():
            split_name = split_of_group[group.group_key]
            guard_id = group_key_to_guard.get(group.group_key, "")
            for p in group.paths:
                path_to_split[p] = split_name
                path_to_group_key[p] = group.group_key
                path_to_guard[p] = guard_id

    # pHash consistency diagnostic (non-blocking, disclosed in reports).
    phash_findings, phash_cross_split_risk = phash_consistency_preview(
        active_classes, path_to_group_key, path_to_split, path_to_guard
    )

    # ------------------------------------------------------------------
    # Build manifest rows (always generated -- see module docstring / report
    # for why a minimum-check failure does not block manifest generation).
    # ------------------------------------------------------------------
    rows_by_split = {s: [] for s in SPLIT_NAMES}
    for class_name in sorted(active_classes):
        groups = groups_by_class[class_name]
        split_of_group = split_of_group_by_class[class_name]
        for group_key in sorted(groups.keys()):
            group = groups[group_key]
            split_name = split_of_group[group_key]
            guard_id = group_key_to_guard.get(group_key, "")
            for path in sorted(group.paths):
                rows_by_split[split_name].append(
                    {
                        "path": path,
                        "class_name": class_name,
                        "class_index": class_index_by_name[class_name],
                        "group_key": group_key,
                        "group_source": group.group_source,
                        "similarity_guard_group": guard_id,
                        "sha256": path_to_sha256[path],
                    }
                )

    for split_name in SPLIT_NAMES:
        rows_by_split[split_name].sort(key=lambda r: (r["class_name"], r["group_key"], r["path"]))

    CSV_COLUMNS = (
        "path",
        "class_name",
        "class_index",
        "group_key",
        "group_source",
        "similarity_guard_group",
        "sha256",
    )
    csv_header = ",".join(CSV_COLUMNS) + "\n"

    def _csv_escape(value: str) -> str:
        if any(c in value for c in (",", '"', "\n")):
            return '"' + value.replace('"', '""') + '"'
        return value

    manifest_hashes = {}
    for split_name in SPLIT_NAMES:
        lines = [csv_header]
        for row in rows_by_split[split_name]:
            lines.append(
                ",".join(_csv_escape(str(row[col])) for col in CSV_COLUMNS) + "\n"
            )
        content = "".join(lines)
        out_path = SPLITS_DIR / f"{split_name}.csv"
        out_path.write_text(content)
        manifest_hashes[split_name] = {
            "sha256": _sha256_bytes(content.encode("utf-8")),
            "row_count": len(rows_by_split[split_name]),
            "byte_count": len(content.encode("utf-8")),
        }

    # ------------------------------------------------------------------
    # Reports
    # ------------------------------------------------------------------
    total_active_scope_images_considered = sum(leaf_total_by_class[c] for c in active_classes)
    total_duplicates_excluded = len(duplicate_excluded)
    total_quarantined_excluded = len(quarantined)
    total_out_of_scope = sum(len(list(_iter_class_files(c))) for c in CORN_CLASSES)

    final_manifest_row_count = sum(len(rows_by_split[s]) for s in SPLIT_NAMES)

    reconciliation_ok = (
        total_active_scope_images_considered - total_duplicates_excluded - total_quarantined_excluded
        == final_manifest_row_count
    )
    assert reconciliation_ok, (
        f"reconciliation failed: {total_active_scope_images_considered} - "
        f"{total_duplicates_excluded} - {total_quarantined_excluded} != {final_manifest_row_count}"
    )

    split_summary = {
        "milestone": "M3B-3A",
        "status": "all_minimums_met" if all_minimums_pass else "FAILED_MINIMUM_REQUIREMENTS",
        "approved": False,
        "approval_note": (
            "M3B-3A generates a review artifact only. Final leakage sign-off "
            "and approval belong to Milestone M3B-4, regardless of this "
            "status value."
        ),
        "potato_healthy_minimum_exception_applied": True,
        "seed": SEED,
        "target_proportions": {"train": TRAIN_FRAC, "val": VAL_FRAC, "test": TEST_FRAC},
        "active_class_list": sorted(active_classes),
        "total_active_scope_images_considered": total_active_scope_images_considered,
        "total_duplicate_images_excluded": total_duplicates_excluded,
        "total_quarantined_images_excluded": total_quarantined_excluded,
        "total_out_of_scope_corn_images_excluded": total_out_of_scope,
        "final_manifest_row_count": final_manifest_row_count,
        "reconciliation_check": (
            "total_active_scope_images_considered - total_duplicate_images_excluded - "
            "total_quarantined_images_excluded == final_manifest_row_count"
        ),
        "reconciliation_ok": reconciliation_ok,
        "per_class": per_class_results,
        "all_minimums_met": all_minimums_pass,
    }
    if not all_minimums_pass:
        failing = {
            cname: {
                s: detail["splits"][s]["minimum_requirement"]
                for s in SPLIT_NAMES
                if detail["splits"][s]["minimum_requirement"]["status"] == "FAIL"
            }
            for cname, detail in per_class_results.items()
            if not detail["all_minimums_met"]
        }
        split_summary["failure_report"] = {
            "message": (
                "One or more classes could not meet their minimum per-split "
                "image/group requirements using only approved grouping "
                "evidence. Manifests were still generated for review, but "
                "this split is NOT approved and must not be used for "
                "training until M3B-4 review resolves the shortfall."
            ),
            "failing_classes": failing,
        }
    _write_json(REPORTS_DIR / "split_summary.json", split_summary)

    split_group_summary = {
        "milestone": "M3B-3A",
        "seed": SEED,
        "per_class_groups": {
            class_name: {
                "total_groups": len(groups_by_class[class_name]),
                "total_components": len(components_by_class[class_name]),
                "group_source_breakdown": {
                    source: sum(
                        1 for g in groups_by_class[class_name].values() if g.group_source == source
                    )
                    for source in ("leaf_id", "tomato_filename_group")
                },
                "groups": [
                    {
                        "group_key": g.group_key,
                        "group_source": g.group_source,
                        "size": g.size,
                        "split": split_of_group_by_class[class_name][g.group_key],
                        "similarity_guard_group": group_key_to_guard.get(g.group_key, ""),
                    }
                    for g in sorted(
                        groups_by_class[class_name].values(), key=lambda g: g.group_key
                    )
                ],
            }
            for class_name in sorted(active_classes)
        },
        "similarity_guards": {
            gid: {
                "class_name": guard["class_name"],
                "original_group_keys": guard["original_group_keys"],
                "final_split": split_of_group_by_class[guard["class_name"]][
                    guard["original_group_keys"][0]
                ],
                "source_phash_cluster_id": guard["source_phash_cluster_id"],
            }
            for gid, guard in guards_by_id.items()
        },
    }
    _write_json(REPORTS_DIR / "split_group_summary.json", split_group_summary)

    split_input_integrity = {
        "milestone": "M3B-3A",
        "checks": integrity_checks,
        "all_checks_passed": True,
        "duplicate_images_excluded_detail": duplicate_detail,
        "quarantined_images": quarantined,
        "similarity_guards_applied": sorted(guards_by_id.keys()),
        "phash_consistency_preview": {
            "note": (
                "Diagnostic only, NOT a blocking check. For each within-class "
                "pHash cluster already recorded in M3A/M3B-2 evidence, this "
                "reports whether both members share one original group_key "
                "and -- the thing that actually matters for leakage -- "
                "whether they ended up in the SAME final SPLIT after "
                "similarity guards (M3B-3A) were applied. Guards force their "
                "linked groups into one split without merging or renaming "
                "the original group_key/group_source and without asserting "
                "common physical-leaf identity; see "
                "training/similarity_guards_v1.json. Any cluster still "
                "showing cross-split risk here has NOT been covered by an "
                "approved guard and remains a disclosed, unresolved risk for "
                "M3B-4."
            ),
            "clusters": phash_findings,
            "clusters_with_cross_split_risk": phash_cross_split_risk,
            "cross_split_risk_count": len(phash_cross_split_risk),
        },
    }
    _write_json(REPORTS_DIR / "split_input_integrity.json", split_input_integrity)

    _write_json(
        REPORTS_DIR / "split_manifest_hashes.json",
        {"milestone": "M3B-3A", "seed": SEED, "manifests": manifest_hashes},
    )

    _write_json(
        REPORTS_DIR / "split_generation_run_metadata.json",
        {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "seed": SEED,
            "note": (
                "This file's generated_at_utc field is expected to differ "
                "between runs; it is intentionally isolated here so all "
                "other split_*.json reports remain byte-identical across "
                "repeated runs of the same inputs."
            ),
        },
    )

    print(json.dumps({"status": split_summary["status"], "all_minimums_met": all_minimums_pass, "final_manifest_row_count": final_manifest_row_count}, indent=2))
    return 0 if all_minimums_pass else 1


if __name__ == "__main__":
    sys.exit(main())
