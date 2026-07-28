# Phase 3 — Weather-Aware Crop Advisory (M1 Plan)

**Status: M1 (requirements, architecture, provider selection) complete.
No production code, schema changes, API routes, UI, or credentials were
added in M1 — this document and `PHASE_3_WEATHER_PROVIDER_DECISION.md` are
the only changes.** M2–M6 are not started; see Section 18 for the exact M2
boundary.

## 1. Phase objective

Add location-based weather information and a transparent, rule-based
crop-weather risk advisory to AgriAI, kept **strictly separate** from the
Phase 2 disease-image-model prediction. Weather must never alter, average
with, or silently reinterpret a model class or confidence — it is
additional, independently-labeled context shown alongside it.

## 2. Current-project audit

### 2.1 Stack and structure
Next.js 14 (App Router, TypeScript), MongoDB via Mongoose, NextAuth
(Credentials + optional Google OAuth, JWT sessions), Tailwind. `ml-service/`
is a separate FastAPI/Python process (Phase 2, untouched by Phase 3).

### 2.2 Relevant existing pieces and what Phase 3 should reuse

| Area | File(s) | Reusable pattern |
|---|---|---|
| Auth check in routes | every `src/app/api/*/route.ts` | `getServerSession(authOptions)` → 401 JSON if absent |
| DB connection | `src/lib/mongodb.ts` | cached global `connectDB()`, call once per handler |
| User schema | `src/models/User.ts` | already has `location: { state, district, coordinates? }` and `farmDetails: { size, cropTypes, soilType, irrigationType }` — **no country, no location label, no growth stage, no timezone, no per-crop selection beyond a `cropTypes[]` array** |
| Analysis schema | `src/models/Analysis.ts` | `type` enum already includes `"weather"` and there is a small pre-existing `weather?: { temperature, humidity, rainfall }` stub — legacy/unused, never populated by any current code path. Phase 3 must decide whether to build on it or replace it (Section 9). |
| Feature-flag config pattern | `src/lib/disease-analysis/config.ts` | validated, fail-fast, server-only env parsing with a cached singleton and a `_resetForTests` escape hatch — the exact shape a `weather/config.ts` should follow |
| Provider-adapter pattern | `src/lib/disease-analysis/providers/custom-ml.ts` | plain `fetch` + `AbortController` timeout, **never trusts the upstream response** — strict field-by-field validation before use, a single `fail()` helper, its own `Error` subclass with a stable `code` | 
| Orchestration/fallback pattern | `src/lib/disease-analysis/service.ts` | separates "infrastructure failure → optional fallback" from "user-caused 4xx → never fallback, just propagate" |
| Persistence re-validation pattern | `src/lib/disease-analysis/persistence.ts` | never trusts the adapter's own validation twice — re-validates every field independently at the exact point of `Analysis.create()`, throws before any partial write |
| Result-card UI | `src/components/dashboard/AnalysisResultCard.tsx`, `custom-ml-shared.tsx` | existing shared badge/label helpers (`formatPercent`, `providerLabel`, status badges) to extend, not duplicate |
| Settings UI | `src/components/dashboard/SettingsForm.tsx` | glass-card sections, `label`/`input-field` CSS classes, `toast` for save feedback — a farm-location form should look identical |
| Profile API | `src/app/api/profile/route.ts` | GET/PATCH pattern on the user document — a `farm-profile` route (if kept on `User`) or a new collection would follow this same GET/PATCH shape |
| History API | `src/app/api/history/route.ts` | paginated, filtered `find()` + `countDocuments()` — the advisory-history route should mirror this |
| Env-var convention | `.env.local.example` | server-only vars, never `NEXT_PUBLIC_`, documented inline with an explanatory comment and a pointer to a docs file |
| Docker | `docker-compose.yml` | only `ml-service` is containerized; Next.js and MongoDB run outside compose. Weather calls happen from the Next.js server process — **no Docker changes needed for Phase 3** |
| CI | `.github/workflows/ci.yml` | lint + build only, on push/PR to `main`; no Python/pytest step exists (ml-service tests are not CI-gated today) |
| Tests | `*.test.ts(x)` colocated with source, Vitest | `config.test.ts`-style direct unit tests are the expected shape for a new `weather/config.test.ts` |

