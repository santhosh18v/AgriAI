# AgriAI ml-service

Python service for the Phase 2 custom crop-disease classifier. Through
**Milestone M7**, this covers dataset preparation, an approved deterministic
train/validation/test split, a first reproducible EfficientNet-B0 training
baseline, a one-time frozen test evaluation with a validation-selected
confidence threshold, a running FastAPI service foundation (health,
readiness, model-info), and a real disease-image prediction endpoint. There
is still no upload persistence, no prediction history, no Gemini fallback,
and no Next.js integration — those are later milestones.

## What exists through M7

- `requirements.txt` — pinned runtime/inference dependencies (FastAPI,
  Pillow, PyTorch, etc), for the not-yet-built inference service.
- `requirements-training.txt` — the actual environment used for M3/M4:
  training/evaluation tooling (torch, torchvision, scikit-learn, tqdm,
  pytest, imagehash, etc), with Python-3.13/arm64-compatible version pins.
  See `docs/MODEL_TRAINING.md` for the compatibility note explaining why
  its pins differ from `requirements.txt`.
- `.env.example` — names and safe placeholder values for the `AGRI_ML_`-
  prefixed settings (see `docs/API_FOUNDATION.md`). No real secrets.
- `app/` — the FastAPI service: `main.py` (app + lifespan + CORS),
  `config.py` (pydantic-settings), `model_loader.py` (validated, load-once
  model loading), `schemas.py`, `dependencies.py`, `routes/health.py`,
  `routes/model_info.py`, and (M7) `routes/predict.py`,
  `image_validation.py`, `preprocessing.py`, `inference.py`. See
  `docs/API_FOUNDATION.md` (foundation/config) and
  `docs/PREDICTION_API.md` (the `/api/predict/disease` endpoint). There is
  still no upload persistence, prediction history, or Gemini fallback —
  that is later scope.
- `training/class_map.json` — the 8 approved classes (Tomato/Potato/Corn),
  frozen index-to-label mapping, unchanged since M1.
- `training/model_scope_v1.json`, `training/tomato_grouping_policy_v1.json`,
  `training/similarity_guards_v1.json` — approved M3B dataset-scope and
  grouping policy (see `docs/DATASET_PROVENANCE.md`).
- `training/build_splits.py`, `training/check_leakage.py`,
  `training/validate_splits.py` — deterministic split generation and its
  two independent validation passes (M3B-3/M3B-3A/M3B-4).
- `training/dataset.py`, `training/model.py`, `training/train.py` — the M4
  EfficientNet-B0 training pipeline. See `docs/MODEL_TRAINING.md` for
  commands, configuration, and results.
- `training/evaluate.py` — M5 evaluation utility with two explicit modes:
  `validation` (repeatable, val.csv) and `final-test` (one-time, test.csv,
  requires `--confirm-final-test-evaluation`). Verifies manifest and
  checkpoint SHA-256 before loading any data.
- `training/select_threshold.py` — M5 confidence-threshold selection
  (`select`, validation predictions only) and frozen-threshold application
  to test predictions with calibration/bootstrap/error analysis (`apply`).
- `training/confidence_policy_v1.json` — the frozen, tracked M5 threshold
  decision record. See `docs/MODEL_EVALUATION.md` for full results.
- `tests/training/` — pytest suite for the M4/M5 pipeline, using tiny
  synthetic images/manifests only (no real dataset images are tracked).
- `tests/api/` — pytest suite for the API foundation and prediction
  endpoint (M6/M7), using tiny synthetic checkpoints and in-memory synthetic
  images only (the real ~48MB checkpoint and PlantVillage source images are
  never used by an automated test).

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

## Model evaluation (M5)

The frozen M4 checkpoint's one-time test evaluation, the validation-only
confidence-threshold selection, and their full results, limitations, and
reproduction commands are documented in
**[`docs/MODEL_EVALUATION.md`](docs/MODEL_EVALUATION.md)**. `test.csv` has
now been evaluated exactly once and must not be evaluated again.

## API foundation (M6) and prediction endpoint (M7)

The FastAPI service foundation — health, readiness, and model-information
endpoints, configuration, and safe model loading — is documented in
**[`docs/API_FOUNDATION.md`](docs/API_FOUNDATION.md)**. The disease-image
prediction endpoint (`POST /api/predict/disease`) — upload validation,
preprocessing, inference, response shape, and manual-verification results
against the real checkpoint — is documented in
**[`docs/PREDICTION_API.md`](docs/PREDICTION_API.md)**.

```bash
cd ml-service
.venv/bin/python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

## What does NOT exist yet (later milestones)

- No upload persistence, prediction history, or Gemini fallback.
- No integration with the Next.js app — M8/M9.

## Approved classes (fixed, do not add without approval)

Active 6-class model scope (`training/model_scope_v1.json`): Tomato
Healthy · Tomato Early Blight · Tomato Late Blight · Potato Healthy ·
Potato Early Blight · Potato Late Blight.

Temporarily excluded: Corn Healthy · Corn Common Rust (see
`docs/DATASET_PROVENANCE.md` for why). `training/class_map.json` itself
remains unchanged and still defines all 8 originally approved classes.
