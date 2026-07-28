# Phase 3 — Weather Provider Decision (ADR)

**Status: decided for M1. No credentials added, no provider called with a
real key. Verification below used only documentation-safe, credential-free
requests (public docs pages).**

## Context

Phase 3 needs a weather data source that can supply, per farm location:
current conditions, a short-term forecast, and enough fields (temperature,
humidity, precipitation, wind) to drive a transparent crop-risk engine
(Section 7 of the main plan). AgriAI already has a precedent for
third-party AI providers (`GEMINI_API_KEY`, `GROQ_API_KEY` — both
server-side-only secrets, validated at a config boundary, never sent to the
browser; see `src/lib/disease-analysis/config.ts`). The weather provider
should fit that same shape.

## Providers compared

| | Open-Meteo | OpenWeatherMap | WeatherAPI.com |
|---|---|---|---|
| Current weather | Yes (15-min model data) | Yes | Yes |
| Hourly forecast | Yes, 50+ variables, 7–16 days | Yes, 3-hourly, 5 days (free) | Yes, hourly, 3 days (free) |
| Daily forecast | Yes, 30+ aggregated variables | Only via paid One Call 3.0, or client-side rollup of the free 3-hourly feed | Yes, up to 3 days (free) |
| Geocoding | Dedicated Geocoding API (GeoNames-based), free, no key | Bundled Geocoding API, free | Search/Autocomplete endpoint |
| Auth | None for free/non-commercial tier | API key required (query param) | API key required (query param) |
| Free-tier rate limit | 600/min, 5,000/hr, 10,000/day, 300,000/month | 60/min, 1,000,000/month | 100,000/month |
| **Commercial use on free tier** | **Explicitly prohibited** ("free API is for non-commercial use") | **Explicitly permitted** | Explicitly permitted |
| Attribution required | Not stated | Not required on free tier | Requested (backlink or logo on free tier) |
| India coverage | Global NWP models (ECMWF/GFS/ICON) — not region-restricted | Long-established India coverage | Not confirmed in docs reviewed |
| TS/local-dev ergonomics | Plain JSON REST, zero setup (no key) | Plain JSON REST, needs a key from signup | Plain JSON REST, needs a key from signup |

Sources: Open-Meteo docs (`/en/docs`, `/en/pricing`, `/en/docs/geocoding-api`),
OpenWeather docs (`/api/one-call-3`, `/price`), WeatherAPI docs
(`/docs/`, `/pricing.aspx`) — fetched during M1, no API key used.

## Decision

**Selected: OpenWeatherMap**, using the free-tier **Current Weather API
2.5**, **5 Day / 3 Hour Forecast API 2.5**, and **Geocoding API 2.5**.

### Why

1. **Commercial-use clarity.** AgriAI is a contest entry today but the
   README already frames it as a real product; Open-Meteo's free tier
   *explicitly prohibits commercial use*, which is a licensing gate, not a
   technicality, and not something to build M2–M6 against and discover
   later. OpenWeatherMap's free tier explicitly permits commercial use at
   generous limits (60 calls/min, 1,000,000 calls/month).
2. **Fits the existing secret-handling convention.** OpenWeatherMap
   requires a server-side API key — the same shape as `GEMINI_API_KEY` /
   `GROQ_API_KEY`, so the Phase 3 provider config module can mirror
   `disease-analysis/config.ts`'s validated, fail-fast pattern almost
   exactly (see Section 5 of the main plan).
3. **India coverage** is well-established and long-standing for
   OpenWeatherMap specifically (in contrast to WeatherAPI, where the
   docs reviewed did not confirm regional coverage detail).
4. **Sufficient for the required scope.** Current weather + a 5-day/3-hour
   forecast covers every field Section 6 of the main plan requires
   (temperature, humidity, precipitation, rain probability, wind). Daily
   aggregates are not needed for M1's scope and can be computed from the
   3-hourly feed inside the normalization layer if a later milestone needs
   them — no paid tier required for that.
5. **No SDK required.** Like the existing `predictWithCustomMl` adapter
   (plain `fetch`, strict response validation, no vendor SDK), OpenWeather's
   REST endpoints can be called the same way.

### Rejected alternatives

- **Open-Meteo** — otherwise the strongest technical fit (no key, highest
  free rate limits, cleanest schema, dedicated geocoding), but the
  non-commercial restriction on its free tier is disqualifying for a
  primary provider. Documented here as a candidate for a **local-dev-only
  convenience or a secondary/reference data source**, never as the
  production path, and only after a fresh licence review if that is ever
  proposed.
- **WeatherAPI.com** — commercial use is permitted, but the free tier's
  forecast horizon (3 days) is shorter than OpenWeatherMap's (5 days), it
  requires a visible attribution backlink/logo (an added UI/legal
  obligation this app does not currently have for any provider), and its
  India-specific coverage was not confirmed in the docs reviewed.

### Known limitations of the decision

- OpenWeatherMap's free daily-forecast product is paid; any future need
  for true multi-day daily aggregates (beyond what M1–M6 requires) means
  either computing daily rollups from the 3-hourly feed or re-opening this
  ADR to evaluate a paid tier.
- Free-tier uptime is not SLA-backed. The system must degrade safely
  (Section 12 of the main plan) rather than assume availability.
- This ADR is a **provider selection**, not a credential setup. No key is
  requested, stored, or used until M2, and M2 must not add it to
  `.env.local` without the user doing so themselves per the project's
  security rules.

### Fallback strategy (design-only, not implemented in M1–M6 unless a later
ADR revises this)

No second live weather provider is proposed for M1–M6 — adding one now
would be premature complexity for a system that doesn't have a single
provider integrated yet. Availability is instead handled by:

1. Serving the last successfully cached normalized snapshot for that
   location, explicitly marked `stale`, within a bounded staleness window.
2. If no cached snapshot exists (or it has exceeded the staleness window),
   returning an explicit "weather information is currently unavailable"
   result — never a fabricated or default value (see Section 12 of the
   main plan).