### 2.3 Gaps Phase 3 must fill
- No geocoding is used anywhere today (`location` is free-text state/district only).
- No third-party HTTP provider config exists outside `disease-analysis/config.ts`'s pattern (Gemini/Groq use SDKs directly, no adapter layer).
- No caching layer exists anywhere in the app (Mongoose queries are direct; the only cache is `custom-ml.ts`'s tiny in-memory readiness-check TTL).
- No structured "unavailable/stale" UI state exists yet — errors are currently shown as toasts, not persistent inline states.

## 3. Functional requirements

**Required for first implementation (M2–M4):**
- Farm profile: location label, district, state, country, optional lat/lng, selected crop (Tomato or Potato, matching Phase 2's active scope), optional growth stage.
- Weather: current temperature, humidity, precipitation, rain probability, wind speed, condition text, a short (multi-day) forecast, `observedAt`/`fetchedAt` timestamps.
- Advisory: risk level (low/moderate/high/unavailable), triggered rule IDs, human-readable reasons, recommendations, data-freshness flag, provider name, safety disclaimer.
- History: persisted advisories with their weather snapshot, crop/location context, risk level, and provider/age metadata.

**Optional / later (not built until explicitly approved in a future milestone):**
- Per-hour forecast UI (vs. the 5-day/3-hour raw feed).
- Timezone-aware display beyond a stored IANA string.
- Multiple saved locations per user (v1 is one active farm profile per user, matching the existing single-`location` field on `User`).
- Wind-based risk rules beyond a basic threshold (most crop-fungal rules in Section 7 don't need wind as a primary factor).

**Explicitly out of scope (Phase 3 does not touch, per the phase brief):**
Pest detection, soil ML, disease-risk *prediction* (as opposed to weather-*condition* risk), crop calendar, voice assistant, RAG, offline PWA, feedback/correction loops, automatic retraining, IoT, and any Phase 2 model change.

## 4. Non-functional requirements

- **Reliability:** a weather-provider outage must degrade to a clearly-labeled unavailable/stale state, never a fabricated value, and must never take down the disease-analysis or chat flows (weather is fetched by a separate route, never inline in `/api/analyze`).
- **Provider timeouts:** bounded (mirroring `custom-ml.ts`'s `fetchWithTimeout` — an `AbortController` with a short, configurable timeout, default in the 5–15s range).
- **Rate limits:** the app must stay within OpenWeatherMap's free-tier 60 calls/minute by caching per-location results (Section 12) rather than calling on every page render.
- **Stale-weather handling:** a normalized snapshot has an explicit `dataFreshness: "fresh" | "stale" | "unavailable"` field; the UI must render all three distinctly.
- **Caching:** short-TTL, in-memory (or Mongo-backed, TBD in M2) cache keyed by rounded lat/lng + provider, so repeated requests for the same farm within the TTL window don't re-call the provider.
- **Input validation:** location and coordinates validated server-side before any provider call (valid lat/lng ranges, non-empty location label); crop restricted to the Phase 2 active set (Tomato/Potato) for the risk engine, though the farm profile itself is not required to restrict `cropTypes` beyond what `User.farmDetails.cropTypes` already allows.
- **Response sanitization:** provider error bodies/URLs are never echoed to the client, mirroring `DiseaseAnalysisError`'s existing rule.
- **Accessibility/responsiveness:** reuse existing `glass-card`/Tailwind conventions; no new design system.
- **Testability:** every adapter/normalization/risk-rule function must be pure and unit-testable without a live network call (mocked HTTP responses), matching the existing `custom-ml.test.ts` style.
- **Privacy:** store only what's needed for the advisory (coordinates at normal precision are fine since this is farm-management data the user explicitly enters — no fine-grained tracking, no location history beyond what's tied to saved advisories).
- **Observability:** server-side `console.error`-style logging of provider failures (matching existing routes), no client-facing stack traces.
- **Performance:** advisory generation should be dominated by the cached-or-not provider call, not by rule evaluation (the risk engine is synchronous, in-process, no external calls).
- **Maintainability:** provider-specific field names/shapes must never leak past the adapter (Section 6); the risk engine only ever sees the normalized schema.

**Provider-unavailable behavior (first version):** return a `risk: "unavailable"` advisory with `dataFreshness: "unavailable"`, a message ("Weather information is currently unavailable."), and no reasons/recommendations — the client never sees a guessed risk level.

## 5. Weather provider research and selection

Full comparison and reasoning: **`docs/PHASE_3_WEATHER_PROVIDER_DECISION.md`**
(ADR). Summary: **OpenWeatherMap** selected (Current Weather API 2.5 + 5
Day/3 Hour Forecast API 2.5 + Geocoding API 2.5) — explicit free-tier
commercial-use permission, a server-side-API-key shape consistent with the
existing `GEMINI_API_KEY`/`GROQ_API_KEY` convention, established India
coverage, and sufficient free-tier limits (60 calls/min, 1,000,000/month).
Open-Meteo was rejected as the *primary* provider specifically because its
free tier explicitly prohibits commercial use; WeatherAPI.com was rejected
for a shorter free forecast horizon and a mandatory attribution backlink.
No credentials were added or requested during this research — all
verification used public, credential-free documentation pages.

## 6. Architecture

```
Authenticated user
  └─ Farm/location settings (dashboard/settings, extended)
       └─ PUT /api/farm-profile  →  User.location / a farm-profile shape (Section 9)
  └─ Dashboard weather card / Scan page weather context
       └─ GET /api/weather/current, GET /api/weather/forecast
            └─ weather/config.ts        (validated server-side provider config)
            └─ weather/provider/openweather.ts   (adapter: fetch + strict validate/normalize)
            └─ weather/normalize.ts     (provider-independent NormalizedWeather schema)
            └─ weather/cache.ts         (short-TTL per-location cache)
       └─ POST /api/weather/advisory
            └─ weather/risk-engine.ts   (pure, rule-based, crop-scoped)
            └─ weather/persistence.ts   (independent re-validation before Mongo write)
            └─ Advisory.create()        (MongoDB)
  └─ GET /api/weather/advisories        (paginated history, mirrors /api/history)
```

Module boundaries (all under `src/lib/weather/`, mirroring
`src/lib/disease-analysis/`'s layout):

| Module | Responsibility |
|---|---|
| `config.ts` | parses/validates `OPENWEATHER_*` env vars, fails fast on inconsistent flags, cached singleton |
| `geocoding.ts` | resolves a free-text location (or accepts explicit lat/lng) to coordinates via the Geocoding API |
| `provider/openweather.ts` | the only module that knows OpenWeatherMap's JSON shape; strict validation, never trusts upstream blindly |
| `types.ts` | the normalized weather/advisory types shared by every other module |
| `risk-engine.ts` | pure functions: `NormalizedWeather` + crop → risk result; no I/O |
| `advisory-service.ts` | orchestrates geocoding → provider call (cached) → risk engine → result shape, mirroring `disease-analysis/service.ts` |
| `persistence.ts` | builds + independently re-validates the exact Mongo document shape, mirroring `disease-analysis/persistence.ts` |
| `cache.ts` | short-TTL, per-location cache (in-memory to start, matching `custom-ml.ts`'s readiness-cache precedent) |
| `src/app/api/weather/*/route.ts`, `src/app/api/farm-profile/route.ts` | thin route handlers: session check → call the service module → shape the JSON response |
| `src/components/dashboard/Weather*.tsx` | UI: farm settings section, weather card, risk badge, forecast, advisory history |
| `*.test.ts(x)` colocated | provider adapter tests (mocked HTTP), normalization tests, risk-rule tests, route tests |

## 7. Normalized weather contract

Provider-specific field names (OpenWeatherMap's `main.temp`, `weather[0].id`,
etc.) must never appear outside `provider/openweather.ts`. Proposed shape:

```ts
interface NormalizedWeather {
  provider: "openweathermap";
  location: { label: string; district?: string; state?: string; country?: string };
  latitude: number;          // required, -90..90
  longitude: number;         // required, -180..180
  timezone?: string;         // IANA string, optional
  observedAt: string;        // ISO 8601 — when the provider observed/computed this
  fetchedAt: string;         // ISO 8601 — when AgriAI's server fetched it
  temperatureC: number;      // required
  apparentTemperatureC?: number;
  humidityPercent: number;   // required, 0..100
  precipitationMm?: number;  // optional, >= 0
  rainProbabilityPercent?: number; // optional, 0..100 (only present on forecast entries)
  windSpeedKph?: number;     // optional, >= 0
  conditionCode: string;     // provider's own code, passed through as an opaque string
  conditionText: string;     // human-readable, required
  forecast: ForecastEntry[]; // ordered, ascending time; empty array if forecast unavailable
  dataFreshness: "fresh" | "stale" | "unavailable";
}

interface ForecastEntry {
  timestamp: string;         // ISO 8601
  temperatureC: number;
  humidityPercent: number;
  precipitationMm?: number;
  rainProbabilityPercent?: number;
  windSpeedKph?: number;
  conditionCode: string;
  conditionText: string;
}
```

**Required fields:** `provider`, `latitude`, `longitude`, `fetchedAt`,
`temperatureC`, `humidityPercent`, `conditionCode`, `conditionText`,
`dataFreshness`. **Optional:** everything else — a missing optional field
is simply absent (`undefined`), never a fabricated `0` or `null` standing
in for "unknown." **Units** are fixed (Celsius, mm, kph, percent) so the
risk engine never has to convert. **Timestamps** are always ISO 8601
strings. A response that fails required-field validation is treated as
`dataFreshness: "unavailable"`, never partially trusted.

## 8. Crop-risk engine design

Rule-based, fully transparent, scoped to **Tomato and Potato** (Phase 2's
active classes). Risk levels: `low`, `moderate`, `high`, `unavailable`
(when weather itself is unavailable — the engine must not guess).

Example rule shape (illustrative, not final — exact thresholds are an M3
task, informed by agronomy references, not invented ad hoc):

```ts
interface RiskRule {
  id: string;               // e.g. "TOMATO_LATE_BLIGHT_HUMIDITY_TEMP"
  crop: "Tomato" | "Potato";
  description: string;      // human-readable, shown in the UI
  evaluate(weather: NormalizedWeather): boolean;
  reason: string;           // shown when triggered
  recommendation: string;   // shown when triggered — never a specific pesticide/dosage
  requiresExpertReview: boolean; // flags rules whose thresholds need agronomy sign-off before M3 ships
}
```

Each advisory result includes: `crop`, `riskLevel`, `triggeredRuleIds`,
`reasons[]`, `recommendations[]`, a fixed **safety disclaimer** string, and
the `observedAt`/`fetchedAt` of the weather snapshot it was computed from.
The engine **never** states or implies that a weather condition *causes* or
*confirms* a disease, and never emits a specific pesticide/fertilizer
product or dosage — recommendations stay at the level of "monitor," "avoid
overhead irrigation," "consult a local extension service," etc. Every rule
whose exact threshold isn't backed by a citable agronomy source is flagged
`requiresExpertReview: true` and documented as such — no rule ships as
implicitly validated just because it's plausible-sounding.

## 9. Phase 2 integration boundary

Weather context is rendered **next to**, never inside, the existing
`AnalysisResultCard`. Concretely: a new, separate card/section (e.g.
`WeatherContextCard`) that:
- never reads or writes `Analysis.result`, `Analysis.customMl`, or `Analysis.providerMetadata`;
- never changes `severity`/`confidence`/`diagnosis` on the disease result;
- is optional — if no farm profile / weather is available, the disease result renders exactly as it does today, unchanged;
- is clearly labeled "Weather context" (or similar), distinct from "Image analysis," matching the example in the phase brief.

Example combined rendering (two independent blocks, not merged):
```
Image analysis:  Potato Late Blight (model confidence 91%)
Weather context: High conditions associated with fungal-disease risk
                 Reasons: high humidity; recent rain; suitable temperature range
                 This is environmental risk context, not a diagnosis confirmation.
```

## 10. Data-model proposal

**Decision: a new `FarmProfile` collection, not an extension of `User`.**
Rationale: `User.location`/`User.farmDetails` are free-text, single-value,
and already used by the (unrelated) profile-settings UI; Phase 3 needs
structured, geocoded, versioned data (coordinates, country, growth stage)
that will grow across M2–M6 (and potentially multiple locations later).
Coupling that to the auth/user document risks exactly the kind of
schema sprawl `Analysis.ts`'s comments show Phase 2 was careful to avoid.
A dedicated collection keeps `User` unchanged and lets farm-profile
validation evolve independently. (No schema is created in M1 — this is a
design decision recorded for M2.)

```ts
// FarmProfile (proposed, M2)
{
  userId: string;              // indexed, one active profile per user in v1
  locationLabel: string;
  district?: string;
  state?: string;
  country: string;             // default "India", still explicit
  latitude?: number;
  longitude?: number;
  selectedCrop: "Tomato" | "Potato";
  growthStage?: string;
  timezone?: string;
  createdAt: Date; updatedAt: Date;
}

// WeatherAdvisory (proposed, M4)
{
  userId: string;
  farmProfileId: string;
  crop: "Tomato" | "Potato";
  weatherSnapshot: NormalizedWeather;   // embedded, not referenced
  forecastSummary?: ForecastEntry[];    // bounded/capped, mirrors persistence.ts's MAX_* caps
  riskLevel: "low" | "moderate" | "high" | "unavailable";
  triggeredRuleIds: string[];
  reasons: string[];
  recommendations: string[];
  provider: "openweathermap";
  observedAt: Date; fetchedAt: Date; createdAt: Date;
  schemaVersion: 1;
}
```

The existing `Analysis.weather` stub (`{ temperature, humidity, rainfall }`)
is left untouched — it is not populated by any current code path and Phase
3 does not repurpose it, to avoid conflating two different kinds of
"weather" data (a leftover generic field vs. a fully-modeled advisory).

## 11. API proposal (design only — not implemented in M1)

| Route | Auth | Notes |
|---|---|---|
| `GET/PUT /api/farm-profile` | session required | mirrors `/api/profile`'s GET/PATCH shape |
| `GET /api/weather/current` | session required | query by the user's farm profile; validates coordinates before calling the provider; cached |
| `GET /api/weather/forecast` | session required | same caching/validation; returns `ForecastEntry[]` |
| `POST /api/weather/advisory` | session required | runs the risk engine against the current cached/fetched weather, persists a `WeatherAdvisory`, returns it |
| `GET /api/weather/advisories` | session required | paginated, mirrors `/api/history` |

For every route: unauthenticated → 401 (no provider call attempted);
malformed/missing farm profile → 400 with a safe message; provider
timeout/unavailable → 503 with `riskLevel: "unavailable"`/`dataFreshness:
"unavailable"`, never a 500 leaking internals; successful advisory
persistence failures → the request fails cleanly, nothing partially
written (mirroring `PersistenceValidationError`'s all-or-nothing rule).
Caching happens inside the service layer, not at the HTTP layer, so
`/current` and `/advisory` share one cached fetch per location/TTL window.

## 12. UI proposal (design only — not implemented in M1)

- Farm settings form (extends `dashboard/settings`, new section styled like `SettingsForm.tsx`'s existing cards): location label, district/state/country, optional coordinates, crop selector (Tomato/Potato), growth stage.
- Dashboard weather card: current conditions + risk badge.
- Risk-level badge: low/moderate/high/unavailable, reusing the existing severity-badge visual language from `custom-ml-shared.tsx`.
- Forecast strip: short multi-entry forecast display.
- Advisory reasons/recommendations list, freshness indicator (fresh/stale/unavailable), and provider attribution line ("Weather data: OpenWeatherMap").
- Advisory history (extends `HistoryList.tsx`'s pattern, or a dedicated weather-history list).
- Weather-context block beside disease results (Section 9), with its own unavailable/stale empty state — never blocking the disease result from rendering.

No existing page is redesigned; this is additive sections/components only.

## 13. Failure and safety design

| Condition | Behavior |
|---|---|
| Invalid/missing location | 400, "Please complete your farm location in Settings." |
| Geocoding failure | treated as provider-unavailable; no coordinates guessed |
| Provider unavailable / timeout / rate-limited | cached snapshot if within staleness window (marked `stale`), else `unavailable` |
| Incomplete/malformed provider response | fails strict validation → `unavailable`, never partially trusted |
| Unsupported crop (not Tomato/Potato) | risk engine returns `unavailable` with an explicit "not yet supported for this crop" reason, distinct from a weather failure |
| Missing farm settings | advisory UI shows a setup prompt, not an error |
| Unauthenticated access | 401 on every route, no provider call made |
| Database failure on persistence | request fails cleanly; the immediate (unpersisted) advisory result may still be returned to the user if the weather portion succeeded — TBD exact behavior in M4, but never a silent partial write |
| Malformed provider response | same as "incomplete" above |

Safe user-facing messages: *"Weather information is currently
unavailable."* / *"No advisory was generated from unavailable weather
data."* Never a fabricated temperature, risk level, or forecast.

## 14. Security and privacy

- Provider calls happen **server-side only** (Next.js route handlers /
  service modules) — the API key is never sent to the browser, matching
  `GEMINI_API_KEY`/`GROQ_API_KEY`'s existing handling.
- The key lives in `OPENWEATHER_API_KEY` (or similar), added to
  `.env.local` **by the user**, not by this M1 milestone (no key is added
  now).
- Coordinates are stored at the precision the user enters (no forced
  rounding/obfuscation) since this is farm-management data the user
  explicitly provides for its use — no third-party sharing beyond the
  weather provider call itself.
- No location data or provider responses are logged with request-level
  detail beyond what the existing routes already log (error class/code),
  and provider error bodies are never echoed to the client.
- Rate-limiting/abuse protection for the new routes rides on the same
  session-required pattern as every other route; no anonymous access.
- Data minimization: only the fields in Section 10 are stored; raw
  provider JSON is never persisted verbatim, only the normalized/validated
  shape.

## 15. Test strategy (for M2–M6)

- **Provider adapter tests** — mocked HTTP responses (success, malformed, timeout, 401/429/5xx), asserting strict validation rejects anything outside contract, matching `custom-ml.test.ts`'s style.
- **Normalization tests** — every required/optional field, boundary values (0%, 100% humidity; negative/zero precipitation rejected; lat/lng range checks).
- **Risk-rule tests** — each rule's boundary conditions, and that `unavailable` weather never produces a non-`unavailable` risk.
- **API auth tests** — every route 401s without a session.
- **API error-mapping tests** — provider failure → correct HTTP status/body, never leaking internals.
- **Persistence tests** — independent re-validation catches an inconsistent advisory before `Advisory.create()`, mirroring `persistence.test.ts`.
- **Legacy-compatibility tests** — `Analysis` documents without any weather data still read/render exactly as before.
- **UI tests** — empty/loading/error/stale states for the weather card and advisory history.
- **E2E weather flow** — one real, credential-backed OpenWeatherMap call reserved for final M6 validation only; every other test uses mocked responses.
- **Disease-result integration test** — confirms the weather-context block never mutates or is read by the disease-analysis persistence path.
- **Security/secret-leak checks** — grep-style check that no API key or raw provider URL appears in a client-facing response or committed file.

## 16. Out-of-scope items

Everything in Section 3's "explicitly out of scope" list, plus (for M1
specifically): calling a production weather API, adding a provider SDK,
adding API keys, modifying Mongoose schemas, implementing API routes,
implementing UI, implementing the risk engine, persisting advisories,
any change to Phase 2 or its Docker setup, and any commit/push.

## 17. M2–M6 implementation plan

- **M2** — Farm location + crop settings (new `FarmProfile` schema, `/api/farm-profile` GET/PUT, settings UI section) and the OpenWeatherMap provider adapter + config module (current + forecast + geocoding), with unit tests. User adds `OPENWEATHER_API_KEY` themselves.
- **M3** — Normalization layer finalized against real (mocked-in-tests) provider responses; crop-risk engine implemented for Tomato/Potato with documented, reviewed thresholds; rule unit tests.
- **M4** — `Advisory` service + persistence, `/api/weather/advisory` and `/api/weather/advisories` routes, MongoDB persistence with re-validation.
- **M5** — Dashboard weather card, risk badge, forecast UI, advisory history UI, and the weather-context block beside disease results.
- **M6** — Real end-to-end validation (one live provider call), documentation, and formal sign-off (mirroring `PHASE_2_SIGN_OFF.md`'s shape).

## 18. Exact M2 scope boundary

M2 may: add `FarmProfile` schema + `/api/farm-profile` route + settings UI
section; add `src/lib/weather/config.ts` + `provider/openweather.ts` +
`geocoding.ts` + `types.ts` with unit tests (mocked HTTP only). M2 may
**not**: implement the risk engine (M3), persist advisories (M4), build the
dashboard weather card (M5), or run a real end-to-end validation (M6). The
user adds the API key to their own `.env.local`; Claude Code does not.

## 19. Known risks

- **Licensing drift**: if AgriAI's usage volume or commercial status
  changes materially, OpenWeatherMap's free-tier limits (60/min, 1M/month)
  should be re-checked against actual usage before M6 sign-off.
- **Agronomy accuracy**: Section 8's risk rules are a first, transparent
  approximation, not an agronomy-reviewed model — every threshold not
  backed by a citable source is flagged `requiresExpertReview: true` and
  must stay flagged in the UI until reviewed.
- **`FarmProfile` vs. `User` decision**: choosing a new collection (Section
  10) adds one more collection to reason about; the alternative (extending
  `User`) was rejected but could be revisited if a single-document view
  proves simpler in practice.
- **Free-tier daily forecast gap**: true daily aggregates require either
  computing rollups from the 3-hourly feed or a paid tier — deferred, not
  blocking M2–M6 as scoped.
- **No live-call verification yet**: M1 deliberately made zero real
  provider calls (credential-free docs only), so exact JSON field
  names/edge cases in Section 7 are based on documentation, not a live
  response, and should be spot-checked once M2 adds a real (user-supplied)
  key.

## 20. M1 completion criteria

- [x] Repository audited; integration points documented (Section 2).
- [x] Functional and non-functional requirements defined (Sections 3–4).
- [x] At least three providers compared using official docs; one selected with documented reasoning (Section 5, ADR).
- [x] Architecture and module boundaries defined (Section 6).
- [x] Normalized weather contract defined (Section 7).
- [x] Crop-risk engine design defined, scoped to Tomato/Potato (Section 8).
- [x] Phase 2 integration boundary defined, non-negotiable separation stated (Section 9).
- [x] Data-model proposal made and justified, no schema changes applied (Section 10).
- [x] API and UI proposed, not implemented (Sections 11–12).
- [x] Failure/safety and security/privacy controls defined (Sections 13–14).
- [x] Test strategy defined for M2–M6 (Section 15).
- [x] Out-of-scope and M2 boundary explicit (Sections 16, 18).
- [x] No credentials, schema changes, routes, UI, or commits introduced.
