# Phase 2 — Custom Crop-Disease ML (Authoritative Overview)

**Status: M1–M10 complete. M11 (this document + final sign-off) in progress.**
This is the single authoritative Phase 2 overview — for deep detail on any
one milestone, follow the links in each section rather than duplicating
that detail here.

## 1. Problem solved

AgriAI's original crop-disease-detection flow relied entirely on a
third-party vision model (Google Gemini) to diagnose plant diseases from a
photo. Phase 2 adds AgriAI's **own** trained image classifier as an
alternative, feature-flagged diagnosis provider — giving the application a
disease-detection path that does not depend on an external vendor's model,
while keeping Gemini fully available as a default and as a fallback.

## 2. Original AgriAI disease-analysis flow

Before Phase 2: `CropScanner.tsx` → `POST /api/analyze` → Gemini Vision
(image + text prompt) → a parsed, fixed result shape (`diagnosis`,
`severity`, `confidence`, `treatment`, `prevention`, `expertAdvice`,
`rawResponse`) → `Analysis.create()` in MongoDB → `GET /api/history`. This
flow is **unchanged** for every request that doesn't use the custom-ml
provider — Phase 2 is additive, not a replacement.

## 3. Why a custom ML model was added

- Independence from a single external vision-model vendor for the specific, well-scoped case of six common Tomato/Potato conditions.
- A reproducible, versioned, locally-evaluated model with documented accuracy/limitations, rather than an opaque third-party API.
- A foundation for future, more specialized agricultural ML work — while staying strictly scoped to image classification only in Phase 2 (see [Out of scope](#24-future-work)).

## 4. Phase 2 architecture

```
Authenticated user
  └─ CropScanner.tsx (upload photo, crop_disease type)
       └─ POST /api/analyze  (Next.js, src/app/api/analyze/route.ts)
            ├─ type ≠ crop_disease, or provider = groq, or no image
            │    → existing Gemini/Groq paths (100% unchanged)
            └─ type = crop_disease + image
                 └─ getDiseaseAnalysisConfig() → provider = "gemini" | "custom-ml"
                      ├─ "gemini"    → existing Gemini Vision path (unchanged)
                      └─ "custom-ml" → runDiseaseAnalysis()
                           ├─ GET  {CUSTOM_ML_SERVICE_URL}/api/ready   (optional)
                           ├─ POST {CUSTOM_ML_SERVICE_URL}/api/predict/disease
                           │    └─ FastAPI (ml-service/) → EfficientNet-B0 inference
                           ├─ strict response validation (never trust upstream blindly)
                           ├─ fallback policy (infra failures only, never for 4xx)
                           └─ optional Gemini secondary opinion (only if primary is uncertain)
            → persistence.ts: independent re-validation + shape-building
            → Analysis.create() (MongoDB) + User.analysisCount increment
       ← JSON response (result / customMl / providerMetadata / secondaryOpinion / resultVersion)
  └─ GET /api/history (same fields, read back for the history list)
```

Two independently-runnable services: the **Next.js app** (this repo's
root) and the **FastAPI ml-service** (`ml-service/`, a separate Python
process on port 8001). MongoDB is a third, external dependency (local
Docker container or MongoDB Atlas).

## 5. Six supported classes

| Class | Crop | Condition | Healthy? |
|---|---|---|---|
| Tomato Healthy | Tomato | Healthy | ✅ |
| Tomato Early Blight | Tomato | Early Blight | ❌ |
| Tomato Late Blight | Tomato | Late Blight | ❌ |
| Potato Healthy | Potato | Healthy | ✅ |
| Potato Early Blight | Potato | Early Blight | ❌ |
| Potato Late Blight | Potato | Late Blight | ❌ |

Corn (2 further PlantVillage classes) was **explicitly excluded** from this
first model — no authoritative physical-leaf grouping metadata exists for
Corn, so a defensible leakage-free split could not be produced for it (see
[Dataset grouping/leakage strategy](#7-dataset-groupingleakage-strategy)).
Any other class name is never silently accepted anywhere in the stack
(`isApprovedClassName` on the Next.js side, `model_scope_v1.json` on the
ml-service side).

## 6. Dataset source and licence restrictions

Source: a PlantVillage-derived image set (via the AIcrowd/crowdAI plant
disease challenge mirror), treated as **CC BY-SA 3.0** per that source's
explicit statement. See `ml-service/docs/DATASET_PROVENANCE.md`'s
"Licence and usage restrictions" section for the full citation chain and
attribution requirements. These are **controlled, lab-style leaf-on-plain-
background images** — not real farm-field photographs (see
[Limitations](docs/CUSTOM_ML_LIMITATIONS.md)).

## 7. Dataset grouping/leakage strategy

The core risk in this dataset is that the same physical leaf (or plant)
was sometimes photographed multiple times, producing near-duplicate images
that must never be split across train/validation/test — otherwise a model
could "memorize" a leaf it saw in training and appear to generalize on a
validation/test image that is actually the same leaf. Phase 2's grouping
strategy (Milestone M3):

1. **Exact-duplicate detection** (SHA-256): 14 exact duplicate images found and excluded from double-counting.
2. **Authoritative leaf-ID recovery**: an internal `leaf-map.json`-style mapping recovered a physical-leaf group ID for the large majority of images.
3. **Approved filename-family rules** (Tomato only, human-reviewed and explicitly approved): images with no leaf-ID match but a clear, documented filename pattern (e.g. `GH_HL Leaf 434.JPG`) were grouped by that pattern instead — never a blind heuristic, and never a "singleton fallback."
4. **Quarantine for the rest**: any image in an active-scope class (Tomato/Potato) that had neither a leaf-ID match nor an approved filename rule was **excluded from all three splits** entirely (4 images total) rather than guessed at.
5. **Corn excluded from active scope entirely** — no leaf-ID or filename signal existed for either Corn class (2,354 images), so no split could be produced without an unacceptable leakage risk.
6. **Similarity guards**: approved near-duplicate clusters (perceptual-hash) that couldn't be resolved to an authoritative group were kept confined to a single split, never split across train/val/test.
7. **Independent, read-only re-validation** (`training/validate_splits.py`, Milestone M3B-4): re-derives every image's expected class/group/guard assignment from source evidence and compares it against the committed manifests — **70/70 checks passed, zero blocking failures**, zero cross-split overlap of any kind (file path, SHA-256, leaf-ID group, or guard group).

Full detail, decision-by-decision: `ml-service/docs/DATASET_PROVENANCE.md`.

## 8. Train/validation/test counts

| Split | Rows |
|---|---:|
| train.csv | 4,642 |
| val.csv | 1,001 |
| test.csv | 991 |
| **Total** | **6,634** |

Manifest SHA-256 (frozen, re-verified during this M11 audit):

| Manifest | SHA-256 |
|---|---|
| train.csv | `3bec912c0efb7a22eb66b388c364be6ab784ce3e8637ffe716c0804655b99a79` |
| val.csv | `85f86dec9e81566b19d0654559f6b56c11d4b7086f3d5b8d244e00cae91dd91f` |
| test.csv | `3d0ee43d9edc836eefadb71bf178d55d3e60817053efa5f9f5a52cd04c284abb` |

These CSVs themselves are **gitignored** — a developer regenerates them
locally from the raw dataset via `training/build_splits.py` (see the
[Runbook](CUSTOM_ML_RUNBOOK.md)) and can independently confirm these exact
hashes result.

## 9. Model architecture and training method

**EfficientNet-B0** (transfer learning, ImageNet-pretrained backbone) fine-tuned
for 6-class classification. Deterministic training (fixed seed 42),
validation-only model/checkpoint selection (the epoch with the best
validation metric was kept — `test.csv` was never loaded during training,
not even for early stopping). See `ml-service/docs/MODEL_TRAINING.md` for
the full training configuration, reproducibility guarantees, and the
Python-3.13/arm64 dependency-version compatibility note.

## 10. Validation and frozen-test metrics

The frozen test evaluation (Milestone M5) is a **one-time**, explicitly-
confirmed final evaluation against `test.csv` — never re-run to "improve"
a result, and gated behind a `--confirm-final-test-evaluation` flag in
`training/evaluate.py` specifically so it can't happen by accident:

| Metric | Value |
|---|---|
| Frozen test accuracy | **0.9889** |
| Frozen test macro-F1 | **0.9841** |
| Test samples | 991 |
| Checkpoint SHA-256 | `24e7244ed2970ec3aac50be870f0de80f42d52baf30cd80b429ff67e9d001081` |

Full per-class metrics, confusion matrix, and bootstrap confidence
intervals: `ml-service/docs/MODEL_EVALUATION.md`.

## 11. Confidence policy and limitations

- **Selected threshold: 0.50** — the *lowest* candidate on a predeclared 0.50–0.99 grid, selected using **validation predictions only** (`test.csv` labels were never read during threshold selection — `confidence_policy_v1.json`'s own `test_labels_used_for_threshold_selection: false` field records this).
- **Status: `approved_for_test_application`.**
- At this threshold, the frozen test evaluation **rejected zero of 991 predictions** (100% coverage) — meaning, on this specific controlled dataset, thresholding provided no additional filtering beyond the model's raw predictions.
- **`production_calibrated: false`**, always — no production-readiness claim is made anywhere in this project.
- Softmax confidence is a **model score**, not a calibrated probability of truth — see [`CUSTOM_ML_LIMITATIONS.md`](CUSTOM_ML_LIMITATIONS.md) for the specific case where one incorrect frozen-test prediction still carried confidence near 1.0.

## 12. FastAPI endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/health` | GET | Process-liveness only; never touches the model |
| `/api/ready` | GET | Model loaded + confidence policy loaded; used by the Next.js adapter's optional readiness check |
| `/api/model-info` | GET | Architecture, class list, confidence-policy summary, frozen evaluation context, limitations |
| `/api/predict/disease` | POST | The real inference endpoint — multipart image upload, in-memory only, returns the normalized prediction |

Full request/response contracts: `ml-service/docs/API_FOUNDATION.md`
(foundation/health/ready/model-info) and
`ml-service/docs/PREDICTION_API.md` (prediction contract, validation
errors, confidence-policy wording, six-class list, preprocessing).

## 13. Next.js integration flow

`src/lib/disease-analysis/` is the integration boundary:

- `config.ts` — validated, server-side-only feature-flag configuration (fails fast on an inconsistent combination rather than silently misbehaving).
- `providers/custom-ml.ts` — the FastAPI adapter. Never trusts an upstream response without strict validation (approved class name, confidence in `[0,1]`, threshold exactly 0.5, `accepted`/`uncertain` strict opposites, etc.) — any deviation is treated as a malformed upstream response, never partially accepted.
- `providers/gemini.ts` — the pre-existing Gemini response-text parser, moved here unchanged.
- `service.ts` — provider selection + the fallback/uncertain-secondary-opinion policy.
- `persistence.ts` — independently **re-validates** everything again at the MongoDB-write boundary (defense in depth — never assumes the adapter's validation alone is sufficient) and builds the exact shape persisted and returned.
- `types.ts` — shared types used by all of the above, and by the Mongoose schema and UI components (single source of truth for field names/shapes).

## 14. Provider feature flags

| Variable | Default | Meaning |
|---|---|---|
| `DISEASE_ANALYSIS_PROVIDER` | `gemini` | `"gemini"` or `"custom-ml"` |
| `CUSTOM_ML_ENABLED` | `false` | Master kill-switch; must be `true` for `custom-ml` to be accepted |
| `CUSTOM_ML_SERVICE_URL` | `http://127.0.0.1:8001` | ml-service base URL |
| `CUSTOM_ML_REQUEST_TIMEOUT_MS` | `15000` | Per-request timeout (1,000–120,000) |
| `CUSTOM_ML_FALLBACK_TO_GEMINI` | `true` | Infra-failure fallback (never for user-caused 4xx) |
| `CUSTOM_ML_REQUIRE_READY_CHECK` | `true` | Checks `/api/ready` before each prediction (short in-memory TTL cache) |

Setting `DISEASE_ANALYSIS_PROVIDER=custom-ml` with `CUSTOM_ML_ENABLED=false`
is a **configuration error** the app refuses to start with, rather than
silently falling back to Gemini or silently ignoring the flag.

## 15. Gemini fallback behavior

Fallback to Gemini triggers **only** for infrastructure failures: service
unreachable, timeout, not-ready, upstream 5xx, or a malformed upstream
response. It **never** triggers for user-caused 4xx (`INVALID_IMAGE`,
`IMAGE_TOO_LARGE`, `UNSUPPORTED_MEDIA_TYPE`) — those propagate as their
specific HTTP status regardless of the fallback flag. Separately, an
**uncertain** (not failed) custom-ml result can optionally trigger a
Gemini **secondary opinion** — the primary uncertain result is never
replaced or silently confirmed by it; the two are always kept in clearly
separate fields (`customMl` stays the primary/uncertain result,
`secondaryOpinion` is additive and explicitly labelled non-confirming).

## 16. MongoDB persistence schema

`Analysis` documents additively carry, alongside the pre-existing legacy
fields (`diagnosis`/`severity`/`confidence`/`treatment`/`prevention`/
`expertAdvice`/`rawResponse`):

- `customMl` — only present when the classifier actually produced a valid result (className, classIndex, crop/condition/healthy, modelConfidence, accepted/uncertain, confidence policy fields, bounded topPredictions, model info, limitations).
- `providerMetadata` — single-source-of-truth provenance (`primaryProvider`, `persistedProvider`, fallback details, `secondaryOpinionUsed`). `"combined"` is used **only** when a secondary opinion genuinely attached.
- `secondaryOpinion` — bounded, capped Gemini text, present only when applicable.
- `resultVersion` — `2` for documents written with this schema; **absent** (never backfilled) on older documents, which remain valid and readable as-is.

Full field-by-field reference, including the independent re-validation
rules enforced at the persistence boundary:
[`CUSTOM_ML_RESULT_SCHEMA.md`](CUSTOM_ML_RESULT_SCHEMA.md).

## 17. Current-result and history behavior

The immediate `/api/analyze` response and the `GET /api/history` response
use **identical field names** for the same concepts — no
`modelConfidence`/`model_confidence`-style drift between the two.
`AnalysisResultCard.tsx` (current result) and `HistoryList.tsx` (history)
share rendering logic via `custom-ml-shared.tsx`: a provider badge, the
predicted class, crop/condition, a healthy/disease indicator, model
confidence, an accepted/uncertain badge (uncertain always shows a visible
"Low-confidence model result" warning — never phrased as a confirmed
diagnosis), the confidence threshold, up to 3 top predictions, a fixed
safety-limitations block, and an honest fallback/secondary-opinion note.
Legacy records (no M9 fields) render safely without crashing.

## 18. Security controls

- The custom-ml adapter never sends a class label or threshold to the ML service, and never includes the ML service's URL in any client-facing error.
- Every upstream ml-service response is strictly validated before being trusted; a deviation fails closed (`ML_UPSTREAM_INVALID_RESPONSE`), never partially accepted.
- Persistence-boundary re-validation is independent of the provider adapter's own validation (defense in depth).
- The outer catch-all in `route.ts` never interpolates a raw caught error's message into the client response (fixed in M9 — verified in M10 against a genuine real upstream failure, not just a synthetic test).
- No uploaded image is ever persisted to MongoDB or written to disk by the ML service (in-memory processing only).
- `.env.local`/`ml-service/.env` are gitignored and were never read, printed, or modified by any Phase 2 milestone's automated work.

## 19. Real M10 end-to-end verification

M10 ran the complete flow against **real** services (real MongoDB, real
FastAPI process with the real checkpoint, a real authenticated NextAuth
session) — not mocks. 4/4 real predictions on `val.csv` images matched
their expected class exactly; persistence, history, refresh, failure/
recovery, concurrency, and invalid-input handling were all verified
against the real stack. Full results and disclosed limitations (no
browser-visual check, Gemini fallback not live-verified due to an invalid
local credential, no naturally uncertain result observed, informal
performance numbers): [`CUSTOM_ML_E2E_VALIDATION.md`](CUSTOM_ML_E2E_VALIDATION.md).

## 20. Known limitations

See [`CUSTOM_ML_LIMITATIONS.md`](CUSTOM_ML_LIMITATIONS.md) for the full,
categorized list (dataset, metrics, confidence, system, safety). In brief:
controlled-image dataset (not real farm photos), six classes only, no
production calibration, no live-verified Gemini fallback path, no real
browser visual check, and no cloud deployment.

## 21. Local startup instructions

Full step-by-step instructions: [`CUSTOM_ML_RUNBOOK.md`](CUSTOM_ML_RUNBOOK.md).
Summary:

```bash
# Terminal 1 — ML service
cd ml-service
source .venv/bin/activate
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001

# Terminal 2 — Next.js (custom-ml mode)
# .env.local: CUSTOM_ML_ENABLED=true, DISEASE_ANALYSIS_PROVIDER=custom-ml
npm run dev
```

## 22. Test commands

```bash
# Frontend
npm test            # vitest — 165 tests, 9 files
npx tsc --noEmit     # TypeScript, no errors
npm run lint         # ESLint, no warnings
npm run build        # production build

# ML service
cd ml-service && source .venv/bin/activate
python -m pytest -q                              # 177 tests
python -m py_compile app/*.py app/routes/*.py training/*.py
python training/validate_splits.py               # read-only, 70/70 checks
```

## 23. Output/checkpoint storage rules

The model checkpoint, dataset images, split manifests, training/evaluation
run outputs, and all generated reports are **never committed** —
`ml-service/data/`, `ml-service/models/`, and `*.pt` are gitignored. A
developer regenerates or obtains them locally per the
[Runbook](CUSTOM_ML_RUNBOOK.md). Only the small, human-reviewed policy/
decision files that define *how* the dataset is scoped and split
(`model_scope_v1.json`, `tomato_grouping_policy_v1.json`,
`similarity_guards_v1.json`, `confidence_policy_v1.json`,
`class_map.json`) are tracked in Git — these are configuration/decision
records, not generated data.

## 24. Future work

Explicitly out of Phase 2 scope (unchanged from the original Phase 2
plan): pest detection, soil ML models, weather advisory, disease-risk
prediction, crop calendar, voice assistant, RAG, offline PWA, feedback/
correction loops, automatic retraining, IoT features, Corn re-inclusion
(pending better grouping metadata), and any cloud deployment of the
ML service. These are candidates for a future phase, not this one.

## 25. Phase 2 does not establish production readiness

**Phase 2 is a working, tested, end-to-end-validated feature — it is not a
production-readiness claim.** The model has not been evaluated on real
farm-field photographs, the confidence threshold is not production-
calibrated, only six classes are supported, the Gemini-fallback and
uncertain-secondary-opinion paths were not live-verified end-to-end in
M10, and no cloud deployment has been performed. See
[`CUSTOM_ML_LIMITATIONS.md`](CUSTOM_ML_LIMITATIONS.md) for the complete,
honest list. Any real agricultural decision should still involve expert
human verification.
