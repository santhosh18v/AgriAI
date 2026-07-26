# API Foundation — Milestone M6 (+ M7 endpoint registration)

## Purpose

M6 built the FastAPI service *foundation*: application startup,
configuration, safe model loading/validation, and three read-only
endpoints (health, readiness, model-info). M7 added the first real
inference endpoint, `POST /api/predict/disease`, on top of that
foundation — its request/response contract, validation, preprocessing,
and inference details are documented separately in
**[`PREDICTION_API.md`](PREDICTION_API.md)**; this document covers the
shared foundation (config, lifecycle, CORS, error handling) both endpoints
rely on.

## Service architecture

```
ml-service/app/
├── __init__.py
├── main.py               # FastAPI app factory, lifespan, CORS, error handling
├── config.py              # pydantic-settings, AGRI_ML_-prefixed env vars
├── dependencies.py         # request -> app.state accessors
├── model_loader.py         # validated, load-once model loading
├── schemas.py              # typed response models
├── image_validation.py     # M7: in-memory upload validation
├── preprocessing.py        # M7: exact M4 validation transform
├── inference.py            # M7: torch.inference_mode() forward pass
└── routes/
    ├── __init__.py
    ├── health.py          # GET /api/health, GET /api/ready
    ├── model_info.py      # GET /api/model-info
    └── predict.py         # M7: POST /api/predict/disease
```

No database, message queue, background worker, or cloud dependency was
introduced — the service is a single FastAPI process backed by an
in-process, load-once model instance.

## Environment setup

This service shares the same `ml-service/.venv` used for training/M4/M5
(Python 3.13.5, arm64 macOS). Runtime dependencies are pinned in
`requirements.txt`:

```bash
cd ml-service
.venv/bin/python3 -m pip install -r requirements.txt
```

Running the API test suite additionally requires `httpx` (used internally
by `fastapi.testclient.TestClient`). `requirements.txt` is the canonical,
runtime-only dependency set the deployed service itself installs — it has
no test-client code path, so `httpx` does not belong there. Per this
project's established convention (`requirements-training.txt` is the
actual shared development/test environment installed into `ml-service/.venv`
for all milestones, not narrowly "training only" — `pytest` itself has
lived there since before any training code existed), `httpx==0.28.1` is
recorded in `requirements-training.txt` alongside `pytest`. A fresh
environment for either test suite installs from that one file:

```bash
.venv/bin/python3 -m pip install -r requirements-training.txt
```

## Configuration

`app/config.py` uses `pydantic-settings`. All environment variables use
the `AGRI_ML_` prefix; invalid values (e.g. an unknown device or
environment name) fail immediately and clearly at `Settings()`
construction, not silently or deep inside model loading.

