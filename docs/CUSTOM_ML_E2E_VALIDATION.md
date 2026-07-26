# Custom ML End-to-End Validation — Milestone M10

## Purpose

M10 validates the complete real application flow — authenticated user →
image upload → `POST /api/analyze` → custom-ML provider adapter → FastAPI
`POST /api/predict/disease` → EfficientNet-B0 inference → normalized
response → MongoDB `Analysis` persistence → `User.analysisCount` increment
→ current-result data → history API → history after refresh — using the
real running services (real MongoDB, real FastAPI process, real trained
checkpoint), not isolated unit tests. It proves the pieces built in
M1–M9 work together, end to end. No retraining, no threshold change, no
schema redesign, no UI redesign, and no Qwen/Groq/Ollama changes were made.

## Tested architecture

```
Authenticated user (disposable local dev account, NextAuth JWT session)
  → POST /api/analyze (multipart: image, query, type=crop_disease, cropName)
       → src/app/api/analyze/route.ts
            → runDiseaseAnalysis() (custom-ml mode: DISEASE_ANALYSIS_PROVIDER=custom-ml)
                 → GET /api/ready (readiness check)
                 → POST /api/predict/disease (real EfficientNet-B0 inference, mps device)
                 → strict response validation (providers/custom-ml.ts)
            → persistence.ts: buildDiseaseAnalysisPersistenceInput (independent re-validation)
            → Analysis.create() (real MongoDB, real Docker container)
            → User.findByIdAndUpdate $inc analysisCount
       ← JSON response (result/customMl/providerMetadata/resultVersion)
  → GET /api/history (second, independent read of the same persisted data)
```

## Environment used

- **FastAPI ML service**: `.venv/bin/python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8001`, real approved checkpoint, `mps` device (Apple Silicon).
- **MongoDB**: pre-existing local Docker container `agriai-mongodb` (`mongodb/mongodb-community-server`), port 27017, already running for the project's local development (not started by this validation, not a disposable test database — it holds pre-existing project data, so cleanup was scoped precisely to records created by this validation session only).
- **Next.js**: two instances were involved. An initial instance came up against a stale/misconfigured local `MONGODB_URI` (`127.0.0.1:27017`, unreachable at the time) and was stopped. After the operator corrected `.env.local`'s `MONGODB_URI` (not read, printed, or modified by this validation — corrected by the operator directly), a dedicated instance was started on port 3002 with `CUSTOM_ML_ENABLED=true`, `DISEASE_ANALYSIS_PROVIDER=custom-ml`, `CUSTOM_ML_SERVICE_URL=http://127.0.0.1:8001`, `CUSTOM_ML_REQUIRE_READY_CHECK=true`, and `CUSTOM_ML_FALLBACK_TO_GEMINI` toggled `false`/`true` for different test sections — all via temporary shell-exported environment variables, never written to `.env.local`. The operator's own separate instance on port 3001 was left completely untouched throughout.
- **Authentication**: a disposable local development account (`m10-e2e-test@example.local`, randomly generated password never printed/logged/committed) was registered via the existing `POST /api/auth/register` route and signed in via the real NextAuth credentials flow (`/api/auth/csrf` + `/api/auth/callback/credentials`) to obtain a genuine session cookie. All requests in this document used that real, authenticated session — not a mocked auth harness. The account and all analyses it created were deleted at the end of validation (see Cleanup below).

## Integrity checks (Section 1)

| Check | Result |
|---|---|
| Branch | `phase-2-custom-disease-ml` ✅ |
| Latest commit | `a82d08f2e2c1ac75300e3acdcf91a1bb1d1db0f8` ("feat: persist and display custom ML analysis metadata") ✅ matches |
| Working tree | clean, up to date with `origin/phase-2-custom-disease-ml` ✅ |
| Model checkpoint SHA-256 | `24e7244ed2970ec3aac50be870f0de80f42d52baf30cd80b429ff67e9d001081` ✅ matches exactly (recomputed with `shasum -a 256`, and independently cross-checked against the `checkpoint_sha256` field embedded in `training/confidence_policy_v1.json`) |
| Confidence policy threshold | `selected_threshold: 0.5` ✅ |
| train/val/test manifest hashes | all three (`data/splits/{train,val,test}.csv`) recomputed and matched `data/reports/split_manifest_hashes.json` exactly ✅ |
| `.env.local` tracked? | confirmed ignored (`.gitignore:23`) and not tracked (`git ls-files`) ✅ — never read, printed, or modified by this validation |

