# Prediction API — Milestone M7

## Purpose

M7 adds the first real model-inference endpoint on top of the M6 service
foundation: `POST /api/predict/disease`. It accepts one uploaded leaf image,
validates and preprocesses it exactly as M4's validation/inference
pipeline, runs the already-loaded, frozen EfficientNet-B0 checkpoint, and
returns a structured prediction using the frozen, validation-selected
confidence threshold (0.50). **There is no upload persistence, no
prediction history, no Gemini fallback, no treatment recommendations, and
no Next.js integration in M7** — M8 has not started.

## Endpoint

```
POST /api/predict/disease
```

Multipart field name: **`file`** (exactly one image; multiple files, URLs,
base64 JSON, ZIPs, videos, PDFs, and arbitrary binaries are all rejected).

### Supported image types

| Extension | MIME type |
|---|---|
| `.jpg`, `.jpeg` | `image/jpeg` |
| `.png` | `image/png` |
| `.webp` | `image/webp` |

Both the extension **and** the declared `Content-Type` must be in the
allowed set, **and** the actual decoded image content must match the
declared MIME type (a PNG declared as `image/jpeg` is rejected) — MIME
type and extension are never trusted alone.

### Maximum file size

10 MB by default (`AGRI_ML_MAX_UPLOAD_BYTES`). The upload is read in
bounded chunks and rejected as soon as the limit is exceeded, without
buffering an arbitrarily large body into memory first.

## Request example

```bash
curl -X POST http://127.0.0.1:8001/api/predict/disease \
  -F "file=@leaf.jpg;type=image/jpeg"
```

## Success response (accepted)

```json
{
  "status": "success",
  "prediction": {
    "class_name": "Potato Early Blight",
    "class_index": 4,
    "model_confidence": 0.9995086193084717,
    "accepted": true,
    "uncertain": false,
    "message": null
  },
  "top_predictions": [
    {"class_name": "Potato Early Blight", "class_index": 4, "model_confidence": 0.9995086193084717},
    {"class_name": "Tomato Early Blight", "class_index": 1, "model_confidence": 0.0003370455524418503},
    {"class_name": "Potato Late Blight", "class_index": 5, "model_confidence": 0.00010144973930437118}
  ],
  "confidence_policy": {
    "method": "maximum_softmax_probability",
    "threshold": 0.5,
    "label": "model confidence",
    "production_calibrated": false
  },
  "input": {"filename": "leaf.jpg", "content_type": "image/jpeg", "width": 256, "height": 256},
  "timing_ms": {"preprocessing": 0.56, "inference": 182.67, "total": 185.08},
  "limitations": [
    "The confidence score is not certainty or probability of truth.",
    "The threshold rejected no samples in the frozen test evaluation.",
    "Real-world farm-photo validation is still required.",
    "The model currently supports six Tomato and Potato classes only."
  ]
}
```

This is an actual response from real-model manual verification against a
`val.csv` image (see below) — not a hypothetical example.

## Uncertain response

Still `HTTP 200` — an uncertain prediction is a normal, expected outcome,
not an error. `accepted` and `uncertain` are always logical opposites
(enforced at the schema level).

```json
{
  "status": "success",
  "prediction": {
    "class_name": "Tomato Late Blight",
    "class_index": 2,
    "model_confidence": 0.41,
    "accepted": false,
    "uncertain": true,
    "message": "The model confidence is below the configured threshold."
  }
}
```

## Validation errors

| Status | Cause |
|---|---|
| `400` | empty file, no filename, malformed/corrupt/truncated image, MIME/content mismatch, animated image, invalid or excessive dimensions |
| `413` | upload exceeds `max_upload_bytes` |
| `415` | unsupported file extension or declared MIME type |
| `503` | model / confidence policy not loaded or unavailable |
| `500` | unexpected inference failure (sanitized — no traceback, path, or internal detail) |

Every error response has the same shape: `{"status": "error", "detail": "<safe message>"}`.

## Confidence-policy meaning and safety wording

- `model_confidence` is the model's own maximum softmax probability — **a
  model score, not a guaranteed true probability or certainty.**
- `accepted` means `model_confidence >= 0.50` (the frozen, validation-only
  selected threshold from `training/confidence_policy_v1.json`); `uncertain`
  is its exact logical opposite. The threshold can never be overridden by a
  request — it is read once from the loaded, validated model metadata.
- On the frozen M5 test set, this threshold **rejected zero of 991
  predictions** — it provided no actual filtering there (see
  `docs/MODEL_EVALUATION.md`). It is **not production-calibrated**, and no
  production-readiness claim is made.