| Setting | Env var | Default |
|---|---|---|
| `app_name` | `AGRI_ML_APP_NAME` | `AgriAI ML Service` |
| `app_version` | `AGRI_ML_APP_VERSION` | `Phase 2 development version` |
| `environment` | `AGRI_ML_ENVIRONMENT` | `development` (`development`\|`test`\|`production`) |
| `host` | `AGRI_ML_HOST` | `127.0.0.1` |
| `port` | `AGRI_ML_PORT` | `8001` |
| `log_level` | `AGRI_ML_LOG_LEVEL` | `info` |
| `model_checkpoint_path` | `AGRI_ML_MODEL_CHECKPOINT_PATH` | `data/training-runs/m4-efficientnet-b0-seed42/best_model.pt` |
| `confidence_policy_path` | `AGRI_ML_CONFIDENCE_POLICY_PATH` | `training/confidence_policy_v1.json` |
| `class_map_path` | `AGRI_ML_CLASS_MAP_PATH` | `training/class_map.json` |
| `model_scope_path` | `AGRI_ML_MODEL_SCOPE_PATH` | `training/model_scope_v1.json` |
| `preferred_device` | `AGRI_ML_PREFERRED_DEVICE` | `auto` (`auto`\|`cpu`\|`mps`\|`cuda`) |
| `eager_model_load` | `AGRI_ML_EAGER_MODEL_LOAD` | `true` |
| `cors_origins` | `AGRI_ML_CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` |
| `request_id_header` | `AGRI_ML_REQUEST_ID_HEADER` | `X-Request-ID` (reserved; not yet wired into logging/responses) |
| `max_upload_bytes` | `AGRI_ML_MAX_UPLOAD_BYTES` | `10485760` (10 MB) |
| `allowed_image_mime_types` | `AGRI_ML_ALLOWED_IMAGE_MIME_TYPES` | `image/jpeg,image/png,image/webp` |
| `allowed_image_extensions` | `AGRI_ML_ALLOWED_IMAGE_EXTENSIONS` | `.jpg,.jpeg,.png,.webp` |
| `image_decode_max_pixels` | `AGRI_ML_IMAGE_DECODE_MAX_PIXELS` | `24000000` (24 MP; decompression-bomb guard) |
| `include_top_predictions` | `AGRI_ML_INCLUDE_TOP_PREDICTIONS` | `true` |
| `top_k_predictions` | `AGRI_ML_TOP_K_PREDICTIONS` | `3` (validated: `1`–`6`, the approved active class count) |

The four path settings default to `None` and are resolved lazily against
`ML_SERVICE_ROOT` (via `Settings.resolved_*_path()`) only when actually
needed — they are never required to exist just to construct `Settings`;
existence/content validation happens in `model_loader.py`. The M7 upload
settings (`allowed_image_mime_types`, `allowed_image_extensions`) reject
empty lists and wildcard entries (e.g. `image/*`) at construction time.

No secrets are read or required by this service. `ml-service/.env` is
gitignored and must never be committed; see `.env.example`.

## Startup command

