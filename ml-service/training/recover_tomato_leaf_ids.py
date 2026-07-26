"""Milestone M3B-1: authoritative Tomato leaf-ID recovery investigation.

Attempts to recover leaf_id matches for the 1,582 Tomato images that Stage
5 of prepare_dataset.py (M3A) left unmatched, by reproducing the upstream
aggregate_map.py normalization exactly (ported to Python 3; the original is
Python 2, unrunnable as-is) against three filtered_leafmaps CSVs that were
NOT fetched during M3A: Tomato___healthy.csv, Tomato___Early_blight.csv,
Tomato___Late_blight.csv.

Read-only with respect to M3A: never writes to, imports the write-path of,
or otherwise modifies any file under ml-service/data/reports/ produced by
prepare_dataset.py. It reads unmatched_images.json (an M3A output) as an
input list, and writes only new, M3B-1-specific report files.

Does NOT assign reviewed_filename_family, singleton groups, pHash groups,
or any inferred (non-authoritative) leaf IDs — those are explicitly out of
scope for M3B-1 and belong to a later, human-reviewed M3B-2 step, per the
approved M3B plan. Only exact/normalized matches against real upstream
leaf-count rows are ever recorded as recovered.
"""

from __future__ import annotations

import csv
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
FILTERED_LEAFMAPS_DIR = SOURCE_ROOT / "leaf_grouping" / "filtered_leafmaps"
REPORTS_DIR = ML_SERVICE_ROOT / "data" / "reports"
UNMATCHED_IMAGES_PATH = REPORTS_DIR / "unmatched_images.json"

UPSTREAM_REPOSITORY_URL = "https://github.com/spMohanty/PlantVillage-Dataset"
UPSTREAM_COMMIT_SHA = "7f7ecc7e1eaca78107e3affe7cb5abd9427e139a"

# Class name -> the exact filtered_leafmaps CSV filename (== the "_key"
# aggregate_map.py derives via `_csvfile.split("/")[-1].split(".")[0]`).
TOMATO_CSV_FILES = {
    "Tomato Healthy": "Tomato___healthy.csv",
    "Tomato Early Blight": "Tomato___Early_blight.csv",
    "Tomato Late Blight": "Tomato___Late_blight.csv",
}

UUID_PREFIX_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}___"
)


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


def _upstream_style_filename_normalize(file_name: str) -> str:
    """Exact port of aggregate_map.py's normalization:
        _filename = ".".join(row['File Name'].split(".")[:-1])
        _filename = _filename.lower().strip()
    Splits on every '.', drops only the final segment (the extension),
    rejoins the rest with '.' (this deliberately preserves a `.1`-style
    sub-numbering token, since that is not the final segment), then
    lowercases and strips. Ported verbatim from the upstream Python 2
    script; not invented independently.
    """
    parts = file_name.split(".")
    stripped = ".".join(parts[:-1]) if len(parts) > 1 else file_name
    return stripped.lower().strip()


def _current_image_normalize(image_filename_no_ext: str) -> str:
    """Same normalization our M3A join used: strip a UUID prefix (which
    the upstream CSVs never contain, since they predate/are independent of
    whatever process added those prefixes to a subset of raw/color files),
    then lower+strip -- matching aggregate_map.py's own lower().strip()."""
    stripped = UUID_PREFIX_RE.sub("", image_filename_no_ext)
    return stripped.lower().strip()


# ---------------------------------------------------------------------------
# Stage A: metadata inventory
# ---------------------------------------------------------------------------