No integrity failure — M10 proceeded.

## Runtime requirements inspected (Section 2)

No `docker-compose.yml` exists in the repository; no seed/demo-user script
exists. README documents MongoDB Atlas as the default approach, but this
machine's actual local development setup uses a local Docker MongoDB
container instead (`agriai-mongodb`) — a pre-existing environment detail
discovered during validation, not something this validation introduced.
No usable local authenticated account was known to exist in advance, so a
single disposable account was created via the existing registration flow,
as explicitly permitted.

## Real success flow (Section 8)

Four real, distinct prediction requests were made against the running
FastAPI service with the real checkpoint. All four used images verified
by SHA-256 to be exact matches for rows in `data/splits/val.csv` (never
`test.csv`):

| # | Source split | Expected class (val.csv) | Predicted class | Model confidence | accepted/uncertain | analysisId |
|---|---|---|---|---|---|---|
| 1 | val.csv | Tomato Late Blight | **Tomato Late Blight** ✅ | 0.9686 | true / false | `6a65fb3e20f4e66aa0abaeea` |
| 2 | val.csv | Potato Healthy | **Potato Healthy** ✅ | 0.99997 | true / false | `6a65fc0c20f4e66aa0abaef8` |
| 3 | val.csv | Potato Healthy (concurrent dup.) | **Potato Healthy** ✅ | 0.99997 | true / false | `6a65fc0c20f4e66aa0abaefa` |
| 4 | val.csv | Tomato Early Blight | **Tomato Early Blight** ✅ | 0.9268 | true / false | (deleted in cleanup, class/confidence recorded here) |

All four: `confidenceLabel: "model confidence"`, `productionCalibrated:
false`, `confidenceThreshold: 0.5`, `confidenceMethod:
"maximum_softmax_probability"`, `topPredictions` bounded to 3 and sorted
descending, `accepted`/`uncertain` strict logical opposites, class one of
the six approved classes. `treatment`/`prevention` for every custom-ml
result stayed disclaimer-only text (no fabricated dosage or disease-specific
claims). Every response returned `success: true` with a real `analysisId`,
and `aiProvider`/`persistedProvider` were `"custom-ml"` for all four
(single-source — no Gemini involvement in any of them, so `"combined"` was
correctly never used).

**Image #1 detail** (used as the primary example throughout this document):
`data/raw/plantvillage-source/raw/color/Tomato___Late_blight/07d7ad48-0740-4cf5-9a26-91fd9296d6b3___RS_Late.B 5464.JPG`,
16,081 bytes, 256×256 RGB JPEG, SHA-256-verified as an exact `val.csv` row.

## Persistence verification (Section 9)

Verified two independent ways for request #1 and cross-checked they were
byte-for-byte identical: (a) the immediate `/api/analyze` JSON response,
and (b) a direct `mongosh` query against the real `agriai` database inside
the `agriai-mongodb` container (`db.analyses.findOne(...)`), bypassing the
application entirely. Both showed:

- `resultVersion: 2`
- `aiProvider: "custom-ml"`
- `result.{diagnosis,severity,confidence,treatment,prevention,rawResponse}` all populated (no `expertAdvice` — correctly absent, since the result was accepted, not uncertain)
- `customMl`: approved class, confidence in range, accepted/uncertain opposite, `confidenceLabel`/`productionCalibrated`/`confidenceThreshold`/`confidenceMethod` all exact, `topPredictions` = 3 entries, `model: {architecture: "efficientnet_b0", classCount: 6}`, `limitations` present
- `providerMetadata`: `{primaryProvider: "custom-ml", persistedProvider: "custom-ml", fallbackUsed: false, secondaryOpinionUsed: false}`
- `secondaryOpinion`: absent (correct — not applicable)
- `createdAt`/`updatedAt` present
- `rawResponse` checked explicitly: contains **no** uploaded image bytes, no base64, no ML-service URL, no MongoDB URI, no stack trace, no API key, no local filesystem path — just a short human-readable summary string.
- No `imageUrl` field was set — the uploaded image itself was never persisted, matching the ml-service's documented in-memory-only image handling.

## Refresh / history verification (Section 10)

`GET /api/history` was called twice (simulating a page refresh) and
returned the same single record consistently. A **disposable synthetic
legacy-shaped document** (no `customMl`/`providerMetadata`/`resultVersion`
fields, mimicking a pre-M9 record) was inserted directly into the real
database alongside the real M9-shaped record, and `GET /api/history` was
confirmed to return **both** records correctly (200, no crash) — the
legacy record simply omits the M9 fields rather than rendering `null` or
throwing. This synthetic record was deleted immediately after the check
(see Cleanup). Actual browser rendering of `AnalysisResultCard.tsx` /
`HistoryList.tsx` against this data was **not visually verified in this
session** (no browser available) — see "Browser/UI verification status"
below for what was and wasn't covered.

## Failure / recovery verification (Section 12)