- The field is always labeled `"model confidence"`, never `"certainty"` or
  `"probability of truth"` — enforced at the schema type level.

## Six supported classes

Tomato Healthy, Tomato Early Blight, Tomato Late Blight, Potato Healthy,
Potato Early Blight, Potato Late Blight — identical order and content to
`GET /api/model-info`'s `classes` field (both are populated from the same
loaded, validated model metadata; see "Model-info alignment" below).

## Preprocessing pipeline

Reconstructs the exact M4 validation transform (see `app/preprocessing.py`):

1. Decode with Pillow (in memory only).
2. Apply EXIF orientation correction.
3. Convert to RGB (grayscale/RGBA and other modes are converted after decode).
4. `Resize(256)` → `CenterCrop(224)` → `ToTensor()` → ImageNet normalization.

No training-time augmentation (random crop/flip/rotation/color-jitter) is
used at inference time. At startup, `app/model_loader.py` cross-validates
the loaded checkpoint's own recorded `preprocessing_config` against these
exact constants and refuses to start serving predictions if they ever
disagree (the same check `training/evaluate.py` performs at M5 evaluation
time).

## No upload persistence

Uploaded images are processed entirely in memory (`io.BytesIO`) and are
never written to disk, logged, or retained after the request completes.
Filenames are treated as display-only metadata — sanitized (control
characters stripped, length capped, path components discarded) and never
used to construct a filesystem path.

## CPU/MPS behavior

`preferred_device` (see `docs/API_FOUNDATION.md`) governs both model
loading and inference — the same device is used throughout a process's
lifetime; there is no per-request device switch. On MPS, timing is measured
with an explicit `torch.mps.synchronize()` immediately after the forward
pass (MPS ops are asynchronous by default, so timing without it would only
measure kernel-launch time). CPU is the always-available fallback and is
exercised by the automated test suite; MPS is exercised by manual
verification below.

## Local startup

```bash
cd ml-service
.venv/bin/python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

## Manual verification results (real checkpoint, 2026-07-26)

Source split used: **`val.csv` only** (never `test.csv`, which must not be
touched again after its one-time M5 evaluation). Device: `mps` (auto-selected).

| Check | Result |
|---|---|
| `GET /api/health` | 200 |
| `GET /api/ready` | 200, `class_count: 6` |
| `GET /api/model-info` | 200, 6 classes, threshold 0.5 |
| `POST /api/predict/disease` (val.csv Potato Early Blight image) | 200, predicted **Potato Early Blight**, confidence **0.99951**, `accepted: true` — matches the M5 validation-run prediction for the same image exactly |
| Corrupt non-image file | 400, sanitized message |
| Unsupported extension (`.txt`) | 415, sanitized message |
| Service health after invalid requests | still 200 |
| Clean shutdown (`SIGTERM`) | logged shutdown, process exited |

### Performance sample (7 sequential `val.csv` requests, MPS, single MacBook Air process)

| Image bytes | Preprocessing (ms) | Inference (ms) | Total (ms) |
|---:|---:|---:|---:|
| 18,355 | 0.64 | 14.73 | 17.16 |
| 19,477 | 0.33 | 12.90 | 14.39 |
| 19,419 | 0.36 | 13.18 | 14.70 |
| 18,648 | 0.33 | 12.67 | 14.13 |
| 18,757 | 0.34 | 8.27 | 9.75 |
| 19,755 | 0.35 | 8.17 | 9.94 |
| 19,572 | 0.34 | 8.10 | 9.49 |

The very first request in a freshly started process took noticeably longer
(preprocessing 0.5ms, inference ~1.45s) — an MPS kernel warm-up/compilation
cost paid once per process, not per request; the table above reflects
steady-state timings after warm-up. **This is a single-machine, sequential,
7-request sample — not a benchmark.** No load testing was performed.

## Known limitations

- Model confidence is a score, not certainty or probability of truth.
- The frozen threshold (0.50) rejected zero of 991 frozen-test predictions
  — it is not proven to filter anything on harder or out-of-distribution
  images.
- Real-world farm-photo validation has not been performed; all evaluation
  to date is PlantVillage-derived, controlled-image data.
- Only six Tomato/Potato classes are supported; Corn is excluded (see
  `docs/DATASET_PROVENANCE.md`).
- Not production-calibrated; no production-readiness claim is made.

## Status

**M8 connected this endpoint to the Next.js app** behind a server-side
feature flag (default: disabled, Gemini remains primary). See the Next.js
repo's `docs/CUSTOM_ML_INTEGRATION.md` for the consumer-side integration,
provider-selection matrix, and fallback policy.
