# Phase 2 Sign-Off Record

- **Branch**: `phase-2-custom-disease-ml`
- **Sign-off date**: 2026-07-26 (UTC)
- **Latest commit before M11 documentation work**: `9e99c14` — "docs: record custom ML end-to-end validation"

## Phase 2 objective

Build a reproducible custom crop-disease image-classification system (an
AgriAI-owned EfficientNet-B0 model for six Tomato/Potato classes) and
integrate it into the existing AgriAI Next.js application through a Python
FastAPI service, as an additive, feature-flagged alternative to the
existing Gemini-based disease-analysis flow — never replacing it, never
silently degrading it.

## Milestone table (M1–M11)

| Milestone | Scope | Status |
|---|---|---|
| M1 | ML service foundation (scaffold, config, class map) | ✅ Complete |
| M2 | Dataset source, licence, and provenance decisions | ✅ Complete |
| M3 | Dataset discovery, grouping, deterministic splitting, independent leakage validation | ✅ Complete |
| M4 | EfficientNet-B0 baseline training (reproducible, validation-only model selection) | ✅ Complete |
| M5 | One-time frozen test evaluation + validation-only confidence threshold selection | ✅ Complete |
| M6 | FastAPI health/readiness/model-info endpoints | ✅ Complete |
| M7 | Disease image prediction endpoint (`POST /api/predict/disease`) | ✅ Complete |
| M8 | Next.js custom-ML provider integration (feature flags, fallback policy) | ✅ Complete |
| M9 | MongoDB persistence of custom-ML metadata + result/history UI | ✅ Complete |
| M10 | Real, authenticated end-to-end validation against running services | ✅ Complete, with disclosed limitations |
| M11 | Final documentation, release-readiness review, sign-off | ✅ Complete (this document) |

## Final automated test totals

| Check | Result |
|---|---|
| `npm test` (vitest) | **165/165 passed**, 9 test files |
| `npx tsc --noEmit` | Clean, zero errors |
| `npm run lint` | Clean, zero warnings |
| `npm run build` | Succeeds, all 16 routes compile |
| `python -m pytest -q` (ml-service) | **177/177 passed**, 16 test files (9 `tests/api/`, 7 `tests/training/`) |
| `python -m py_compile app/*.py app/routes/*.py training/*.py` | Clean |
| `python training/validate_splits.py` (read-only) | `approved_for_training`, 6,634 rows, 70/70 checks, zero blocking failures |

## Final model metrics (frozen, one-time test evaluation)

| Metric | Value |
|---|---|
| Frozen test accuracy | **0.9889** |
| Frozen test macro-F1 | **0.9841** |
| Test samples | 991 |
| Coverage at selected threshold | 100% (0 rejected) |

## Final manifest hashes and dataset counts

| Manifest | Rows | SHA-256 |
|---|---:|---|
| train.csv | 4,642 | `3bec912c0efb7a22eb66b388c364be6ab784ce3e8637ffe716c0804655b99a79` |
| val.csv | 1,001 | `85f86dec9e81566b19d0654559f6b56c11d4b7086f3d5b8d244e00cae91dd91f` |
| test.csv | 991 | `3d0ee43d9edc836eefadb71bf178d55d3e60817053efa5f9f5a52cd04c284abb` |
| **Total** | **6,634** | |

