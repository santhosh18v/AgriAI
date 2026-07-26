# Custom ML Runbook

Exact operational steps for running AgriAI's Phase 2 custom disease-ML
stack locally: MongoDB, the FastAPI ml-service, and Next.js in each of its
three provider modes. See [`PHASE_2_CUSTOM_DISEASE_ML.md`](PHASE_2_CUSTOM_DISEASE_ML.md)
for the architecture and [`CUSTOM_ML_LIMITATIONS.md`](CUSTOM_ML_LIMITATIONS.md)
for what this stack does *not* do. No credentials or real connection
strings appear in this document — every value below is a placeholder or a
non-sensitive local default.

## Required software

- Node.js 18+ and npm
- Python 3.13 (arm64 on Apple Silicon; see `ml-service/docs/MODEL_TRAINING.md`'s compatibility note for why this specific version)
- A MongoDB instance — either a local install/container, or a MongoDB Atlas cluster
- ~500 MB free disk for the ML service's Python virtual environment + PyTorch

## 1. Frontend install

```bash
cd AgriAI          # repo root
npm install
cp .env.local.example .env.local
# edit .env.local: fill in MONGODB_URI, NEXTAUTH_SECRET, GEMINI_API_KEY,
# GROQ_API_KEY at minimum. Never commit this file (it is gitignored).
```

## 2. ML-service virtual environment

```bash
cd ml-service
python3 -m venv .venv
source .venv/bin/activate
```

## 3. Dependency installation

```bash
# still inside ml-service/, with .venv activated
pip install -r requirements-training.txt
```

`requirements-training.txt` is the actual environment used for all
development and testing in this repo (training + the FastAPI runtime +
pytest) — it is a documented superset of `requirements.txt` (the
runtime-only set a deployed service would install). See
`ml-service/docs/MODEL_TRAINING.md` for why these pins target Python
3.13/arm64 specifically.

Optional: copy the ML-service env example if you need to override a
default (host/port/paths/CORS/upload limits):

```bash
cp .env.example .env   # ml-service/.env — gitignored, all settings optional
```

## 4. MongoDB options

**Option A — local Docker container:**

```bash
docker run -d --name agriai-mongodb -p 27017:27017 mongodb/mongodb-community-server:latest
```

Set in `.env.local`:
```
MONGODB_URI=mongodb://127.0.0.1:27017/agriai
```

**Option B — MongoDB Atlas:**

Create a free-tier cluster at [MongoDB Atlas](https://www.mongodb.com/cloud/atlas),
create a database user, and set:
```
MONGODB_URI=mongodb+srv://<user>:<password>@<your-cluster>.mongodb.net/agriai?retryWrites=true&w=majority
```
(`<...>` placeholders — never paste a real value into a tracked file.)

## 5. Safe environment setup

- `.env.local` (repo root) and `ml-service/.env` are both gitignored — never commit them, never paste secrets into any tracked file, chat log, or issue.
- For quick provider-mode switching without editing `.env.local`, the `CUSTOM_ML_*`/`DISEASE_ANALYSIS_PROVIDER` variables can be set as **temporary shell-exported environment variables** when launching `npm run dev` (see step 8 below) — Next.js gives shell-exported variables priority over `.env.local`.

## 6. Start MongoDB

- Docker option: `docker start agriai-mongodb` (if already created per step 4A), or the `docker run` command above the first time.
- Atlas option: nothing to start locally — just ensure `MONGODB_URI` in `.env.local` is correct.

Verify: the Next.js app will fail fast with a clear `MongooseServerSelectionError` in its own server log if it can't connect — see Troubleshooting below.

## 7. Start FastAPI

```bash
cd ml-service
source .venv/bin/activate
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Do not bind to `0.0.0.0`. Expect a log line confirming the model loaded
(architecture, class count, device, duration) before "Application startup
complete."

## 7B. Alternative: run FastAPI in Docker instead of a venv

Once the checkpoint exists locally (step 7B-1), Docker Compose can run
the ml-service instead of steps 2–3 and 7 — no manual venv activation or
`uvicorn` command needed day to day.

**Prerequisites:** Docker Desktop (or another Docker Engine +
`docker compose`) running locally; ~2 GB free disk for the image (CPU-only
PyTorch, no CUDA).

**7B-1. Obtain and place the checkpoint.** This file is gitignored and not
part of the repository, same as the venv path (step 3/"Model checkpoint
missing" below) — get it from wherever your team stores trained
checkpoints and place it at:

```
ml-service/data/training-runs/m4-efficientnet-b0-seed42/best_model.pt
```

**7B-2. Confirm its SHA-256** matches the value recorded in
`ml-service/training/confidence_policy_v1.json`
(`checkpoint_sha256`) — this is the same hash the service itself verifies
automatically at startup (native or Docker) before it will report ready:

```bash
shasum -a 256 ml-service/data/training-runs/m4-efficientnet-b0-seed42/best_model.pt
```

**7B-3. Start it** (from the repo root):

```bash
docker compose up -d ml-service
```

This builds `ml-service/Dockerfile` (see that file for what's baked in vs.
bind-mounted) and starts a container listening on `0.0.0.0:8001` inside
Docker, published to the host as `127.0.0.1:8001` — identical from
Next.js's point of view to the native `uvicorn` command in step 7. The
checkpoint is bind-mounted read-only from the path above; it is never
copied into the image or committed. The confidence policy, class map, and
model scope JSON files are tracked in git and are baked into the image.

**Logs:**

```bash
docker compose logs -f ml-service
```

Expect the same "Model loaded successfully" line as the native startup,
followed by `Uvicorn running on http://0.0.0.0:8001`.

**Status / health:**

```bash
docker compose ps                       # STATUS column shows "healthy" once /api/ready succeeds
docker compose exec ml-service python -c "import torch; print(torch.backends.mps.is_available())"  # always False in Docker
```

**Stop / restart:**

```bash
docker compose stop ml-service          # stop the container, keep it for next `up -d`
docker compose restart ml-service       # restart in place; the model reloads from the mounted checkpoint
docker compose down                     # remove the ml-service container (and its network); does not touch agriai-mongodb
```

**CPU vs. MPS:** the Docker container always runs on CPU
(`AGRI_ML_PREFERRED_DEVICE=cpu` is set in `docker-compose.yml`) — Linux
containers on Apple Silicon cannot use macOS's Metal/MPS API. The native
venv command in step 7 can still use MPS (`preferred_device: auto` picks
it up automatically on a Mac). Predictions are functionally equivalent
either way; inference latency differs (MPS is faster). No CUDA/GPU is
required in either mode.

**Docker-specific troubleshooting:** see also the shared entries below
("Model checkpoint missing", "Readiness returns 503", "Port 8001 already
in use").

- **Container immediately unhealthy / `/api/ready` returns 503** — almost
  always the checkpoint bind mount is missing or points at the wrong file
  (see 7B-1/7B-2), or the SHA-256 doesn't match the confidence policy.
  Check `docker compose logs ml-service` for the sanitized failure reason.
- **`docker compose up` fails to build** — confirm Docker Desktop has
  network access to `download.pytorch.org` and `pypi.org` (the build
  installs a CPU-only PyTorch wheel explicitly, to avoid pulling
  CUDA-bundled Linux wheels).
- **Port 8001 already in use** — a native `uvicorn` process (step 7) is
  probably already running; stop one or the other, don't run both at once.

## 8. Verify health/readiness/model-info

```bash
curl http://127.0.0.1:8001/api/health
curl http://127.0.0.1:8001/api/ready
curl http://127.0.0.1:8001/api/model-info
```

Expect: `/api/health` → `{"status":"ok",...}`; `/api/ready` →
`{"status":"ready","model_loaded":true,"confidence_policy_loaded":true,"class_count":6}`;
`/api/model-info` → `class_count: 6`, `threshold: 0.5`,
`production_calibrated: false`.

These checks are identical whether the service is running natively (step
7) or in Docker (step 7B) — `docker compose` publishes the same
`127.0.0.1:8001` address.

## 9. Start Next.js in Gemini mode (default)

```bash
npm run dev
```

No special environment variables needed — `DISEASE_ANALYSIS_PROVIDER`
defaults to `gemini` if unset in `.env.local`.

## 10. Start Next.js in custom-ML-only mode

```bash
CUSTOM_ML_ENABLED=true \
DISEASE_ANALYSIS_PROVIDER=custom-ml \
CUSTOM_ML_SERVICE_URL=http://127.0.0.1:8001 \
CUSTOM_ML_FALLBACK_TO_GEMINI=false \
CUSTOM_ML_REQUIRE_READY_CHECK=true \
npm run dev
```

Every crop-disease image analysis now goes to the custom model only; a
custom-ml failure returns a safe error rather than silently trying Gemini.

## 11. Start Next.js with Gemini fallback

Same as step 10, but with `CUSTOM_ML_FALLBACK_TO_GEMINI=true`. An
infrastructure failure (ml-service down/timeout/malformed response) now
falls back to Gemini automatically; a user-caused 4xx (bad/oversized/
unsupported image) never falls back, regardless of this flag.

## 12. Perform a prediction

Through the UI: log in, go to the crop scanner (`/dashboard/scan`), select
"Crop Disease," upload a leaf photo, and submit.

Through the API directly (useful for scripting/debugging — requires a
valid authenticated session cookie):

```bash
curl -b cookies.txt -X POST http://localhost:3000/api/analyze \
  -F "type=crop_disease" \
  -F "query=spots on my tomato leaves" \
  -F "cropName=Tomato" \
  -F "image=@/path/to/leaf.jpg;type=image/jpeg"
```

## 13. Inspect history

```bash
curl -b cookies.txt http://localhost:3000/api/history
```

Or through the UI at `/dashboard/history`.

## 14. Stop services

- Next.js: `Ctrl+C` in its terminal (or `kill <pid>`).
- FastAPI (native, step 7): `Ctrl+C` in its terminal (or `kill <pid>`).
- FastAPI (Docker, step 7B): `docker compose stop ml-service` (or
  `docker compose down` to also remove the container/network — see 7B for
  details). Never run the native and Docker FastAPI at the same time; both
  bind `127.0.0.1:8001`.
- MongoDB (Docker): `docker stop agriai-mongodb` — only stop it if you started it yourself for this session; don't stop a container other developers/services depend on. `docker compose down`/`up` for `ml-service` never starts, stops, or otherwise touches `agriai-mongodb`.

## Troubleshooting

**Port 3000 already in use**
Another `next dev` is already running (check `lsof -iTCP -sTCP:LISTEN -P | grep 3000`), or start this one on a different port: `npm run dev -- -p 3002`.

**Port 8001 already in use**
Another ml-service instance is already running — reuse it, or pick a different port: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8002` and update `CUSTOM_ML_SERVICE_URL` to match.

**System Python missing uvicorn**
You're not inside the virtual environment. Run `source ml-service/.venv/bin/activate` first (or recreate it per step 2–3 if it doesn't exist yet).

**Virtual environment activation fails / "command not found"**
Recreate it: `cd ml-service && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements-training.txt`.

**Model checkpoint missing**
`GET /api/ready` will report `model_loaded: false` (or startup will fail) if `data/training-runs/m4-efficientnet-b0-seed42/best_model.pt` doesn't exist locally. This file is gitignored and not part of the repository — obtain it from wherever your team stores trained checkpoints, or retrain it yourself following `ml-service/docs/MODEL_TRAINING.md` (Phase 2 milestone work — do not do this casually, it is a deliberate, seeded, documented process).

**Readiness returns 503**
Either the model failed to load (check the FastAPI startup log for the failure reason) or the confidence policy file is missing/invalid. Confirm `training/confidence_policy_v1.json` exists and check the checkpoint-hash cross-validation the service performs at startup.

**MongoDB connection refused**
`ECONNREFUSED` on `127.0.0.1:27017` means nothing is listening there — start your local MongoDB (step 6, Option A) or confirm you actually intended to use Atlas (Option B) and that `MONGODB_URI` in `.env.local` reflects that choice.

**Incorrect `MONGODB_URI`**
Symptoms: `MongooseServerSelectionError` in the Next.js server log at request time. Fix `.env.local` directly (never paste the real value elsewhere) and restart `npm run dev` — Next.js does not always hot-reload every `.env.local` change reliably; restarting the dev process is the reliable fix.

**Invalid Gemini key**
Any Gemini-involving request (default Gemini mode, or a custom-ml fallback/secondary-opinion attempt) fails with a generic sanitized `500`/error; the real reason (`API_KEY_INVALID` from Google's API) is logged server-side only, never returned to the client. Get/refresh a key at [Google AI Studio](https://aistudio.google.com/app/apikey) and update `GEMINI_API_KEY` in `.env.local`.

**CORS issues**
The ml-service's `AGRI_ML_CORS_ORIGINS` defaults to `http://localhost:3000,http://127.0.0.1:3000`. If Next.js runs on a different port (e.g. `3002`), the browser calls Next.js directly (not the ml-service — the ml-service is only ever called server-side by Next.js), so this normally isn't a concern for the standard flow; it only matters if something calls the ml-service directly from a browser.

**Unsupported image**
`UNSUPPORTED_MEDIA_TYPE` (415) — the file's extension/MIME type isn't one of `.jpg/.jpeg/.png/.webp`. Use a supported format.

**Oversized image**
`IMAGE_TOO_LARGE` (413) — the ml-service's default limit is 10 MB (`AGRI_ML_MAX_UPLOAD_BYTES`). Use a smaller image or raise the limit in `ml-service/.env` if you have a specific reason to.

**Model service unavailable**
`ML_SERVICE_UNAVAILABLE` (503) — the ml-service process isn't reachable at `CUSTOM_ML_SERVICE_URL`. Confirm it's running (step 7–8) and the URL/port match.

**No naturally uncertain result**
On this dataset, the frozen threshold (0.50) rejects essentially nothing (0 of 991 frozen-test predictions) — most real images you try will come back `accepted: true`. This is expected and documented (see [`CUSTOM_ML_LIMITATIONS.md`](CUSTOM_ML_LIMITATIONS.md)); it is not a bug, and you should not treat a lack of naturally-uncertain results as something to "fix." Uncertain-flow behavior (the low-confidence UI warning, optional secondary opinion) is covered by the automated test suite instead.