```bash
cd ml-service
.venv/bin/python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Do not bind to `0.0.0.0` for this milestone.

## Endpoints

### `GET /api/health`

Confirms only that the process is running. Never depends on the model,
performs no I/O, always `HTTP 200` while the process is alive.

```json
{
  "status": "ok",
  "service": "AgriAI ML Service",
  "version": "Phase 2 development version",
  "environment": "development"
}
```

### `GET /api/ready`

Reports whether the service can serve future predictions. `HTTP 200` only
after the checkpoint, confidence policy, and class mapping have all been
validated and loaded successfully — never based on file existence alone.

Ready (`HTTP 200`):
```json
{"status": "ready", "model_loaded": true, "confidence_policy_loaded": true, "class_count": 6}
```

Not ready (`HTTP 503`):
```json
{"status": "not_ready", "model_loaded": false, "reason": "confidence policy is not approved"}
```

### `GET /api/model-info`

Safe, public model metadata only — never a checkpoint path, optimizer
state, or training file path, and never a model call.

```json
{
  "status": "available",
  "architecture": "efficientnet_b0",
  "model_version": "m4-efficientnet-b0-seed42",
  "class_count": 6,
  "classes": ["Tomato Healthy", "Tomato Early Blight", "Tomato Late Blight",
              "Potato Healthy", "Potato Early Blight", "Potato Late Blight"],
  "input": {"width": 224, "height": 224, "channels": 3},
  "confidence": {
    "method": "maximum_softmax_probability",
    "threshold": 0.5,
    "label": "model confidence",
    "production_calibrated": false
  },
  "evaluation": {
    "frozen_test_accuracy": 0.9889,
    "frozen_test_macro_f1": 0.9841,
    "dataset_context": "PlantVillage-derived controlled-image evaluation"
  },
  "limitations": [
    "The confidence score is not certainty or probability of truth.",
    "The threshold rejected no samples in the frozen test evaluation.",
    "Real-world farm-photo validation is still required.",
    "The model currently supports six Tomato and Potato classes only."
  ]
}
```

`frozen_test_accuracy`/`frozen_test_macro_f1` are cited, immutable
constants from the one-time frozen M5 test evaluation (see
`docs/MODEL_EVALUATION.md`) — not read from `confidence_policy_v1.json`,
which is deliberately validation-only, and not re-derived by re-evaluating
`test.csv` (which must not happen again). If the model is unavailable,
this endpoint returns `HTTP 503` with `{"status": "unavailable", "reason": "..."}`.

`POST /api/predict/disease` (the image upload / prediction endpoint) is
documented in **[`PREDICTION_API.md`](PREDICTION_API.md)**, not here.

## Model-loading lifecycle

`app/model_loader.py`'s `ModelLoader` loads the model **at most once per
process**, guarded by a lock so concurrent callers block on the same
initialization and observe the same final state (loaded, or failed —
never retried automatically). Validation order, all before any weights are
loaded:

1. class map / model scope files exist and parse; exactly 6 active classes.
2. confidence policy exists, parses, `status == approved_for_test_application`,
   architecture/confidence-method match, threshold is numeric.
3. checkpoint SHA-256 matches `confidence_policy_v1.json`'s `checkpoint_sha256`.
4. checkpoint's recorded architecture, `class_names`, and `class_to_index`
   match the approved active scope.
5. `EfficientNet-B0` is reconstructed via `training/model.py`'s
   `build_model()` (not duplicated), and only `model_state_dict` is loaded
   — never a pickled full model object.

Any failure produces a sanitized `ModelLoadError` message (no absolute
paths, no tracebacks, no checkpoint contents) surfaced through
`ModelLoader.failure_reason`; `/api/ready` and `/api/model-info` return
`HTTP 503` accordingly while `/api/health` stays `HTTP 200`.

## CPU/MPS behavior

`preferred_device` defaults to `auto` (prefers MPS, then CPU — unchanged
from `training/model.py`'s existing `select_device()`). On this
development machine, `auto` selects MPS and loads in well under half a
second. If MPS proves unstable for a long-running process, override with
`AGRI_ML_PREFERRED_DEVICE=cpu` — verified working (see Manual verification
below); CPU remains the safe, always-available fallback. CUDA is supported
for portability but not exercised on this machine.

## CORS

Configured only from validated settings — never `allow_origins=["*"]`
combined with credentials, and no hard-coded, unapproved deployment
domains. `allow_credentials=False` (no cookie/auth mechanism exists yet)
and `allow_methods=["GET", "POST"]` (`POST` was added in M7 for
`/api/predict/disease`; every other route remains `GET`-only).

Default allowed origins: `http://localhost:3000`, `http://127.0.0.1:3000`
(local Next.js dev server). Override via a comma-separated or JSON-array
env var:

```bash
AGRI_ML_CORS_ORIGINS=http://localhost:3000,https://staging.example.com
```

## Safe error handling

- Pydantic/FastAPI validation errors use FastAPI's standard `422` responses.
- Model-loading failures are sanitized `ModelLoadError` messages, surfaced
  as `503` with `{"status": "not_ready"|"unavailable", "reason": "..."}`.
- Any unexpected exception is caught by a global handler, logged locally
  with full detail (`logger.exception`), and returned to the client as a
  generic `HTTP 500 {"status": "error", "detail": "internal server error"}`
  — never a traceback, path, or environment variable.

## Known confidence limitations

Unchanged from M5 (see `docs/MODEL_EVALUATION.md`): the confidence score is
a model score, not a guaranteed true probability; the frozen-test threshold
(0.50) rejected zero of 991 test predictions, so thresholding alone
provided no filtering on that set; real-world field validation is still
required; this model and threshold are **not production-calibrated**, and
no production-readiness claim is made anywhere in this service.

## Status

`POST /api/predict/disease` is implemented (M7) — see
`docs/PREDICTION_API.md`. **M8 (Next.js integration) has not started.**
