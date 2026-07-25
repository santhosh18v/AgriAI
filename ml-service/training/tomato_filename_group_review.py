"""Milestone M3B-2A: filename-family group inventory + contact-sheet
generation for AI-ASSISTED PRELIMINARY visual review of proposed (NOT
approved) Tomato grouping rules.

Review status: this script only renders contact sheets; it records no
judgments itself. The judgments recorded elsewhere
(tomato_filename_review_judgments.py) from inspecting these sheets are
`review_type: "preliminary_ai_review"` -- an AI assistant's preliminary
pass, not final human approval. No group is eligible for
train/validation/test use as a result of anything in this script or its
outputs. Final approval belongs to the user during Milestone M3B-2.

This script only proposes candidate groups and renders them for review.
It never assigns reviewed_filename_family, never writes
approved_phash_groups.json, never touches split eligibility, and never
modifies any M3A or M3B-1 report. Read-only with respect to those.

Two candidate rules are inventoried (not approved):
  - Tomato Healthy: group by base `Leaf <N>` number, decimal sub-index
    stripped.
  - Tomato Late Blight: group by (session_prefix, base `Leaf <N>` number),
    decimal sub-index AND `Day <N>` both collapsed into one group.

Tomato Early Blight (1 unmatched image) is deliberately NOT given a
candidate rule -- a single image cannot demonstrate a filename family, per
the M3B-2A instructions; it is reported as unresolved/quarantined.

The preliminary_ai_review visual-review judgments (same_physical_leaf_likely,
etc.) are recorded separately, in tomato_filename_review_judgments.py, after
this script's contact sheets have been inspected -- this script only
proposes the sample and renders it.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from collections import defaultdict, Counter
from datetime import datetime, timezone
from pathlib import Path

ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
SOURCE_ROOT = ML_SERVICE_ROOT / "data" / "raw" / "plantvillage-source"
REPORTS_DIR = ML_SERVICE_ROOT / "data" / "reports"
REVIEW_DIR = REPORTS_DIR / "tomato_filename_review"
UNMATCHED_IMAGES_PATH = REPORTS_DIR / "unmatched_images.json"

UUID_PREFIX_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}___", re.I
)

TH_RE = re.compile(r"^GH_HL Leaf (\d+)(\.(\d+))?\s*$", re.I)
TLB_RE = re.compile(
    r"^(GHLB2ES|GHLB2|GHLB_PS|GHLB|GH_HL)\s+Leaf\s+(\d+)(\.(\d+))?(\s+Day\s*(\d+))?\s*$",
    re.I,
)

SEED = 42


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


def _strip_ext(fn: str) -> str:
    return re.sub(r"\.(jpg|jpeg)$", "", fn, flags=re.I)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_tomato_healthy(path: str):
    fn = Path(path).name
    stem = UUID_PREFIX_RE.sub("", _strip_ext(fn))
    m = TH_RE.match(stem)
    if not m:
        return {"parsed": False, "stem": stem, "path": path, "filename": fn}
    leaf_number = int(m.group(1))
    sub_index = int(m.group(3)) if m.group(3) else None
    return {
        "parsed": True,
        "stem": stem,
        "path": path,
        "filename": fn,
        "leaf_number": leaf_number,
        "sub_index": sub_index,
        "candidate_group_key": f"th::Leaf{leaf_number}",
    }


def parse_tomato_late_blight(path: str):
    fn = Path(path).name
    stem = UUID_PREFIX_RE.sub("", _strip_ext(fn))
    m = TLB_RE.match(stem)
    if not m:
        return {"parsed": False, "stem": stem, "path": path, "filename": fn}
    session_prefix = m.group(1).upper() if m.group(1).upper() != "GH_HL" else m.group(1)
    # Normalize known prefixes to a canonical case (GHLB2ES/GHLB2/GHLB_PS/GHLB).
    canon = {"GHLB2ES": "GHLB2ES", "GHLB2": "GHLB2", "GHLB_PS": "GHLB_PS", "GHLB": "GHLB"}
    session_prefix = canon.get(m.group(1).upper(), m.group(1))
    leaf_number = int(m.group(2))
    sub_index = int(m.group(4)) if m.group(4) else None
    day_number = int(m.group(6)) if m.group(6) else None
    return {
        "parsed": True,
        "stem": stem,
        "path": path,
        "filename": fn,
        "session_prefix": session_prefix,
        "leaf_number": leaf_number,
        "sub_index": sub_index,
        "day_number": day_number,
        "candidate_group_key": f"tlb::{session_prefix}::Leaf{leaf_number}",
    }


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

def build_inventory():
    with open(UNMATCHED_IMAGES_PATH) as f:
        unmatched = json.load(f)

    th_images = sorted(
        [e["path"] for e in unmatched if e["class_name"] == "Tomato Healthy"]
    )
    tlb_images = sorted(
        [e["path"] for e in unmatched if e["class_name"] == "Tomato Late Blight"]
    )
    teb_images = sorted(
        [e["path"] for e in unmatched if e["class_name"] == "Tomato Early Blight"]
    )

    th_parsed = [parse_tomato_healthy(p) for p in th_images]
    tlb_parsed = [parse_tomato_late_blight(p) for p in tlb_images]

    def group_stats(parsed_records, class_name):
        malformed = [r for r in parsed_records if not r["parsed"]]
        parsed_ok = [r for r in parsed_records if r["parsed"]]
        groups: dict[str, list] = defaultdict(list)
        for r in parsed_ok:
            groups[r["candidate_group_key"]].append(r)

        sizes = Counter(len(v) for v in groups.values())
        largest = max((len(v) for v in groups.values()), default=0)

        return {
            "class_name": class_name,
            "total_unmatched_images": len(parsed_records),
            "malformed_or_unparseable_count": len(malformed),
            "malformed_or_unparseable_filenames": sorted(r["filename"] for r in malformed),
            "parsed_image_count": len(parsed_ok),
            "proposed_group_count": len(groups),
            "singleton_groups": sizes.get(1, 0),
            "groups_of_size_2": sizes.get(2, 0),
            "groups_of_size_3": sizes.get(3, 0),
            "groups_of_size_4_or_more": sum(c for size, c in sizes.items() if size >= 4),
            "largest_group_size": largest,
            "group_size_distribution": dict(sorted(sizes.items())),
        }, groups

    th_stats, th_groups = group_stats(th_parsed, "Tomato Healthy")
    tlb_stats, tlb_groups = group_stats(tlb_parsed, "Tomato Late Blight")

    teb_stats = {
        "class_name": "Tomato Early Blight",
        "total_unmatched_images": len(teb_images),
        "malformed_or_unparseable_count": 0,
        "malformed_or_unparseable_filenames": [],
        "parsed_image_count": 0,
        "proposed_group_count": 0,
        "singleton_groups": 0,
        "groups_of_size_2": 0,
        "groups_of_size_3": 0,
        "groups_of_size_4_or_more": 0,
        "largest_group_size": 0,
        "group_size_distribution": {},
        "note": "Only 1 unmatched image -- a single image cannot demonstrate a filename family. No candidate rule proposed; remains quarantined pending direct evidence.",
        "unmatched_filename": Path(teb_images[0]).name if teb_images else None,
    }

    inventory = {
        "seed": SEED,
        "classes": {
            "Tomato Healthy": th_stats,
            "Tomato Late Blight": tlb_stats,
            "Tomato Early Blight": teb_stats,
        },
    }
    return inventory, th_groups, tlb_groups, th_parsed, tlb_parsed


# ---------------------------------------------------------------------------
# Collision checks (section 4)
# ---------------------------------------------------------------------------

def collision_checks(th_groups, tlb_groups, th_parsed, tlb_parsed):
    result = {}

    # Same group key across classes: structurally impossible here since
    # keys are prefixed "th::"/"tlb::", but verify explicitly rather than
    # assume.
    th_keys = set(th_groups.keys())
    tlb_keys = set(tlb_groups.keys())
    result["group_key_collisions_across_classes"] = sorted(th_keys & tlb_keys)

    # Same leaf number under different session prefixes (Late Blight) --
    # expected to exist; report it, and confirm our key keeps them separate.
    leafnum_to_prefixes = defaultdict(set)
    for r in tlb_parsed:
        if r["parsed"]:
            leafnum_to_prefixes[r["leaf_number"]].add(r["session_prefix"])
    shared_leafnum_diff_prefix = {
        str(num): sorted(prefixes)
        for num, prefixes in leafnum_to_prefixes.items()
        if len(prefixes) > 1
    }
    result["late_blight_leaf_numbers_shared_across_different_session_prefixes"] = {
        "count": len(shared_leafnum_diff_prefix),
        "examples": dict(list(shared_leafnum_diff_prefix.items())[:10]),
        "note": "These are kept as SEPARATE groups by the candidate rule (key includes session_prefix), confirming normalization does not merge across sessions.",
    }

    # Raw base-string collisions between classes (sanity check that the
    # GH_HL Healthy convention and GHLB* Late Blight convention never
    # produce the same raw stem).
    th_stems = {r["stem"] for r in th_parsed if r["parsed"]}
    tlb_stems = {r["stem"] for r in tlb_parsed if r["parsed"]}
    result["raw_stem_collisions_between_healthy_and_late_blight"] = sorted(th_stems & tlb_stems)

    return result


# ---------------------------------------------------------------------------
# Comparison against authoritative CSVs (section 5)
# ---------------------------------------------------------------------------

def compare_against_authoritative():
    import csv as csv_mod

    filtered = SOURCE_ROOT / "leaf_grouping" / "filtered_leafmaps"
    files = {
        "Tomato Healthy": filtered / "Tomato___healthy.csv",
        "Tomato Early Blight": filtered / "Tomato___Early_blight.csv",
        "Tomato Late Blight": filtered / "Tomato___Late_blight.csv",
    }

    findings = {}
    for class_name, path in files.items():
        if not path.exists():
            findings[class_name] = {"available": False}
            continue
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv_mod.DictReader(f))
        decimal_suffixed = [
            r for r in rows if re.search(r"\d+\.\d+\.[Jj][Pp][Gg]", r["File Name"])
        ]
        day_suffixed = [r for r in rows if re.search(r"\bDay\b", r["File Name"], re.I)]
        findings[class_name] = {
            "available": True,
            "csv_row_count": len(rows),
            "decimal_suffixed_filename_rows_in_authoritative_csv": len(decimal_suffixed),
            "day_suffixed_filename_rows_in_authoritative_csv": len(day_suffixed),
        }

    findings["conclusion"] = (
        "Zero decimal-suffixed and zero Day-suffixed filenames exist anywhere "
        "in the three authoritative Tomato CSVs (RS_HL / RS_Erly.B / RS_Late.B "
        "families never use this convention). This comparison provides NO "
        "supporting or refuting evidence for the decimal-suffix or Day-suffix "
        "grouping hypotheses -- there is no comparable pattern in the "
        "authoritative source to validate against. Not fabricating equivalence "
        "where none exists; the visual review (section 3) is the only evidence "
        "source for these two hypotheses."
    )
    return findings


# ---------------------------------------------------------------------------
# Deterministic sampling for contact sheets
# ---------------------------------------------------------------------------

def sample_groups_for_review(groups: dict, min_count: int, class_tag: str):
    """Deterministic, stable-sorted sample of multi-image (size>=2) groups,
    stratified across group sizes."""
    multi = {k: v for k, v in groups.items() if len(v) >= 2}
    keys_sorted = sorted(multi.keys())

    by_size = defaultdict(list)
    for k in keys_sorted:
        by_size[len(multi[k])].append(k)
    for size in by_size:
        by_size[size].sort()

    sizes_sorted = sorted(by_size.keys())
    picked = []
    i = 0
    while len(picked) < min_count and any(by_size[s] for s in sizes_sorted):
        size = sizes_sorted[i % len(sizes_sorted)]
        if by_size[size]:
            picked.append(by_size[size].pop(0))
        i += 1
        if i > 10000:
            break

    return {k: multi[k] for k in sorted(picked)}


def sample_late_blight_groups_for_review(groups: dict, min_count: int):
    """Stratified deterministic sample for Tomato Late Blight: guarantees
    coverage of every session prefix that has any multi-image group, and of
    at least one Day-number-bearing group where available, in addition to
    spanning different group sizes -- required because a naive size-only
    stratification (as used for the simpler Tomato Healthy case) undersamples
    rare prefixes like GHLB2ES."""
    multi = {k: v for k, v in groups.items() if len(v) >= 2}

    by_prefix = defaultdict(list)
    for k in sorted(multi.keys()):
        prefix = k.split("::")[1]
        by_prefix[prefix].append(k)

    picked: list[str] = []
    picked_set: set[str] = set()

    def take(key):
        if key not in picked_set:
            picked.append(key)
            picked_set.add(key)

    # Pass 1: at least 2 groups per session prefix (or all available if fewer),
    # preferring one Day-bearing and one non-Day-bearing group per prefix
    # where both exist, so Day-number patterns are represented.
    for prefix in sorted(by_prefix.keys()):
        keys = by_prefix[prefix]
        day_keys = [k for k in keys if any(m["day_number"] is not None for m in multi[k])]
        non_day_keys = [k for k in keys if k not in day_keys]
        for k in (day_keys[:1] + non_day_keys[:1] + keys)[:2]:
            take(k)

    # Pass 2: round-robin across sizes for the remaining budget, spanning
    # all prefixes, until min_count reached.
    by_size = defaultdict(list)
    for k in sorted(multi.keys()):
        if k not in picked_set:
            by_size[len(multi[k])].append(k)
    sizes_sorted = sorted(by_size.keys())
    i = 0
    while len(picked) < min_count and any(by_size[s] for s in sizes_sorted):
        size = sizes_sorted[i % len(sizes_sorted)]
        if by_size[size]:
            take(by_size[size].pop(0))
        i += 1
        if i > 10000:
            break

    picked = sorted(picked)
    return {k: multi[k] for k in picked}


# ---------------------------------------------------------------------------
# Contact sheet rendering
# ---------------------------------------------------------------------------

def render_contact_sheets(sampled_groups: dict, out_prefix: Path, groups_per_sheet: int, thumb_size=(140, 140)):
    from PIL import Image, ImageDraw, ImageFont
    import imagehash

    keys = sorted(sampled_groups.keys())
    sheets_written = []

    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    for sheet_idx in range(0, len(keys), groups_per_sheet):
        sheet_keys = keys[sheet_idx : sheet_idx + groups_per_sheet]
        max_cols = max(len(sampled_groups[k]) for k in sheet_keys)
        row_h = thumb_size[1] + 55
        col_w = thumb_size[0] + 10
        label_col_w = 260
        img_w = label_col_w + max_cols * col_w
        img_h = len(sheet_keys) * row_h + 20

        sheet = Image.new("RGB", (img_w, img_h), "white")
        draw = ImageDraw.Draw(sheet)

        for row_idx, key in enumerate(sheet_keys):
            members = sampled_groups[key]
            y = row_idx * row_h + 10
            draw.text((5, y + thumb_size[1] // 2 - 10), key, fill="black", font=font)

            phashes = []
            for col_idx, member in enumerate(members):
                x = label_col_w + col_idx * col_w
                img_path = ML_SERVICE_ROOT / member["path"]
                try:
                    with Image.open(img_path) as im:
                        im = im.convert("RGB")
                        ph = imagehash.phash(im)
                        phashes.append(ph)
                        thumb = im.copy()
                        thumb.thumbnail(thumb_size)
                        sheet.paste(thumb, (x, y))
                except Exception as e:
                    draw.text((x, y), f"ERR:{e}", fill="red", font=font)
                    phashes.append(None)

                label_parts = [member["filename"]]
                if "sub_index" in member and member["sub_index"] is not None:
                    label_parts.append(f"sub={member['sub_index']}")
                if "day_number" in member and member["day_number"] is not None:
                    label_parts.append(f"day={member['day_number']}")
                if col_idx > 0 and phashes[0] is not None and phashes[-1] is not None:
                    dist = phashes[0] - phashes[-1]
                    label_parts.append(f"phash_dist_to_first={dist}")
                label = "\n".join(label_parts)
                draw.text((x, y + thumb_size[1] + 2), label[:60], fill="black", font=font)

        REVIEW_DIR.mkdir(parents=True, exist_ok=True)
        out_path = REVIEW_DIR / f"{out_prefix.name}_{sheet_idx // groups_per_sheet + 1:02d}.png"
        sheet.save(out_path)
        sheets_written.append(str(out_path.relative_to(ML_SERVICE_ROOT)))

    return sheets_written


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run():
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    inventory, th_groups, tlb_groups, th_parsed, tlb_parsed = build_inventory()
    _write_json(REPORTS_DIR / "tomato_filename_group_inventory.json", inventory)

    collisions = collision_checks(th_groups, tlb_groups, th_parsed, tlb_parsed)
    authoritative_comparison = compare_against_authoritative()

    candidates_report = {
        "tomato_healthy_groups": {
            k: [{"path": m["path"], "filename": m["filename"], "leaf_number": m["leaf_number"], "sub_index": m["sub_index"]} for m in v]
            for k, v in sorted(th_groups.items())
        },
        "tomato_late_blight_groups": {
            k: [
                {
                    "path": m["path"],
                    "filename": m["filename"],
                    "session_prefix": m["session_prefix"],
                    "leaf_number": m["leaf_number"],
                    "sub_index": m["sub_index"],
                    "day_number": m["day_number"],
                }
                for m in v
            ]
            for k, v in sorted(tlb_groups.items())
        },
        "collision_checks": collisions,
        "authoritative_comparison": authoritative_comparison,
    }
    _write_json(REPORTS_DIR / "tomato_filename_group_candidates.json", candidates_report)

    # Deterministic sample for visual review.
    th_sample = sample_groups_for_review(th_groups, min_count=20, class_tag="th")
    tlb_sample = sample_late_blight_groups_for_review(tlb_groups, min_count=30)

    th_sheets = render_contact_sheets(th_sample, REVIEW_DIR / "tomato_healthy_contact_sheet", groups_per_sheet=10)
    tlb_sheets = render_contact_sheets(tlb_sample, REVIEW_DIR / "tomato_late_blight_contact_sheet", groups_per_sheet=10)

    sample_manifest = {
        "tomato_healthy_sampled_group_keys": sorted(th_sample.keys()),
        "tomato_healthy_sampled_group_count": len(th_sample),
        "tomato_late_blight_sampled_group_keys": sorted(tlb_sample.keys()),
        "tomato_late_blight_sampled_group_count": len(tlb_sample),
        "tomato_healthy_contact_sheets": th_sheets,
        "tomato_late_blight_contact_sheets": tlb_sheets,
    }
    _write_json(REPORTS_DIR / "tomato_filename_group_sample_manifest.json", sample_manifest)

    run_metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "agriai_repo_commit_at_run_time": _agriai_repo_commit(),
        "note": "Volatile timestamp isolated from deterministic reports, matching the M3A/M3B-1 pattern.",
    }
    _write_json(REPORTS_DIR / "tomato_filename_review_run_metadata.json", run_metadata)

    return {
        "inventory": inventory,
        "sample_manifest": sample_manifest,
        "candidates_report_path": "data/reports/tomato_filename_group_candidates.json",
    }


if __name__ == "__main__":
    result = run()
    print(json.dumps(result["inventory"], indent=2))
    print()
    print(json.dumps(result["sample_manifest"], indent=2))