6 active classes; Corn excluded from scope; 14 exact duplicates excluded;
4 quarantined active-scope images excluded; zero cross-split leakage
(file path, SHA-256, leaf-ID group, and similarity-guard group — all
independently re-verified via `validate_splits.py`, not just the original
generator's own self-report).

## Checkpoint hash and confidence threshold

- **Checkpoint SHA-256**: `24e7244ed2970ec3aac50be870f0de80f42d52baf30cd80b429ff67e9d001081`
- **Confidence threshold**: **0.50**, `status: approved_for_test_application`, selected from validation predictions only, `production_calibrated: false`

## FastAPI endpoints

`GET /api/health`, `GET /api/ready`, `GET /api/model-info`,
`POST /api/predict/disease` — see
[`PHASE_2_CUSTOM_DISEASE_ML.md`](PHASE_2_CUSTOM_DISEASE_ML.md) §12 for the
full contract summary and links to detailed docs.

## Integration status

Next.js custom-ML provider adapter (`src/lib/disease-analysis/`) complete:
strict upstream-response validation, feature-flag-gated provider
selection, infra-failure-only Gemini fallback, optional uncertain-result
secondary opinion — all additive to the pre-existing Gemini/Groq flows,
which are unmodified.

## Persistence status

`Analysis` documents additively carry `customMl`, `providerMetadata`,
`secondaryOpinion` (when applicable), and `resultVersion` alongside the
pre-existing legacy fields — independently re-validated at the persistence
boundary (not merely trusting the upstream adapter). Legacy (pre-M9)
documents remain valid and render safely with no migration performed. See
[`CUSTOM_ML_RESULT_SCHEMA.md`](CUSTOM_ML_RESULT_SCHEMA.md).

## M10 real end-to-end status

`m10_complete_with_disclosed_limitations`. Verified against real running
services (real MongoDB, real FastAPI process with the real checkpoint, a
real authenticated NextAuth session): 4/4 real predictions on `val.csv`
images matched their expected class; persistence, history/refresh,
concurrency, failure/recovery, and invalid-input handling all confirmed
against the real stack. Full results:
[`CUSTOM_ML_E2E_VALIDATION.md`](CUSTOM_ML_E2E_VALIDATION.md).

## Known limitations (full detail: [`CUSTOM_ML_LIMITATIONS.md`](CUSTOM_ML_LIMITATIONS.md))

- Controlled, lab-style image dataset — not real farm-field photography; no production-generalization claim.
- Six classes only; Corn excluded (no defensible grouping metadata).
- Potato Healthy has only 38 leaf groups (6 each in validation/test) — thinner statistical support than the other five classes.
- Confidence is a model score, not certainty; not production-calibrated; one frozen-test error carried confidence near 1.0.
- Threshold alone does not detect out-of-distribution inputs.
- Gemini-involving fallback/secondary-opinion paths were not live-verified end-to-end (invalid local credential during M10) — verified via the automated test suite instead.
- No naturally uncertain real prediction was observed during M10.
- Real browser visual verification was not completed during M10.
- No cloud deployment has been performed for either service.
- Minor, non-blocking dependency-hygiene note: `ml-service/requirements-training.txt` lists `pandas`/`matplotlib`/`seaborn`, none of which are installed in the current venv or imported by any tracked code — harmless (all 177 ml-service tests pass without them) but worth a future cleanup pass; not changed during M11 per its "no unnecessary code/config changes" scope.

## Security scan status

Tracked repository scanned for MongoDB URIs with embedded credentials,
API-key patterns, bearer tokens, private keys, password literals,
`/Users/` absolute paths, base64 image blobs, and stack traces —
**none found**. `.env.local` and `ml-service/.env` confirmed ignored and
untracked. No model checkpoint, dataset image, CSV split manifest, virtual
environment, or log file is tracked in Git. Largest tracked file is
`package-lock.json` (328 KB) — no unexpected large binaries.

## Merge-readiness status

**`ready_with_disclosed_limitations`**

- All M1–M10 implementation is complete and independently re-verified in M11.
- Final automated checks pass (frontend and ML-service).
- No real secret exposure found.
- The working tree contains only the intended M11 documentation additions/edits (no generated binaries, model weights, or dataset images staged — none exist in the working tree at all).
- No known blocking runtime defect was found or introduced during M11 (M11 was documentation/audit only — no application code was changed).
- Known limitations are fully documented (above and in `CUSTOM_ML_LIMITATIONS.md`) and do not prevent normal local development use.
- `main` has not moved since this branch's merge-base (0 commits ahead on `main`, 15 on this branch) — a dry-run merge (`git merge-tree`) produced a clean auto-merge with no conflicts.

## Files intentionally excluded from Git

PlantVillage source images, `train.csv`/`val.csv`/`test.csv` and all
generated split reports, `best_model.pt`/`last_model.pt` and all
training-run/evaluation-run outputs, local MongoDB data files,
`.env.local`/`ml-service/.env`, both virtual environments
(`node_modules/`, `ml-service/.venv/`), all logs, and any temporary
uploaded image (the ML service never writes an uploaded image to disk in
the first place). See [`CUSTOM_ML_RUNBOOK.md`](CUSTOM_ML_RUNBOOK.md) for
how another developer obtains or regenerates each of these locally.

## Exact next step after this sign-off

1. Review the M11 diff (documentation only — see the M11 completion report's git summary).
2. Commit the M11 documentation.
3. Push the branch.
4. Open a pull request against `main`.
5. Review and merge **only after final human approval** — this sign-off records readiness for a pull request, not a completed merge. The branch has not been merged as of this document.
