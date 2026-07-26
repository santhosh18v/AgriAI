# Custom ML Integration — Milestone M8 (+ M9 persistence/UI update)

## Purpose

M8 connects the existing Next.js `POST /api/analyze` disease-analysis flow
to the custom FastAPI ML service (`ml-service/`, Phase 2 M1–M7) behind a
server-side-only feature flag. The existing Gemini-based flow is preserved
completely — nothing is removed, and the custom ML provider is strictly
additive, scoped to crop-disease image analysis only.

> **M9 update:** the sections below on response shape, MongoDB
> persistence, and fallback reasons describe the **M8-era** state and are
> kept for architecture/flow context. The current persisted/response
> schema (dedicated `customMl`/`providerMetadata`/`secondaryOpinion`/
> `resultVersion` fields, and the updated crop-scanner/history UI) is
> documented in **[`CUSTOM_ML_RESULT_SCHEMA.md`](CUSTOM_ML_RESULT_SCHEMA.md)**
> — that document is authoritative for the current schema; treat any
> conflict between it and the M8 sections below in favor of that doc.

**Persistence note (pre-commit correction):** the initial M8 pass skipped
MongoDB persistence entirely for custom-ml-sourced results, because the
`Analysis.aiProvider` enum only permitted `gemini`/`groq`/`combined`. A
pre-commit review identified this as a regression (every other analysis
type is always saved to history) and applied the smallest honest fix:
`"custom-ml"` was added to the existing enum (`src/models/Analysis.ts`),
and every completed analysis — custom-ml included — is now persisted
exactly like every other provider. This is a minimal compatibility
extension, **not** the broader M9 schema/UI expansion described above.

## Architecture flow

```
CropScanner.tsx (unchanged)
  └─ POST /api/analyze (multipart: image, query, type, cropName, provider)
       └─ src/app/api/analyze/route.ts
            ├─ type !== "crop_disease", or provider === "groq",
            │  or no image  →  existing Gemini/Groq paths (100% unchanged)
            └─ type === "crop_disease" && image present
                 └─ getDiseaseAnalysisConfig() (lib/disease-analysis/config.ts)
                      ├─ provider === "gemini"  → existing Gemini vision path (unchanged)
                      └─ provider === "custom-ml"
                           └─ runDiseaseAnalysis() (lib/disease-analysis/service.ts)
                                ├─ GET  {CUSTOM_ML_SERVICE_URL}/api/ready   (optional)
                                ├─ POST {CUSTOM_ML_SERVICE_URL}/api/predict/disease
                                │    (lib/disease-analysis/providers/custom-ml.ts)
                                ├─ strict response validation
                                ├─ fallback policy (infra failures only)
                                └─ maps to the app's existing result shape
```

New modules (all under `src/lib/disease-analysis/`):

| File | Responsibility |
|---|---|
| `types.ts` | Shared normalized types, approved class list, error class |
| `class-mapping.ts` | `ApprovedClassName` → `{crop, condition, healthy}` |
| `config.ts` | Validated, server-side-only feature-flag configuration |
| `providers/custom-ml.ts` | FastAPI adapter: readiness check, multipart POST, strict validation |
| `providers/gemini.ts` | Gemini response-text parsing (moved verbatim from route.ts) |
| `service.ts` | Provider selection + fallback orchestration |

`src/lib/gemini.ts` (the actual Gemini SDK wrapper) is **untouched**.
`src/lib/groq.ts` and `src/lib/ollama.ts` are **untouched**.

## Feature flags / environment variables

All server-side only — **never** `NEXT_PUBLIC_`-prefixed, never sent to the
browser bundle. See `.env.local.example`.

| Variable | Default | Validation |
|---|---|---|
| `DISEASE_ANALYSIS_PROVIDER` | `gemini` | `"custom-ml" \| "gemini"` only |
| `CUSTOM_ML_ENABLED` | `false` | boolean-like (`true/false/1/0/yes/no`) |
| `CUSTOM_ML_SERVICE_URL` | `http://127.0.0.1:8001` | must be a valid `http(s)://` URL |
| `CUSTOM_ML_REQUEST_TIMEOUT_MS` | `15000` | number, `1000`–`120000` |
| `CUSTOM_ML_FALLBACK_TO_GEMINI` | `true` | boolean-like |
| `CUSTOM_ML_REQUIRE_READY_CHECK` | `true` | boolean-like |

