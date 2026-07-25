"""Configuration templates for the ml-service.

This module only defines constants. It does not load a model, run
inference, or read the dataset. Values marked "dev placeholder" are not
final — thresholds will be selected from validation-set data once a model
exists (see plan Milestone M5), and this file will be updated then.
"""

import os
from pathlib import Path

# --- Paths -------------------------------------------------------------

ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = ML_SERVICE_ROOT / "models"
DATA_DIR = ML_SERVICE_ROOT / "data"
CLASS_MAP_PATH = ML_SERVICE_ROOT / "training" / "class_map.json"
MODEL_MANIFEST_PATH = MODEL_DIR / "version.json"

MODEL_PATH = os.environ.get("MODEL_PATH", str(MODEL_DIR / "efficientnet_b0.pt"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "info")

# --- Class list (must match training/class_map.json exactly) -----------

NUM_CLASSES = 8

# --- Image preprocessing (must match training-time preprocessing) ------

INPUT_SIZE = (224, 224)
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)

# --- Upload validation ---------------------------------------------------

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB, matches existing client-side limit
ALLOWED_CONTENT_TYPES = ("image/jpeg", "image/png", "image/webp")
MAX_IMAGE_DIMENSION_PX = 8000  # decompression-bomb / excessive-dimension guard

# --- Confidence thresholds (DEV PLACEHOLDERS — not yet selected from data) --
#
# These values are only used for local development and mocked tests before
# a trained model exists. The real thresholds are selected from the
# validation split at Milestone M5 (accuracy-vs-coverage / precision-error
# sweep) and recorded in models/version.json as `uncertainty_threshold`.
# GET /model/info is the source of truth once a model is loaded.

DEV_UNCERTAIN_CONFIDENCE_THRESHOLD = 0.60
DEV_LOW_RELIABILITY_CONFIDENCE_THRESHOLD = 0.35
DEV_LOW_RELIABILITY_MARGIN_THRESHOLD = 0.10

TOP_K_PREDICTIONS = 3
