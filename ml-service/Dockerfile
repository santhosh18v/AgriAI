# AgriAI ml-service -- Phase 2 custom disease-ML FastAPI container.
#
# Runs CPU-only inference. The model checkpoint is NOT baked into this
# image (it is gitignored and never committed); it must be bind-mounted
# read-only at container run time -- see ../docker-compose.yml. The
# confidence policy / class map / model scope JSON files ARE tracked in
# git (non-secret, small config), so they are copied in below rather than
# mounted.
#
# Apple Silicon note: this container never uses macOS MPS -- MPS is a
# host-only, non-Linux acceleration API. Native `uvicorn` runs on this
# Mac can use MPS (AGRI_ML_PREFERRED_DEVICE=auto/mps); this container
# always runs on CPU. Predictions are functionally equivalent either way;
# inference latency will differ. No CUDA/GPU is required or used.
FROM python:3.13-slim

# libgomp1: OpenMP runtime required by PyTorch's CPU kernels on Debian.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./

# Install the CPU-only PyTorch build explicitly first: the default PyPI
# index resolves torch's Linux wheels to CUDA-bundled builds (multi-GB);
# this container has no GPU and must not require CUDA. The subsequent
# `pip install -r requirements.txt` sees torch/torchvision already
# satisfied at the pinned versions and only installs the remaining
# (non-torch) runtime dependencies from PyPI.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
        torch==2.7.1 torchvision==0.22.1 \
    && pip install --no-cache-dir -r requirements.txt

# Application code.
COPY app ./app

# Only the training/ modules and tracked config files app/model_loader.py
# actually imports/reads at startup -- not the training scripts, dataset
# tooling, or docs.
COPY training/__init__.py training/dataset.py training/model.py ./training/
COPY training/class_map.json training/model_scope_v1.json training/confidence_policy_v1.json ./training/

RUN useradd --create-home --uid 1000 agriml \
    && chown -R agriml:agriml /app
USER agriml

ENV PYTHONUNBUFFERED=1

EXPOSE 8001

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/api/ready', timeout=3)"

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