1. FastAPI stopped cleanly (`kill`, confirmed nothing listening on 8001).
2. A valid val.csv image was submitted: `503 {"success":false,"error":{"code":"ML_SERVICE_UNAVAILABLE","message":"Disease analysis is temporarily unavailable."}}` — no service URL, no stack trace.
3. Confirmed `analysisCount` unchanged (stayed at 1) and `db.analyses.countDocuments()` unchanged (stayed at 1) — no partial/failed persistence.
4. FastAPI restarted with the identical startup command; `GET /api/ready` returned 200 within ~3 seconds (model reloaded, `duration=0.406s`).
5. The same image was resubmitted and succeeded normally, persisting correctly (this is prediction #2/#3 in the table above, run as a concurrency pair — see below).

## Concurrency / duplicate-submission check (Section 15)

Two simultaneous `POST /api/analyze` requests were sent with the **same**
image (`Potato Healthy`, val.csv). Both succeeded (200), each got a
**distinct** `analysisId` (`...aef8` and `...aefa`), `analysisCount`
incremented by exactly 2 (1 → 3), and `db.analyses.countDocuments()`
correspondingly went from 1 → 3 with three distinct, uncorrupted
documents. No load/stress test was performed — this was a small, controlled
two-request check only.

## Fallback verification (Section 13) — partial, disclosed limitation

Next.js was restarted with `CUSTOM_ML_FALLBACK_TO_GEMINI=true`.

- **Infrastructure-failure fallback**: with FastAPI stopped, a valid image
  was submitted. The real Gemini SDK call was genuinely attempted (this
  environment's configured `GEMINI_API_KEY` is **invalid** — Google's API
  responded `400 API_KEY_INVALID`, visible in server-side logs only). The
  client received the generic sanitized `{"error":"Analysis failed. Please
  try again later."}` (500) — the real upstream error text (which named
  the Google API domain) was **not** leaked to the client, a valuable real
  confirmation of the M9 Section-15 sanitization fix against a genuine,
  not synthetic, upstream failure. No `Analysis` document was created
  (`analysisCount` and document count both stayed at 3).
- Because Gemini credentials are invalid in this environment, the
  **successful** infra-fallback-to-Gemini path (persisted `aiProvider:
  "gemini"`, honest `providerMetadata`, no fabricated `customMl`) and the
  **uncertain + secondary-opinion** combined path (persisted `aiProvider:
  "combined"`, `customMl` remaining uncertain, `secondaryOpinion`
  persisted) were **not exercised live end-to-end** in this session. Per
  the M10 instructions, this does not block M10: both scenarios are
  already covered by the existing automated test suite with mocked Gemini
  responses and a real orchestration/persistence code path —
  `src/lib/disease-analysis/service.test.ts` ("falls back on...", "falls
  back with fallbackReason 'service_not_ready'", uncertain-prediction
  tests), `src/app/api/analyze/route.test.ts` ("persists to Mongo as
  'gemini' when an infrastructure fallback...", "persists as 'combined'
  only when custom-ml (uncertain) AND a Gemini secondary opinion both
  contributed"), and `src/lib/disease-analysis/persistence.test.ts`
  (`buildProviderMetadata`/`buildDiseaseAnalysisPersistenceInput` for both
  scenarios) — all passing (see Automated regression below).

## Invalid-input verification (Section 14)

All four cases tested through the real, running, authenticated route:

| Input | Expected | Observed | Persisted? | analysisCount changed? |
|---|---|---|---|---|
| Unsupported `.txt` file | `415 UNSUPPORTED_MEDIA_TYPE` | ✅ exact match | No | No |
| Corrupt image (random bytes, `.jpg` name/MIME) | `400 INVALID_IMAGE` | ✅ exact match | No | No |
| Oversized file (~11 MB, limit 10 MB) | `413 IMAGE_TOO_LARGE` | ✅ exact match | No | No |
| Unauthenticated request | `401 Unauthorized` | ✅ exact match | No | No |

None of the three 4xx cases ever attempted a Gemini fallback (verified
against an instance running with `CUSTOM_ML_FALLBACK_TO_GEMINI=true`,
which made this a stronger check than testing with fallback disabled — a
bug that mistakenly fell back on a 4xx would have surfaced as the same
invalid-Gemini-key 500 seen in the fallback section above, and it did
not). FastAPI's own `GET /api/health` was confirmed still `200` after this
sequence.

## Uncertain-result verification (Section 11) — disclosed limitation

All four real predictions made in this session were **accepted**
(confidences 92.7%–100%); none was naturally uncertain. This is
consistent with the frozen M5 test evaluation, which rejected 0 of 991
test-set predictions at the 0.50 threshold (cited in
`GET /api/model-info`'s own limitations). Per instructions, no uncertain
case was forced and `test.csv` was never used to search for one. Real
uncertain-result E2E behavior (visible "Low-confidence model result"
warning, optional Gemini secondary opinion, `combined` persistence) was
**not naturally observed** in this session and is verified instead via
the existing automated test suite (`service.test.ts`'s "uncertain
predictions" describe block, `route.test.ts`'s uncertain-outcome tests,
`persistence.test.ts`'s secondary-opinion tests, and
`AnalysisResultCard.test.tsx`/`HistoryList.test.tsx`'s uncertain-badge
tests) — all passing.

## Browser/UI verification status

**Not performed in this session**: visual browser rendering of
`AnalysisResultCard.tsx`/`HistoryList.tsx` against the real data produced
above (no browser tool was available). What **was** verified: (a) the
exact JSON shapes these components consume were produced correctly by the
real running application and real database (see Persistence and
Refresh/history sections above), and (b) the M9-era React Testing
Library component tests (`AnalysisResultCard.test.tsx`,
`HistoryList.test.tsx`) already assert the specific rendering behaviors
(provider badge, accepted/uncertain wording, top predictions, safety
notes, fallback/secondary-opinion notes, legacy-record safety) against
this same data shape, and all pass. This is disclosed as a real limitation
rather than claimed as fully verified.

## Performance observations (not a benchmark)

| Request | preprocessing_ms | inference_ms | Notes |
|---|---|---|---|
| #1 (Tomato Late Blight) | 5.7 | 273.7 | First request after a fresh restart |
| #2 (Potato Healthy) | 0.9 | 213.9 | Concurrent pair, steady-state |
| #3 (Potato Healthy) | 1.1 | 214.1 | Concurrent pair, steady-state |
| #4 (Tomato Early Blight) | 0.6 | 202.7 | Steady-state |

One full round trip (curl `time_total`, request #4, including the
readiness check, the FastAPI call, and the MongoDB persist) measured
**224 ms** end to end. Model load at each FastAPI startup: 0.406–0.417 s
on the `mps` device. These are single-machine, single-session
observations, not a formal benchmark, and no stress/load testing was
performed.

## Security and privacy review (Section 18)

- All client-facing response bodies captured during this validation were
  scanned for MongoDB connection strings, API keys, the ML-service URL,
  absolute filesystem paths, and stack traces — **none found**.
- A genuine real-world upstream failure occurred during fallback testing
  (an actual invalid-Gemini-API-key rejection from Google's API) and was
  confirmed **not** to leak into the client response — real evidence for
  the M9 Section-15 sanitization fix, not just a synthetic test case.
- `.env.local` remained ignored and untracked throughout; its contents
  were never read, printed, or modified by this validation session (the
  operator corrected `MONGODB_URI` directly).
- No temporary uploaded files remain in the repository — all test images
  used were existing dataset files (read-only), and synthetic invalid
  files (`.txt`, corrupt/oversized images) were created only in the
  session scratchpad directory (outside the repository) and deleted
  after use.
- `git status` was clean throughout and remained clean at the end of
  validation.

## Cleanup performed (Section 19)

- The disposable account (`m10-e2e-test@example.local`) and all 4
  `Analysis` documents it created were deleted directly from the real
  database after validation was complete (`deleteMany`/`deleteOne`
  scoped exactly to that account's `userId`/`email` — confirmed via a
  `remaining analyses: 0` / `remaining users: 1` check that this did not
  touch the one pre-existing user or any pre-existing analysis data).
- The one synthetic legacy-record document used for the history-safety
  check was deleted immediately after that check.
- Both processes this validation started (a Next.js dev instance on port
  3002, and the FastAPI ML service on port 8001) were stopped cleanly at
  the end. The operator's own separate Next.js instance (port 3001) and
  the pre-existing `agriai-mongodb` Docker container (port 27017) were
  left running, untouched, exactly as found.
- Final port check: nothing listening on 3000, 3002, or 8001; 3001
  (operator's instance) and 27017 (pre-existing MongoDB container)
  remained, as intended.

## Automated regression results (Section 20)

| Check | Result |
|---|---|
| `npx vitest run` | **165/165 passed**, 9 test files |
| `npx tsc --noEmit` | clean, zero errors |
| `npm run lint` | clean, zero warnings |
| `npm run build` | succeeds, all 16 routes compile |
| `cd ml-service && python3 -m pytest -q` | **177/177 passed** |

## Defects found and fixed

**None.** No integration defect was discovered in application code during
M10. Two environment-level issues were encountered and are documented as
environment facts, not code defects (per Section 21, environment/config
mismatches are explicitly distinguished from application bugs):

1. This machine's local `MONGODB_URI` initially pointed at an unreachable
   `127.0.0.1:27017` before a local `agriai-mongodb` Docker container was
   started and `.env.local` was corrected by the operator.
2. This environment's `GEMINI_API_KEY` is invalid, which limited live
   verification of the Gemini-involving fallback/secondary-opinion paths
   (see "Fallback verification" above for how this was otherwise covered).

No code, tests, schema, model, or configuration files were modified as
part of M10 — this validation was purely observational.

## Known limitations

- Full authenticated **browser** UI rendering was not visually verified (no browser tool available) — verified instead via real API/DB data shape checks plus existing RTL component tests.
- Live Gemini-involving fallback and uncertain+secondary-opinion paths were not exercised end-to-end (invalid API key in this environment) — verified instead via the existing automated test suite.
- No natural uncertain-confidence result was observed among the 4 real predictions made (consistent with the frozen evaluation's 0-rejection result) — uncertain-flow behavior verified via existing automated tests only.
- Performance figures are single-session observations on one development machine, not a formal benchmark.

## Status

M10 real end-to-end validation is complete, with the disclosed limitations
above. **M11 (final documentation / sign-off) has not started.**
