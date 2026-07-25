# AgriAI ml-service

Python service for the Phase 2 custom crop-disease classifier. Through
**Milestone M4**, this covers dataset preparation, an approved deterministic
train/validation/test split, and a first reproducible EfficientNet-B0
training baseline. There is still no running FastAPI service and no
Next.js integration — those are later milestones.

## What exists through M4

- `requirements.txt` — pinned runtime/inference dependencies (FastAPI,
  Pillow, PyTorch, etc), for the not-yet-built inference service.
- `requirements-training.txt` — the actual environment used for M3/M4:
  training/evaluation tooling (torch, torchvision, scikit-learn, tqdm,
  pytest, imagehash, etc), with Python-3.13/arm64-compatible version pins.
  See `docs/MODEL_TRAINING.md` for the compatibility note explaining why
  its pins differ from `requirements.txt`.
- `.env.example` — names and safe placeholder values for `MODEL_PATH` and
  `LOG_LEVEL`. No real secrets.
- `app/config.py`, `app/schemas.py` — inference-service scaffolding from
  M1. No routes wired up yet; serving is a later milestone.
- `training/class_map.json` — the 8 approved classes (Tomato/Potato/Corn),
  frozen index-to-label mapping, unchanged since M1.
- `training/model_scope_v1.json`, `training/tomato_grouping_policy_v1.json`,
  `training/similarity_guards_v1.json` — approved M3B dataset-scope and
  grouping policy (see `docs/DATASET_PROVENANCE.md`).
- `training/build_splits.py`, `training/check_leakage.py`,
  `training/validate_splits.py` — deterministic split generation and its
  two independent validation passes (M3B-3/M3B-3A/M3B-4).
- `training/dataset.py`, `training/model.py`, `training/train.py`,
  `training/evaluate.py` — the M4 EfficientNet-B0 training/evaluation
  pipeline. See `docs/MODEL_TRAINING.md` for commands, configuration, and
  results.
- `tests/training/` — pytest suite for the M4 pipeline, using tiny
  synthetic images/manifests only (no real dataset images are tracked).

## Dataset

Dataset source, licence, fetch method, integrity metadata, grouping policy,
and the approved M3B-4 split sign-off are documented in
**[`docs/DATASET_PROVENANCE.md`](docs/DATASET_PROVENANCE.md)** — that file
is the authoritative record; nothing dataset-related is duplicated here.
The dataset and generated split manifests live only under the gitignored
`ml-service/data/` directory and are never committed.

## Model training

Baseline training configuration, commands, outputs, and known limitations
(notably the small Potato Healthy validation slice) are documented in
**[`docs/MODEL_TRAINING.md`](docs/MODEL_TRAINING.md)**. Trained checkpoints
live only under the gitignored `ml-service/data/training-runs/` and
`ml-service/models/` directories and are never committed or pushed.

## What does NOT exist yet (later milestones)

- No M5 final test-set evaluation or confidence-threshold selection —
  `test.csv` has not been loaded by anything yet.
- No FastAPI app (`app/main.py`, `app/routers/`, `app/inference.py`) and no
  running server — M6/M7.
- No integration with the Next.js app — M8/M9.

## Approved classes (fixed, do not add without approval)

Active 6-class model scope (`training/model_scope_v1.json`): Tomato
Healthy · Tomato Early Blight · Tomato Late Blight · Potato Healthy ·
Potato Early Blight · Potato Late Blight.

Temporarily excluded: Corn Healthy · Corn Common Rust (see
`docs/DATASET_PROVENANCE.md` for why). `training/class_map.json` itself
remains unchanged and still defines all 8 originally approved classes.
