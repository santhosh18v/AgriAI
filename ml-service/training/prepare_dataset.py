"""Dataset preparation pipeline — discovery/reporting stages (Milestone M3A).

Milestone boundary: this script currently implements only the discovery and
reporting stages approved for M3A:
  1. source validation
  2. class-map validation
  3. global SHA-256 analysis (exact-duplicate + cross-class conflict detection)
  4. global pHash candidate analysis (near-duplicate detection, review-only)
  5. leaf-map.json join
  6. unmatched-image and quarantine analysis

It deliberately does NOT generate train/validation/test split manifests.
Split generation (Stage 5) is scoped to a later milestone (M3B) and requires
a human-reviewed `approved_phash_groups.json` to resolve any unmatched
images into groups — that file does not exist yet, and this script does not
fabricate one. Every image without a leaf_id match is quarantined by
default.

All paths below assume the sparse-checked-out upstream repo lives at
ml-service/data/raw/plantvillage-source, preserving its original layout
(see ml-service/docs/DATASET_PROVENANCE.md for exact fetch provenance).

Note on splits/: the upstream GitHub repository at the approved commit does
NOT contain a splits/ directory (color_train.txt / color_test.txt only
exist on a separate, unapproved secondary mirror and are intentionally not
fetched here). This is expected and acceptable — Milestone M3B builds our
own deterministic 70/15/15 grouped split directly from the fetched color
images and leaf-map.json, so no upstream split manifest is required.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
SOURCE_ROOT = ML_SERVICE_ROOT / "data" / "raw" / "plantvillage-source"
COLOR_ROOT = SOURCE_ROOT / "raw" / "color"
LEAF_MAP_PATH = SOURCE_ROOT / "leaf-map.json"
CLASS_MAP_PATH = ML_SERVICE_ROOT / "training" / "class_map.json"
REPORTS_DIR = ML_SERVICE_ROOT / "data" / "reports"
APPROVED_PHASH_GROUPS_PATH = REPORTS_DIR / "approved_phash_groups.json"

# Source-folder -> internal class name (order matches training/class_map.json).
CLASS_FOLDER_MAP = {
    "Tomato___healthy": "Tomato Healthy",
    "Tomato___Early_blight": "Tomato Early Blight",
    "Tomato___Late_blight": "Tomato Late Blight",
    "Potato___healthy": "Potato Healthy",
    "Potato___Early_blight": "Potato Early Blight",
    "Potato___Late_blight": "Potato Late Blight",
    "Corn_(maize)___healthy": "Corn Healthy",
    "Corn_(maize)___Common_rust_": "Corn Common Rust",
}

UUID_PREFIX_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}___"
)

PHASH_HAMMING_THRESHOLD = 5


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)


def _iter_class_images():
    """Yield (path, class_folder, class_name) for every image, in stable
    (sorted) order — required for deterministic downstream processing."""
    for folder in sorted(CLASS_FOLDER_MAP):
        class_dir = COLOR_ROOT / folder
        for path in sorted(class_dir.glob("*")):
            if path.is_file():
                yield path, folder, CLASS_FOLDER_MAP[folder]


# ---------------------------------------------------------------------------
# Stage 1: source validation
# ---------------------------------------------------------------------------

def stage_source_validation() -> dict:
    result = {
        "class_folders": {},
        "metadata_files": {},
        "ok": True,
        "note": (
            "The upstream GitHub repository does not contain a splits/ "
            "directory at the approved commit; no split-manifest "
            "cross-check is performed here. Milestone M3B builds our own "
            "deterministic split from these images and leaf-map.json."
        ),
    }

    for folder in sorted(CLASS_FOLDER_MAP):
        class_dir = COLOR_ROOT / folder
        exists = class_dir.is_dir()
        count = len(list(class_dir.glob("*"))) if exists else 0
        entry = {"exists": exists, "file_count": count}
        result["class_folders"][folder] = entry
        if not exists or count == 0:
            result["ok"] = False

    for name, path in (
        ("leaf-map.json", LEAF_MAP_PATH),
        ("README.md", SOURCE_ROOT / "README.md"),
        ("CITATION.cff", SOURCE_ROOT / "CITATION.cff"),
    ):
        exists = path.exists()
        result["metadata_files"][name] = {
            "exists": exists,
            "size_bytes": path.stat().st_size if exists else None,
        }
        if not exists:
            result["ok"] = False

    return result


# ---------------------------------------------------------------------------
# Stage 2: class-map validation
# ---------------------------------------------------------------------------

def stage_class_map_validation() -> dict:
    result = {"ok": True, "issues": []}
    if not CLASS_MAP_PATH.exists():
        return {"ok": False, "issues": ["training/class_map.json does not exist"]}

    with open(CLASS_MAP_PATH) as f:
        class_map = json.load(f)

    expected_names = list(CLASS_FOLDER_MAP.values())
    actual_names = [class_map.get(str(i)) for i in range(len(expected_names))]

    if len(class_map) != 8:
        result["ok"] = False
        result["issues"].append(f"expected 8 classes, found {len(class_map)}")
    if actual_names != expected_names:
        result["ok"] = False
        result["issues"].append(
            f"class_map.json order/content mismatch: expected {expected_names}, got {actual_names}"
        )

    result["expected_classes"] = expected_names
    result["class_map_classes"] = actual_names
    return result


# ---------------------------------------------------------------------------
# Stage 3: global SHA-256 exact-hash analysis
# ---------------------------------------------------------------------------

def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stage_global_sha256():
    """Returns (hash_to_entries, exact_hash_report)."""
    hash_to_entries: dict[str, list[dict]] = defaultdict(list)

    for path, folder, class_name in _iter_class_images():
        digest = _sha256_file(path)
        hash_to_entries[digest].append(
            {
                "path": str(path.relative_to(ML_SERVICE_ROOT)),
                "class_folder": folder,
                "class_name": class_name,
            }
        )

    same_class_duplicate_groups = []
    cross_class_conflict_groups = []
    representative_path_by_hash: dict[str, str] = {}

    for digest, entries in sorted(hash_to_entries.items()):
        entries_sorted = sorted(entries, key=lambda e: e["path"])
        representative_path_by_hash[digest] = entries_sorted[0]["path"]
        classes = {e["class_name"] for e in entries_sorted}
        if len(entries_sorted) == 1:
            continue
        if len(classes) == 1:
            same_class_duplicate_groups.append(
                {
                    "sha256": digest,
                    "representative": entries_sorted[0]["path"],
                    "duplicates": [e["path"] for e in entries_sorted[1:]],
                    "class_name": entries_sorted[0]["class_name"],
                }
            )
        else:
            cross_class_conflict_groups.append(
                {"sha256": digest, "members": entries_sorted}
            )

    report = {
        "total_images_hashed": sum(len(v) for v in hash_to_entries.values()),
        "unique_hashes": len(hash_to_entries),
        "same_class_duplicate_group_count": len(same_class_duplicate_groups),
        "same_class_duplicate_image_count": sum(
            len(g["duplicates"]) for g in same_class_duplicate_groups
        ),
        "cross_class_conflict_group_count": len(cross_class_conflict_groups),
        "cross_class_conflict_image_count": sum(
            len(g["members"]) for g in cross_class_conflict_groups
        ),
        "same_class_duplicate_groups": same_class_duplicate_groups,
        "cross_class_conflict_groups": cross_class_conflict_groups,
    }
    return hash_to_entries, representative_path_by_hash, report


# ---------------------------------------------------------------------------
# Stage 4: global pHash candidate analysis
# ---------------------------------------------------------------------------

def stage_phash_analysis(representative_path_by_hash: dict[str, str]):
    import imagehash
    import numpy as np
    from PIL import Image

    # One phash per unique SHA-256 (exact duplicates share identical bytes,
    # hence identical phash — no need to recompute per duplicate copy).
    paths = [
        (digest, ML_SERVICE_ROOT / rel)
        for digest, rel in sorted(representative_path_by_hash.items(), key=lambda kv: kv[1])
    ]

    hashes_int = []
    meta = []  # (path_str, class_name)
    class_by_rel = {}
    for path, folder, class_name in _iter_class_images():
        class_by_rel[str(path.relative_to(ML_SERVICE_ROOT))] = class_name

    for digest, abs_path in paths:
        rel = str(abs_path.relative_to(ML_SERVICE_ROOT))
        with Image.open(abs_path) as img:
            h = imagehash.phash(img)
        # imagehash hash -> 64-bit int
        bits = h.hash.flatten()
        as_int = 0
        for bit in bits:
            as_int = (as_int << 1) | int(bit)
        hashes_int.append(as_int)
        meta.append((rel, class_by_rel[rel]))

    n = len(hashes_int)
    arr = np.array(hashes_int, dtype=np.uint64)

    candidate_pairs = []
    chunk = 500
    for start in range(0, n, chunk):
        end = min(start + chunk, n)
        block = arr[start:end]
        xor = block[:, None] ^ arr[None, :]
        dist = np.bitwise_count(xor)
        for i_local in range(end - start):
            i = start + i_local
            row = dist[i_local]
            js = np.nonzero((row <= PHASH_HAMMING_THRESHOLD) & (np.arange(n) > i))[0]
            for j in js:
                candidate_pairs.append((i, int(j), int(row[j])))

    # Union-find clustering over candidate pairs.
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i, j, _ in candidate_pairs:
        union(i, j)

    clusters_by_root: dict[int, list[int]] = defaultdict(list)
    for idx in range(n):
        clusters_by_root[find(idx)].append(idx)

    pair_dist_lookup = {}
    for i, j, d in candidate_pairs:
        pair_dist_lookup[(i, j)] = d
        pair_dist_lookup[(j, i)] = d

    within_class_clusters = []
    cross_class_clusters = []
    for root, members in clusters_by_root.items():
        if len(members) < 2:
            continue
        member_info = [{"path": meta[m][0], "class_name": meta[m][1]} for m in members]
        classes = {meta[m][1] for m in members}
        # Explicit all-pairs max distance within the cluster, not just the
        # linkage edges that connected it via union-find — chained
        # transitivity can hide a large end-to-end distance.
        max_pairwise = 0
        pairwise_within_cluster = []
        for a_idx in range(len(members)):
            for b_idx in range(a_idx + 1, len(members)):
                a, b = members[a_idx], members[b_idx]
                d = pair_dist_lookup.get((a, b))
                if d is None:
                    d = int(bin(hashes_int[a] ^ hashes_int[b]).count("1"))
                pairwise_within_cluster.append(
                    {"a": meta[a][0], "b": meta[b][0], "hamming_distance": d}
                )
                max_pairwise = max(max_pairwise, d)

        cluster_entry = {
            "cluster_id": f"phash-{root}",
            "member_count": len(members),
            "members": member_info,
            "max_pairwise_hamming_distance": max_pairwise,
            "pairwise_distances": pairwise_within_cluster,
            "requires_human_approval": True,
        }
        if len(classes) == 1:
            within_class_clusters.append(cluster_entry)
        else:
            cross_class_clusters.append(cluster_entry)

    candidate_pairs_report = [
        {
            "a": meta[i][0],
            "a_class": meta[i][1],
            "b": meta[j][0],
            "b_class": meta[j][1],
            "hamming_distance": d,
            "cross_class": meta[i][1] != meta[j][1],
        }
        for i, j, d in candidate_pairs
    ]

    report = {
        "hamming_threshold": PHASH_HAMMING_THRESHOLD,
        "unique_images_compared": n,
        "candidate_pair_count": len(candidate_pairs),
        "within_class_cluster_count": len(within_class_clusters),
        "within_class_candidate_image_count": sum(
            c["member_count"] for c in within_class_clusters
        ),
        "cross_class_cluster_count": len(cross_class_clusters),
        "cross_class_candidate_image_count": sum(
            c["member_count"] for c in cross_class_clusters
        ),
        "note": (
            "Cluster membership is derived from transitive (union-find) "
            "connectivity of pairwise candidates below the threshold. "
            "max_pairwise_hamming_distance is computed over ALL member "
            "pairs, not just the linkage edges — a high value here means "
            "the cluster may be a weakly-connected chain, not a tight "
            "group, and should be scrutinized during human review. No "
            "cluster is used as a grouping key without explicit human "
            "approval recorded in approved_phash_groups.json."
        ),
    }
    return meta, within_class_clusters, cross_class_clusters, candidate_pairs_report, report


# ---------------------------------------------------------------------------
# Stage 5: leaf-map.json join
# ---------------------------------------------------------------------------

def _normalize_for_leaf_map(filename_no_ext: str) -> str:
    stripped = UUID_PREFIX_RE.sub("", filename_no_ext)
    return stripped.lower().strip()


def stage_leaf_id_join(leaf_map: dict):
    per_image = []
    per_class_stats = defaultdict(lambda: {"total": 0, "matched": 0, "unmatched": 0})

    for path, folder, class_name in _iter_class_images():
        rel = str(path.relative_to(ML_SERVICE_ROOT))
        stem = path.stem
        key = _normalize_for_leaf_map(stem)
        leaf_ids = leaf_map.get(key)

        matched_leaf_id = None
        if leaf_ids:
            for candidate in leaf_ids:
                if candidate.startswith(folder + ":::"):
                    matched_leaf_id = candidate
                    break

        per_class_stats[class_name]["total"] += 1
        if matched_leaf_id:
            per_class_stats[class_name]["matched"] += 1
        else:
            per_class_stats[class_name]["unmatched"] += 1

        per_image.append(
            {
                "path": rel,
                "class_name": class_name,
                "normalized_key": key,
                "leaf_id": matched_leaf_id,
            }
        )

    summary = {}
    for class_name, stats in sorted(per_class_stats.items()):
        pct = (stats["matched"] / stats["total"] * 100) if stats["total"] else 0.0
        summary[class_name] = {
            "total": stats["total"],
            "matched": stats["matched"],
            "matched_pct": round(pct, 2),
            "unmatched": stats["unmatched"],
        }

    return per_image, summary


# ---------------------------------------------------------------------------
# Stage 6: unmatched-image and quarantine analysis
# ---------------------------------------------------------------------------

def stage_quarantine_analysis(
    per_image_leaf_id,
    within_class_clusters,
    cross_class_conflict_groups_exact,
    cross_class_clusters_phash,
):
    approved_cluster_ids = set()
    if APPROVED_PHASH_GROUPS_PATH.exists():
        with open(APPROVED_PHASH_GROUPS_PATH) as f:
            approved_cluster_ids = set(json.load(f).get("approved_cluster_ids", []))

    path_to_cluster = {}
    for cluster in within_class_clusters:
        for m in cluster["members"]:
            path_to_cluster[m["path"]] = cluster["cluster_id"]

    cross_class_exact_paths = {
        m["path"] for g in cross_class_conflict_groups_exact for m in g["members"]
    }
    cross_class_phash_paths = {
        m["path"] for c in cross_class_clusters_phash for m in c["members"]
    }

    quarantined = []
    resolved_via_reviewed_cluster = []

    for entry in per_image_leaf_id:
        path = entry["path"]
        reasons = []
        if path in cross_class_exact_paths:
            reasons.append("cross_class_exact_hash_conflict")
        if path in cross_class_phash_paths:
            reasons.append("cross_class_phash_conflict")

        if entry["leaf_id"]:
            group_source = "leaf_id"
        else:
            cluster_id = path_to_cluster.get(path)
            if cluster_id and cluster_id in approved_cluster_ids:
                group_source = "reviewed_phash_cluster"
                resolved_via_reviewed_cluster.append(path)
            else:
                group_source = None
                reasons.append("no_leaf_id_match_and_no_approved_cluster")

        if group_source is None or reasons:
            quarantined.append(
                {"path": path, "class_name": entry["class_name"], "reasons": reasons or ["no_leaf_id_match_and_no_approved_cluster"]}
            )

    quarantine_by_class = defaultdict(int)
    for q in quarantined:
        quarantine_by_class[q["class_name"]] += 1

    report = {
        "approved_phash_groups_file_present": APPROVED_PHASH_GROUPS_PATH.exists(),
        "approved_cluster_id_count": len(approved_cluster_ids),
        "resolved_via_reviewed_cluster_count": len(resolved_via_reviewed_cluster),
        "quarantined_total": len(quarantined),
        "quarantined_by_class": dict(sorted(quarantine_by_class.items())),
        "quarantined_images": quarantined,
    }
    return report


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _agriai_repo_commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ML_SERVICE_ROOT.parent,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except Exception:
        return None


def run_discovery_pipeline() -> dict:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    source_validation = stage_source_validation()
    _write_json(REPORTS_DIR / "source_validation.json", source_validation)

    class_map_validation = stage_class_map_validation()
    _write_json(REPORTS_DIR / "class_map_validation.json", class_map_validation)

    hash_to_entries, representative_path_by_hash, exact_hash_report = stage_global_sha256()
    _write_json(REPORTS_DIR / "exact_hash_report.json", exact_hash_report)

    (
        phash_meta,
        within_class_clusters,
        cross_class_clusters,
        candidate_pairs_report,
        phash_summary,
    ) = stage_phash_analysis(representative_path_by_hash)
    _write_json(REPORTS_DIR / "phash_candidate_pairs.json", candidate_pairs_report)
    _write_json(
        REPORTS_DIR / "phash_clusters.json",
        {
            "within_class_clusters": within_class_clusters,
            "cross_class_clusters": cross_class_clusters,
        },
    )
    _write_json(REPORTS_DIR / "phash_summary.json", phash_summary)

    with open(LEAF_MAP_PATH) as f:
        leaf_map = json.load(f)
    per_image_leaf_id, leaf_id_summary = stage_leaf_id_join(leaf_map)
    _write_json(REPORTS_DIR / "leaf_id_join_summary.json", leaf_id_summary)
    _write_json(
        REPORTS_DIR / "unmatched_images.json",
        [e for e in per_image_leaf_id if not e["leaf_id"]],
    )

    quarantine_report = stage_quarantine_analysis(
        per_image_leaf_id,
        within_class_clusters,
        exact_hash_report["cross_class_conflict_groups"],
        cross_class_clusters,
    )
    _write_json(REPORTS_DIR / "quarantine_report.json", quarantine_report)

    leaf_map_sha256 = _sha256_file(LEAF_MAP_PATH)

    import imagehash
    import numpy
    import scipy
    from PIL import Image as _PILImage

    dependency_versions = {
        "python": sys.version.split()[0],
        "pillow": _PILImage.__version__ if hasattr(_PILImage, "__version__") else __import__("PIL").__version__,
        "imagehash": imagehash.__version__,
        "numpy": numpy.__version__,
        "scipy": scipy.__version__,
    }

    # Deterministic, analysis-identity facts only. Volatile per-run values
    # (wall-clock timestamps) are written to run_metadata.json instead, so
    # this file is expected to be byte-identical across repeated runs of
    # the same source commit + config + dependency versions.
    source_integrity = {
        "upstream_repository_url": "https://github.com/spMohanty/PlantVillage-Dataset",
        "upstream_default_branch": "master",
        "upstream_commit_sha": "7f7ecc7e1eaca78107e3affe7cb5abd9427e139a",
        "splits_directory_status": (
            "The upstream repository at this commit does NOT contain a "
            "splits/ directory (no color_train.txt / color_test.txt). "
            "This was confirmed via `git ls-tree -r HEAD -- splits` "
            "returning empty. These files were NOT fetched from any "
            "secondary source (Hugging Face, Kaggle, Zenodo). Milestone "
            "M3B generates our own deterministic 70/15/15 grouped split "
            "directly from the fetched images and leaf-map.json instead."
        ),
        "class_folder_mapping": CLASS_FOLDER_MAP,
        "licence": "Treated as CC BY-SA 3.0 per the AIcrowd/crowdAI challenge's explicit statement that trained algorithms fall under the same licence (see ml-service/docs/DATASET_PROVENANCE.md). Private training, academic evaluation, and internal AgriAI demonstrations only. No dataset images or trained weights may be committed/published during Phase 2.",
        "leaf_map_json_sha256": leaf_map_sha256,
        "prepare_dataset_script_version": "0.1.0-m3a-discovery",
        "discovery_dependency_versions": dependency_versions,
    }
    _write_json(REPORTS_DIR / "source_integrity.json", source_integrity)

    # Volatile per-run metadata — deliberately separated from
    # source_integrity.json so the latter stays byte-identical across runs.
    run_metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "agriai_repo_commit_at_run_time": _agriai_repo_commit(),
        "note": "This file's generated_at_utc field is expected to differ between runs; it is intentionally kept separate from source_integrity.json so that file remains deterministic.",
    }
    _write_json(REPORTS_DIR / "run_metadata.json", run_metadata)

    return {
        "source_validation": source_validation,
        "class_map_validation": class_map_validation,
        "exact_hash_report": exact_hash_report,
        "phash_summary": phash_summary,
        "leaf_id_summary": leaf_id_summary,
        "quarantine_report": quarantine_report,
        "source_integrity": source_integrity,
        "run_metadata": run_metadata,
    }


if __name__ == "__main__":
    summary = run_discovery_pipeline()
    print(json.dumps({k: v for k, v in summary.items() if k != "quarantine_report"}, indent=2)[:2000])
    print("\n(Full detail written to ml-service/data/reports/*.json)")