def stage_metadata_inventory() -> dict:
    inventory = {
        "upstream_repository_url": UPSTREAM_REPOSITORY_URL,
        "upstream_commit_sha": UPSTREAM_COMMIT_SHA,
        "fetched_files": {},
    }

    for class_name, csv_name in sorted(TOMATO_CSV_FILES.items()):
        path = FILTERED_LEAFMAPS_DIR / csv_name
        rel = str(path.relative_to(ML_SERVICE_ROOT))
        if not path.exists():
            inventory["fetched_files"][csv_name] = {"exists": False}
            continue

        raw_bytes = path.read_bytes()
        has_bom = raw_bytes[:3] == b"\xef\xbb\xbf"
        try:
            raw_bytes.decode("utf-8")
            encoding = "utf-8"
        except UnicodeDecodeError:
            encoding = "not-clean-utf-8"

        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            columns = reader.fieldnames
            rows = list(reader)

        filename_counts = defaultdict(int)
        blank_filename = 0
        blank_leaf_id = 0
        malformed_rows = []
        for idx, row in enumerate(rows):
            fn = (row.get("File Name") or "").strip()
            leaf = (row.get("Leaf #") or "").strip()
            if not fn:
                blank_filename += 1
            if not leaf:
                blank_leaf_id += 1
            if not fn or not leaf:
                malformed_rows.append({"row_index": idx, "File Name": row.get("File Name"), "Leaf #": row.get("Leaf #")})
            filename_counts[fn] += 1

        duplicate_filenames = {fn: c for fn, c in filename_counts.items() if c > 1}

        inventory["fetched_files"][csv_name] = {
            "relative_path": rel,
            "exists": True,
            "size_bytes": path.stat().st_size,
            "sha256": _sha256_file(path),
            "encoding": encoding,
            "utf8_bom_present": has_bom,
            "columns": columns,
            "row_count": len(rows),
            "duplicate_file_name_row_count": len(duplicate_filenames),
            "duplicate_file_name_examples": dict(list(duplicate_filenames.items())[:10]),
            "blank_file_name_count": blank_filename,
            "blank_leaf_id_count": blank_leaf_id,
            "malformed_row_count": len(malformed_rows),
            "malformed_rows": malformed_rows[:20],
            "associated_class": class_name,
        }

    for script_name in ("aggregate_map.py", "create_map.py"):
        path = SOURCE_ROOT / "leaf_grouping" / script_name
        if path.exists():
            inventory["fetched_files"][script_name] = {
                "relative_path": str(path.relative_to(ML_SERVICE_ROOT)),
                "exists": True,
                "size_bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
                "note": "Inspected to reproduce normalization exactly; not executed (Python 2, uses csv.DictReader + xlrd).",
            }

    return inventory


# ---------------------------------------------------------------------------
# Stage B: build the CSV-derived leaf-id map (reproducing aggregate_map.py)
# ---------------------------------------------------------------------------

def stage_build_csv_leaf_map() -> dict:
    """Returns {normalized_filename_key: [leaf_id, ...]} exactly as
    aggregate_map.py's MAP dict would, restricted to only the 3 fetched
    Tomato CSVs (not all 31 upstream CSVs, since only Tomato is in scope
    for M3B-1)."""
    csv_map: dict[str, list[str]] = defaultdict(list)

    for class_name, csv_name in sorted(TOMATO_CSV_FILES.items()):
        path = FILTERED_LEAFMAPS_DIR / csv_name
        csv_key = csv_name.split(".")[0]  # matches aggregate_map.py's _key derivation
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                file_name = row["File Name"]
                leaf_num = row["Leaf #"]
                normalized = _upstream_style_filename_normalize(file_name)
                leaf_id = f"{csv_key}:::{leaf_num}"
                csv_map[normalized].append(leaf_id)

    return csv_map


# ---------------------------------------------------------------------------
# Stage C: staged matching against unmatched Tomato images
# ---------------------------------------------------------------------------