Configuration is validated once (cached) the first time it's read; an
invalid value throws immediately with a clear message rather than failing
silently deep inside a request.

## Provider-selection / feature-flag matrix

| # | `CUSTOM_ML_ENABLED` | `DISEASE_ANALYSIS_PROVIDER` | `CUSTOM_ML_FALLBACK_TO_GEMINI` | Behavior | Verified |
|---|---|---|---|---|---|
| A | `false` | `gemini` | — | Existing Gemini flow, unchanged | ✅ (unit) |
| B | `true` | `custom-ml` | `false` | Custom ML only; safe error (no fallback) when unavailable | ✅ (unit) |
| C | `true` | `custom-ml` | `true` | Custom ML primary; Gemini infrastructure fallback | ✅ (unit + live) |
| D | `false` | `custom-ml` | — | **Configuration error at load time** — refuses to start with an inconsistent flag combination rather than silently ignoring `DISEASE_ANALYSIS_PROVIDER` or silently enabling custom-ml | ✅ (unit) |

"Unit" coverage for A/B/C includes the full mocked-auth/mocked-MongoDB
persistence path (`Analysis.create`, `aiProvider` value, `analysisCount`
increment) via `src/app/api/analyze/route.test.ts`, not just provider
selection.

## Custom ML request/response mapping

**Request**: `POST {CUSTOM_ML_SERVICE_URL}/api/predict/disease`, `multipart/form-data`,
field name `file` (filename/MIME forwarded as upload metadata only — no
class label, no threshold, and no other ML-relevant parameter is ever sent
by the client or the adapter).

**Response validation** (`providers/custom-ml.ts`) — *any* of these failing
makes the whole response `ML_UPSTREAM_INVALID_RESPONSE` (never partially
trusted):

- `status === "success"`
- `prediction.class_name` is one of the six approved classes (Corn or any
  unknown class name is rejected, never silently accepted)
- `prediction.model_confidence` is a finite number in `[0, 1]`
- `prediction.accepted` and `prediction.uncertain` are strict logical
  opposites (both booleans, `accepted !== uncertain`)
- `confidence_policy.threshold === 0.5`
- `confidence_policy.label === "model confidence"`
- `confidence_policy.production_calibrated === false`

**Normalized result** (`CustomMlNormalizedResult`) adds `crop`/`condition`/
`healthy` via a fixed lookup table (`class-mapping.ts`) — never inferred,
only the six approved classes are ever accepted:

| Class | crop | condition | healthy |
|---|---|---|---|
| Tomato Healthy | Tomato | Healthy | true |
| Tomato Early Blight | Tomato | Early Blight | false |
| Tomato Late Blight | Tomato | Late Blight | false |
| Potato Healthy | Potato | Healthy | true |
| Potato Early Blight | Potato | Early Blight | false |
| Potato Late Blight | Potato | Late Blight | false |

## Response shape returned to the browser

*(M8-era shape — superseded by M9; see
[`CUSTOM_ML_RESULT_SCHEMA.md`](CUSTOM_ML_RESULT_SCHEMA.md) for the current
`customMl`/`providerMetadata`/`secondaryOpinion`/`resultVersion` fields.)*

`result.diagnosis/severity/confidence/treatment/prevention/expertAdvice/
rawResponse` — the **existing** fields `AnalysisResultCard.tsx` already
reads — are always populated, regardless of provider, so the M8-era UI
kept working unmodified before M9's UI update.

`treatment`/`prevention` for a custom-ml result are safe, static,
non-diagnostic strings (the ML model returns a classification only, never
treatment text) — the model does **not** fabricate treatment claims. This
is unchanged by M9.

## MongoDB persistence

