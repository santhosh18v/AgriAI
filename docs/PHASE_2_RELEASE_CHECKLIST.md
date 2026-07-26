# Phase 2 Release Checklist

A practical checklist for another developer picking up this branch, or
for whoever opens/reviews the pull request. See
[`CUSTOM_ML_RUNBOOK.md`](CUSTOM_ML_RUNBOOK.md) for the detailed steps
behind each item, and [`PHASE_2_SIGN_OFF.md`](PHASE_2_SIGN_OFF.md) for the
formal sign-off this checklist supports.

## Environment setup

- [ ] Node.js 18+ and npm installed
- [ ] Python 3.13 (arm64 on Apple Silicon) installed
- [ ] Repo cloned, on branch `phase-2-custom-disease-ml`
- [ ] `.env.local` created from `.env.local.example` (never commit it)
- [ ] `ml-service/.env` created from `ml-service/.env.example` if any non-default setting is needed (optional — the service runs with safe defaults if absent)

## Dependency installation

- [ ] `npm install` succeeds at repo root
- [ ] `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements-training.txt` succeeds in `ml-service/`

## Model checkpoint availability

- [ ] `ml-service/data/training-runs/m4-efficientnet-b0-seed42/best_model.pt` exists locally (obtained or regenerated — never committed)
- [ ] Its SHA-256 matches `24e7244ed2970ec3aac50be870f0de80f42d52baf30cd80b429ff67e9d001081`

## MongoDB connectivity

- [ ] A MongoDB instance is reachable (local Docker container or Atlas)
- [ ] `MONGODB_URI` in `.env.local` is correct for that instance
- [ ] Registration/login through the app succeeds (confirms the connection works end to end)

## FastAPI health/readiness

- [ ] `python -m uvicorn app.main:app --host 127.0.0.1 --port 8001` starts cleanly
- [ ] `GET /api/health` → 200
- [ ] `GET /api/ready` → 200, `model_loaded: true`, `confidence_policy_loaded: true`, `class_count: 6`
- [ ] `GET /api/model-info` → `threshold: 0.5`, `production_calibrated: false`

## Next.js startup

- [ ] `npm run dev` starts with no build/config errors
- [ ] Home page loads at `http://localhost:3000`

## Feature flags

- [ ] Default (Gemini) mode works: crop-disease image analysis returns a result
- [ ] Custom-ML mode works: `CUSTOM_ML_ENABLED=true`, `DISEASE_ANALYSIS_PROVIDER=custom-ml` — analysis is served by the custom model
- [ ] An invalid flag combination (e.g. `DISEASE_ANALYSIS_PROVIDER=custom-ml` with `CUSTOM_ML_ENABLED=false`) fails fast with a clear configuration error, not a silent fallback

## Valid image prediction

- [ ] A real leaf photo (or a `val.csv`/`train.csv` image) submitted through the crop scanner returns a prediction from one of the six approved classes
- [ ] `accepted`/`uncertain` are logical opposites; `confidenceLabel` is `"model confidence"`; `productionCalibrated` is `false`

## Persistence / history

- [ ] The analysis appears in `GET /api/history` after submission
- [ ] `analysisCount` on the user's profile incremented by exactly 1
- [ ] Refreshing the history page shows the same record consistently
- [ ] A pre-existing (pre-M9) history record, if any, still renders without crashing

## Tests

- [ ] `npm test` — all pass
- [ ] `npx tsc --noEmit` — clean
- [ ] `npm run lint` — clean
- [ ] `cd ml-service && python -m pytest -q` — all pass

## Build

- [ ] `npm run build` succeeds

## Secrets scan

- [ ] No MongoDB URI, API key, bearer token, or private key found in tracked files (`git ls-files` + grep for known patterns)
- [ ] `.env.local` and `ml-service/.env` are untracked (`git ls-files` does not list them)

## Ignored files

- [ ] `git status` shows a clean working tree before opening the PR
- [ ] No model checkpoint, dataset image/CSV, virtual environment, or log file appears in `git ls-files`

## PR creation

- [ ] Branch pushed to `origin`
- [ ] PR opened against `main`, referencing [`PHASE_2_SIGN_OFF.md`](PHASE_2_SIGN_OFF.md)
- [ ] PR description links the key Phase 2 docs (this checklist, the sign-off record, the limitations doc)

## Post-merge verification

- [ ] After merge, re-run the full checklist above once more on a fresh clone of `main`
- [ ] Confirm the deployed/default environment still defaults to Gemini (`CUSTOM_ML_ENABLED` unset or `false`) unless custom-ML mode is explicitly intended for that environment