def stage_recovery_matching(csv_map: dict[str, list[str]]):
    with open(UNMATCHED_IMAGES_PATH) as f:
        unmatched_all = json.load(f)

    tomato_unmatched = [e for e in unmatched_all if e["class_name"] in TOMATO_CSV_FILES]

    class_to_csv_key = {cn: csv_name.split(".")[0] for cn, csv_name in TOMATO_CSV_FILES.items()}

    matches = []
    ambiguous = []
    unresolved = []

    for entry in sorted(tomato_unmatched, key=lambda e: e["path"]):
        path = entry["path"]
        class_name = entry["class_name"]
        image_filename = Path(path).name
        image_stem = Path(path).stem  # matches prepare_dataset.py's use of path.stem

        normalized_current = _current_image_normalize(image_stem)
        expected_csv_key = class_to_csv_key[class_name]

        candidates = csv_map.get(normalized_current, [])
        # Only candidates whose csv_key matches this image's own class are
        # compatible -- a candidate from a different class's CSV key would
        # be a cross-class collision, not a valid match for this image.
        compatible = [c for c in candidates if c.startswith(expected_csv_key + ":::")]

        record = {
            "current_image_path": path,
            "normalized_image_filename": normalized_current,
            "matched_metadata_source_file": TOMATO_CSV_FILES[class_name],
            "class_name": class_name,
        }

        if len(compatible) == 0:
            record.update(
                {
                    "original_metadata_filename_value": None,
                    "recovered_leaf_identifier": None,
                    "matching_method": None,
                    "ambiguity_count": 0,
                    "status": "no_match",
                }
            )
            unresolved.append(record)
        elif len(set(compatible)) == 1:
            record.update(
                {
                    "original_metadata_filename_value": image_filename,
                    "recovered_leaf_identifier": compatible[0],
                    "matching_method": (
                        "exact_authoritative_match"
                        if image_stem == normalized_current
                        else "normalized_authoritative_match"
                    ),
                    "ambiguity_count": len(compatible),
                    "status": (
                        "exact_authoritative_match"
                        if image_stem == normalized_current
                        else "normalized_authoritative_match"
                    ),
                }
            )
            matches.append(record)
        else:
            record.update(
                {
                    "original_metadata_filename_value": image_filename,
                    "recovered_leaf_identifier": None,
                    "matching_method": "multiple_incompatible_candidates",
                    "ambiguity_count": len(set(compatible)),
                    "status": "ambiguous_match",
                    "candidate_leaf_identifiers": sorted(set(compatible)),
                }
            )
            ambiguous.append(record)

    return tomato_unmatched, matches, ambiguous, unresolved


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_recovery() -> dict:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    inventory = stage_metadata_inventory()
    _write_json(REPORTS_DIR / "tomato_metadata_inventory.json", inventory)

    csv_map = stage_build_csv_leaf_map()
    tomato_unmatched, matches, ambiguous, unresolved = stage_recovery_matching(csv_map)

    all_records = sorted(
        matches + ambiguous + unresolved, key=lambda r: r["current_image_path"]
    )
    _write_json(REPORTS_DIR / "tomato_recovery_matches.json", all_records)
    _write_json(REPORTS_DIR / "tomato_ambiguous_matches.json", ambiguous)
    _write_json(REPORTS_DIR / "tomato_unresolved_after_recovery.json", unresolved)

    per_class = defaultdict(lambda: {
        "unmatched_before_recovery": 0,
        "exact_authoritative_match": 0,
        "normalized_authoritative_match": 0,
        "ambiguous_match": 0,
        "malformed_metadata": 0,
        "no_match": 0,
    })
    for e in tomato_unmatched:
        per_class[e["class_name"]]["unmatched_before_recovery"] += 1
    for r in matches:
        per_class[r["class_name"]][r["status"]] += 1
    for r in ambiguous:
        per_class[r["class_name"]]["ambiguous_match"] += 1
    for r in unresolved:
        per_class[r["class_name"]]["no_match"] += 1

    summary = {}
    for class_name in sorted(TOMATO_CSV_FILES):
        stats = per_class[class_name]
        recovered = stats["exact_authoritative_match"] + stats["normalized_authoritative_match"]
        unresolved_count = stats["unmatched_before_recovery"] - recovered
        pct = (recovered / stats["unmatched_before_recovery"] * 100) if stats["unmatched_before_recovery"] else 0.0
        summary[class_name] = {
            **stats,
            "unresolved_after_recovery": unresolved_count,
            "recovered_percentage": round(pct, 2),
        }
    _write_json(REPORTS_DIR / "tomato_recovery_summary.json", summary)

    leaf_map_sha256 = None
    leaf_map_path = SOURCE_ROOT / "leaf-map.json"
    if leaf_map_path.exists():
        leaf_map_sha256 = _sha256_file(leaf_map_path)

    source_integrity = {
        "upstream_repository_url": UPSTREAM_REPOSITORY_URL,
        "upstream_commit_sha": UPSTREAM_COMMIT_SHA,
        "fetch_scope": "leaf_grouping/filtered_leafmaps/{Tomato___healthy,Tomato___Early_blight,Tomato___Late_blight}.csv + aggregate_map.py + create_map.py only -- no other leaf_grouping files, no other crop metadata.",
        "existing_leaf_map_json_sha256": leaf_map_sha256,
        "csv_sha256": {
            name: inventory["fetched_files"][name]["sha256"]
            for name in TOMATO_CSV_FILES.values()
        },
        "recovery_script_version": "0.1.0-m3b1",
    }
    _write_json(REPORTS_DIR / "tomato_source_integrity.json", source_integrity)

    run_metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "agriai_repo_commit_at_run_time": _agriai_repo_commit(),
        "note": "Volatile timestamp isolated from the deterministic reports above, matching the M3A pattern.",
    }
    _write_json(REPORTS_DIR / "tomato_recovery_run_metadata.json", run_metadata)

    return {
        "inventory": inventory,
        "summary": summary,
        "source_integrity": source_integrity,
        "run_metadata": run_metadata,
    }


if __name__ == "__main__":
    result = run_recovery()
    print(json.dumps(result["summary"], indent=2))
    print("\n(Full detail written to ml-service/data/reports/tomato_*.json)")
