# AgriAI ml-service — M1 scaffold

Python FastAPI service for the Phase 2 custom crop-disease classifier. This
is **Milestone M1 only**: directory scaffolding, dependency manifests, and
typed schemas. There is no dataset, no trained model, and no running service
yet. Dataset preparation, training, model serving, and Next.js integration
are implemented in later Phase 2 milestones.

## What exists after M1

- `requirements.txt` — pinned runtime/inference dependencies (FastAPI,
  Pillow, PyTorch, etc). Not installed yet.
- `requirements-training.txt` — superset adding training/evaluation-only
  tooling (scikit-learn, imagehash, etc). Not installed yet.
- `.env.example` — names and safe placeholder values for `MODEL_PATH` and
  `LOG_LEVEL`. No real secrets.
- `app/config.py` — configuration constants (image size, normalization,
  upload limits, dev-only placeholder confidence thresholds). No model
  loading or inference logic.
- `app/schemas.py` — Pydantic request/response models for the future
  `/health`, `/model/info`, and `/predict/disease` endpoints. No routes
  wired up yet.
- `training/class_map.json` — the 8 approved classes (Tomato/Potato/Corn),
  frozen index-to-label mapping used by both training and inference once
  they exist.
- `model_manifest.example.json` — a **tracked** example of the metadata
  shape the real (gitignored) `models/version.json` will have once a model
  is trained. All values are placeholders.

## What does NOT exist yet (later milestones)

- No dataset has been downloaded (`ml-service/data/` does not exist — the
  exact PlantVillage source URL and license require explicit approval at
  M2 first).
- No training/evaluation code (`training/prepare_dataset.py`, `train.py`,
  `evaluate.py`, etc.) — M3/M4/M5.
- No FastAPI app (`app/main.py`, `app/routers/`, `app/inference.py`) and no
  running server — M6/M7.
- No integration with the Next.js app — M8/M9.

## Approved classes (fixed, do not add without approval)

Tomato Healthy · Tomato Early Blight · Tomato Late Blight · Potato Healthy ·
Potato Early Blight · Potato Late Blight · Corn Healthy · Corn Common Rust