**Every completed analysis is persisted** (`Analysis.create()`), exactly
as before M8 — custom-ml results are not skipped. `Analysis.aiProvider`
(`src/models/Analysis.ts`) is resolved to an honest value reflecting what
actually produced the *persisted* result:

| Scenario | Live response `aiProvider` | **Persisted** `Analysis.aiProvider` |
|---|---|---|
| Gemini primary | `gemini` | `gemini` |
| Groq primary | `groq` | `groq` |
| custom-ML primary (accepted or uncertain, no secondary opinion) | `custom-ml` | `custom-ml` |
| custom-ML infra failure → full Gemini fallback (no custom-ml data at all) | `gemini` | `gemini` |
| custom-ML uncertain + Gemini secondary opinion (both contributed) | `custom-ml` | `combined` |

The live JSON response's top-level `aiProvider` always describes the
*primary* result being shown (`custom-ml` stays `custom-ml` even with a
labelled secondary opinion attached, since the primary displayed result
is still the ML model's own). The **persisted** value additionally uses
`combined` specifically to record, for history purposes, that two sources
genuinely contributed — `combined` is never written for a single-source
result. This table is unchanged by M9 (`aiProvider`/`persistedProvider`
in `docs/CUSTOM_ML_RESULT_SCHEMA.md` use the same mapping).

### What survives persistence (M9 update)

As of **M9**, dedicated fields (`customMl`, `providerMetadata`,
`secondaryOpinion`, `resultVersion`) are additively written to
`Analysis` alongside the legacy `result` fields, and are readable back
through `GET /api/history`. See
**[`CUSTOM_ML_RESULT_SCHEMA.md`](CUSTOM_ML_RESULT_SCHEMA.md)** for the
full field-by-field reference. Records written before M9 have none of
these fields and remain valid, readable documents — no migration was run.

## Fallback policy

Infrastructure fallback (to Gemini, when `CUSTOM_ML_FALLBACK_TO_GEMINI=true`)
triggers **only** for:

- ML service unreachable (`ML_SERVICE_UNAVAILABLE`)
- readiness check false (`ML_SERVICE_NOT_READY`)
- request timeout (`ML_SERVICE_TIMEOUT`)
- upstream 5xx
- upstream response fails strict schema validation (`ML_UPSTREAM_INVALID_RESPONSE`)

Fallback **never** triggers for user-caused 4xx (`INVALID_IMAGE`,
`IMAGE_TOO_LARGE`, `UNSUPPORTED_MEDIA_TYPE`) — these propagate directly as
the corresponding HTTP status, regardless of the fallback flag.

When fallback occurs, the response includes fallback details nested inside
`providerMetadata` (M9; see `CUSTOM_ML_RESULT_SCHEMA.md` — the M8-era
top-level `fallback` field no longer exists):
```json
"providerMetadata": { "fallbackUsed": true, "fallbackProvider": "gemini", "fallbackReason": "service_unavailable", "...": "..." }
```
(`fallbackReason` ∈ `service_unavailable | timeout | malformed_upstream | service_not_ready | uncertain_prediction`)

## Uncertain-result handling

When the ML service returns `accepted: false, uncertain: true`, the API
**preserves that state** — it is never converted into a confirmed
diagnosis. `result.expertAdvice` is set to: *"The custom model returned a
low-confidence result. Please capture a clearer leaf image or use expert
review."*

If `CUSTOM_ML_FALLBACK_TO_GEMINI=true` and the result is uncertain, Gemini
is optionally consulted as a **separately labelled secondary opinion**
(top-level `secondaryOpinion`, flattened — see `CUSTOM_ML_RESULT_SCHEMA.md`
for the exact M9 shape) — the primary `result`/`aiProvider` stay
`custom-ml`/uncertain; Gemini's opinion is never presented as confirmation
of, or a silent replacement for, the primary result. If the secondary call
itself fails, the primary uncertain result is still returned normally.

## Supported classes

Tomato Healthy, Tomato Early Blight, Tomato Late Blight, Potato Healthy,
Potato Early Blight, Potato Late Blight. Corn and any other class name are
never silently accepted.

## Local startup (both services)

```bash
# Terminal 1 -- ML service
cd ml-service
.venv/bin/python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8001

# Terminal 2 -- Next.js app (custom-ml mode)
# in .env.local:
#   CUSTOM_ML_ENABLED=true
#   DISEASE_ANALYSIS_PROVIDER=custom-ml
#   CUSTOM_ML_SERVICE_URL=http://127.0.0.1:8001
#   CUSTOM_ML_FALLBACK_TO_GEMINI=false   (or true, for Scenario C)
npm run dev
```

Then use the existing Crop Scanner UI (`/dashboard/scan`), or call
`POST /api/analyze` directly with an authenticated session cookie.

## Verification performed

Direct integration-level verification was run against the real, locally
running FastAPI service: successful prediction on a `val.csv` image (never
`test.csv`), an unsupported-file rejection, a safe error while the ML
service was stopped, and successful recovery after restart — all via the
actual `providers/custom-ml.ts`/`service.ts` code path making real HTTP
calls to `127.0.0.1:8001`.

Provider selection, the full feature-flag matrix, fallback/uncertain-result
policy, **and the complete authenticated API route + MongoDB persistence
flow** (session handling, `Analysis.create()`/`User.analysisCount`
ordering, the `aiProvider` persistence mapping table above, database-
failure handling, and `/api/history` serialization of custom-ml/`combined`
records) were verified with mocked-auth/mocked-database unit tests using
the project's `vi.mock` pattern for `next-auth`, `@/lib/mongodb`,
`@/models/Analysis`, and `@/models/User`. As of M9 this also includes
component tests (`@testing-library/react` + jsdom, per-file
`@vitest-environment` pragma) for `AnalysisResultCard.tsx`/`HistoryList.tsx`
— see `docs/CUSTOM_ML_RESULT_SCHEMA.md` and the M9 completion report for
current pass counts.

**Not performed**: full authenticated **browser** verification through a
real NextAuth session and a real MongoDB instance (no MongoDB/ml-service
process was running locally during M8 or M9, and `.env.local` was not read
or modified, per project policy). This is disclosed rather than claimed as
fully verified end-to-end in a browser.

## Safe error behavior

Stable error contract, never a stack trace/path/service URL/API key:
```json
{ "success": false, "error": { "code": "ML_SERVICE_UNAVAILABLE", "message": "Disease analysis is temporarily unavailable." } }
```
Codes: `INVALID_IMAGE` (400), `IMAGE_TOO_LARGE` (413),
`UNSUPPORTED_MEDIA_TYPE` (415), `ML_SERVICE_NOT_READY` (503),
`ML_SERVICE_UNAVAILABLE` (503), `ML_SERVICE_TIMEOUT` (504),
`ML_UPSTREAM_INVALID_RESPONSE` (502), `DISEASE_ANALYSIS_FAILED` (500,
configuration error).

## Confidence limitations (unchanged from ml-service M5/M7)

Model confidence is a model score, not certainty or probability of truth.
The frozen threshold (0.50) rejected zero of 991 frozen-test predictions.
Real-world farm-photo validation has not been performed. Only six
Tomato/Potato classes are supported. **Not production-calibrated — no
production-readiness claim is made.**

## Status

Custom-ml analyses are persisted to history with both the legacy fields
and, as of **M9**, dedicated `customMl`/`providerMetadata`/
`secondaryOpinion`/`resultVersion` fields — see
[`CUSTOM_ML_RESULT_SCHEMA.md`](CUSTOM_ML_RESULT_SCHEMA.md) for the current
schema and `AnalysisResultCard.tsx`/`HistoryList.tsx` for how it's
rendered. **M10** (real end-to-end validation against a running MongoDB,
FastAPI service, and Next.js app) has been completed — see
[`CUSTOM_ML_E2E_VALIDATION.md`](CUSTOM_ML_E2E_VALIDATION.md) for the full
results, including disclosed limitations. M11 (final documentation /
sign-off) has not started.
