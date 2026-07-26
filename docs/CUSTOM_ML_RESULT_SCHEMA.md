# Custom ML Result Schema — Milestone M9

## Purpose

M9 adds dedicated MongoDB fields for the custom-ml classifier's metadata
(previously response-only, per M8's "What survives persistence" gap) and
updates the crop-scanner/history UI to display it. This document is the
single reference for the resulting schema: what is persisted, what the
API returns, and how the two relate. Field names are identical between the
persisted document, the immediate `POST /api/analyze` response, and the
`GET /api/history` response — there is exactly one shape, not three.

Nothing here changes the ML model, checkpoint, confidence policy, training
pipeline, dataset, or the frozen `0.5` confidence threshold. Nothing here
changes Qwen/Groq/Ollama.

## Where each shape is defined

| Concern | File |
|---|---|
| Shared TypeScript types (`PersistedCustomMl`, `ProviderMetadata`, `PersistedSecondaryOpinion`, `ResultVersion`) | `src/lib/disease-analysis/types.ts` |
| Shape-building + independent re-validation at the persistence boundary | `src/lib/disease-analysis/persistence.ts` |
| Mongoose schema (additive sub-schemas) | `src/models/Analysis.ts` |
| Writes `customMl`/`providerMetadata`/`secondaryOpinion`/`resultVersion`, builds the immediate response | `src/app/api/analyze/route.ts` |
| Reads the same fields back for history | `src/app/api/history/route.ts` |
| Renders the fields (provider badge, safety notes, top predictions, fallback/secondary-opinion labels) | `src/components/dashboard/custom-ml-shared.tsx`, `AnalysisResultCard.tsx`, `HistoryList.tsx` |

## `customMl` — only present when the classifier actually produced a valid result

```ts
interface PersistedCustomMl {
  className: ApprovedClassName;     // one of the six approved classes
  classIndex: number;               // cross-checked against the fixed class ordering
  crop: "Tomato" | "Potato";
  condition: string;                // e.g. "Late Blight", "Healthy"
  healthy: boolean;
  modelConfidence: number;          // [0, 1] -- a model score, not a probability of truth
  accepted: boolean;
  uncertain: boolean;               // accepted and uncertain are always strict opposites
  confidenceLabel: "model confidence";
  productionCalibrated: false;      // always false -- no production-readiness claim
  supportedClass: true;
  confidenceThreshold: 0.5;         // frozen -- see confidence_policy_v1.json (ml-service, out of M9 scope)
  confidenceMethod: "maximum_softmax_probability";
  topPredictions: { className: ApprovedClassName; classIndex: number; modelConfidence: number }[]; // sorted desc, capped at 3
  model: { architecture: string; classCount: number }; // "efficientnet_b0", 6
  limitations: string[];            // capped at 10, verbatim from the ml-service response
}
```

`customMl` is **absent** (not `null`, not an empty object) whenever:
- the request never reached the custom-ml flow (Gemini/Groq primary, or `type !== "crop_disease"`), or
- a full infrastructure fallback occurred and only Gemini produced content.

It is never fabricated on an infra failure — a request that fell back to
Gemini persists with no `customMl` at all, only `providerMetadata`
describing the fallback.

## `providerMetadata` — single source of truth for provenance

```ts
interface ProviderMetadata {
  primaryProvider: "custom-ml" | "gemini";     // which provider call actually produced this result
  persistedProvider: "gemini" | "groq" | "custom-ml" | "combined";
  fallbackUsed: boolean;
  fallbackProvider?: "custom-ml" | "gemini";    // present iff fallbackUsed
  fallbackReason?: "service_unavailable" | "timeout" | "malformed_upstream" | "service_not_ready" | "uncertain_prediction";
  secondaryOpinionUsed: boolean;
}
```

`persistedProvider` is the same value written to the legacy
`Analysis.aiProvider` field, so both remain consistent:

| Scenario | `persistedProvider` / `aiProvider` |
|---|---|
| Gemini primary (no custom-ml flow) | `gemini` |
| Groq primary | `groq` |
| custom-ml primary (accepted or uncertain, no secondary opinion) | `custom-ml` |
| custom-ml infra failure → full Gemini fallback (no `customMl`) | `gemini` |
| custom-ml uncertain + Gemini secondary opinion (both genuinely contributed) | `combined` |

`combined` is **only** ever produced when a secondary opinion actually
attached to the outcome — never as a stand-in label for a single-provider
result. This is enforced twice: once when `providerMetadata` is built
(`persistence.ts`'s `buildProviderMetadata`), and again independently at
`validateProviderMetadataForPersistence`, which rejects `combined` without
`secondaryOpinionUsed: true` (and vice versa) before anything is written.

`providerMetadata` is only present for requests that went through the
custom-ml flow (`runDiseaseAnalysis`) — plain Gemini/Groq requests outside
that flow have no `providerMetadata` at all, exactly like pre-M9 records.

## `secondaryOpinion` — never ground truth

```ts
interface PersistedSecondaryOpinion {
  provider: "gemini";
  diagnosis: string;      // capped at 500 chars
  severity: "critical" | "high" | "medium" | "low" | "healthy";
  confidence: number;     // [0, 100], legacy scale
  treatment: string;      // capped at 4000 chars
  prevention: string;     // capped at 4000 chars
  expertAdvice?: string;  // capped at 4000 chars
}
```

Present only when the primary custom-ml result was `uncertain` and
`CUSTOM_ML_FALLBACK_TO_GEMINI=true` caused a secondary Gemini opinion to be
sought. The UI (`SecondaryOpinionNote`) always labels this "not a
confirmation" — it never overrides or is merged into the primary
`customMl`/`result` fields.

## `resultVersion`

`2` for every document written by M9-era code (any record with
`customMl`/`providerMetadata`/`secondaryOpinion` awareness — including
disease-analysis records where those three all end up absent, e.g. a plain
Gemini primary through the custom-ml flow). **Absent** — never backfilled
to `1` — on documents written before M9. Consumers must treat a missing
`resultVersion` as version 1. This is purely additive: no migration was
run, no existing document was modified.

## Defense-in-depth: persistence-boundary re-validation

`persistence.ts` never trusts that `providers/custom-ml.ts`'s own
validation (`validateAndNormalize`) is sufficient. Every invariant is
re-checked independently at the point of persistence
(`buildPersistedCustomMl`, `buildProviderMetadata` +
`validateProviderMetadataForPersistence`):

- `className` is one of the six approved classes
- `classIndex` agrees with the fixed class ordering
- `modelConfidence` is finite and in `[0, 1]`
- `accepted`/`uncertain` are strict logical opposites
- `confidenceThreshold === 0.5`, `confidenceLabel === "model confidence"`, `productionCalibrated === false`, `supportedClass === true`
- `confidenceMethod` is a supported method
- `topPredictions` contains at least one valid entry, sorted desc, capped at 3
- `crop`/`condition`/`healthy` agree with the fixed class-breakdown lookup table
- `persistedProvider === "combined"` if and only if `secondaryOpinionUsed === true`
- `fallbackProvider`/`fallbackReason` are present if and only if `fallbackUsed === true`

Any failure throws `PersistenceValidationError` in
`src/app/api/analyze/route.ts` **before** `Analysis.create()` is ever
called: nothing is persisted, `User.analysisCount` is not incremented, and
the client receives a sanitized `500 { success: false, error: { code:
"DISEASE_ANALYSIS_FAILED", ... } }` — never the internal validation
reason.

## API response shape (`POST /api/analyze` and `GET /api/history`)

Both endpoints return the exact same field names for the exact same
concepts — nothing is renamed or reshaped between the immediate response
and history:

```json
{
  "result": { "diagnosis": "...", "severity": "medium", "confidence": 98, "treatment": "...", "prevention": "...", "rawResponse": "..." },
  "aiProvider": "custom-ml",
  "resultVersion": 2,
  "customMl": { "...": "PersistedCustomMl, see above" },
  "providerMetadata": { "...": "ProviderMetadata, see above" },
  "secondaryOpinion": { "...": "PersistedSecondaryOpinion, only if present" }
}
```

`GET /api/history` additionally wraps this per-record inside
`analyses[i]`, alongside the pre-existing `id`/`type`/`query`/`cropName`/
`createdAt` fields (`src/app/api/history/route.ts`). Legacy records (no
M9 fields) simply omit `customMl`/`providerMetadata`/`secondaryOpinion`/
`resultVersion` — they are never rendered as empty objects or `null`.

## Security correction bundled with M9 (Section 15)

`src/app/api/analyze/route.ts`'s outer catch-all handler previously
interpolated the raw caught error's `message` into the client-facing JSON
response (`Analysis failed: ${error.message}`) — a pre-existing issue
flagged during the M8 review, unrelated to the schema/UI work above but
fixed alongside it since it touches the same file. It now always returns
the fixed string `"Analysis failed. Please try again later."`; the full
error is still logged server-side via `console.error`. See
`route.test.ts`'s `"the outer catch handler never interpolates a raw
error message..."` test.

## UI rendering rules (`AnalysisResultCard.tsx`, `HistoryList.tsx`)

- An `uncertain: true` result always shows a visible **"Low-confidence
  model result"** badge/warning — never phrased as a confirmed diagnosis.
- An accepted result is labelled **"Model prediction"** — never
  "Confirmed disease".
- The safety-notes block (`CustomMlSafetyNotes`) always states the
  six-class scope and the lack of real-world field validation, regardless
  of `accepted`/`uncertain` — the model's scope limitations don't change
  based on how confident one prediction was.
- A secondary opinion is always rendered with an explicit "not a
  confirmation" disclaimer.
- A fallback is rendered as an honest note ("Fell back to ... because
  ...") rather than silently hidden.

## What is explicitly out of scope for this schema

- No pesticide/fertilizer dosage of any kind is ever included in
  `customMl`/`secondaryOpinion` — `treatment`/`prevention` remain
  disclaimer text for custom-ml results (unchanged from M8).
- No new MongoDB indexes were added — `customMl`/`providerMetadata`/
  `secondaryOpinion`/`resultVersion` are not currently queried/filtered on
  by any existing route, so no index is demonstrated as needed yet.
- No migration of existing documents. No change to `confidence_policy_v1.json`,
  the model checkpoint, the training pipeline, or the dataset/split
  manifests.

## Status

This schema was validated end to end against a real MongoDB instance
during **M10** (see [`CUSTOM_ML_E2E_VALIDATION.md`](CUSTOM_ML_E2E_VALIDATION.md)).
See [`PHASE_2_CUSTOM_DISEASE_ML.md`](PHASE_2_CUSTOM_DISEASE_ML.md) for how
this fits into the complete, now-complete Phase 2 feature (M1–M11).
