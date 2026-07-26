"""Safe, validated, load-once model loading (Milestone M6).

Loads and cross-checks the approved class map, model scope, and frozen
confidence policy, verifies the checkpoint's SHA-256 and architecture
against that policy, reconstructs EfficientNet-B0 via training/model.py,
and loads model weights (state_dict only, never a pickled full model).
Exposes immutable, API-safe metadata and a sanitized failure state.

Does not implement image preprocessing or inference -- that is M7 scope.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import torch

# training/ is not an installed package -- flat-import it the same way
# training/evaluate.py and tests/training/conftest.py already do.
TRAINING_DIR = Path(__file__).resolve().parent.parent / "training"
if str(TRAINING_DIR) not in sys.path:
    sys.path.insert(0, str(TRAINING_DIR))

from dataset import load_active_classes, load_class_index_by_name  # noqa: E402
from model import ARCHITECTURE_NAME, build_model, select_device  # noqa: E402

logger = logging.getLogger("agri_ml.model_loader")

REQUIRED_ACTIVE_CLASS_COUNT = 6
SUPPORTED_CONFIDENCE_METHODS = {"maximum_softmax_probability"}
APPROVED_POLICY_STATUS = "approved_for_test_application"
INPUT_IMAGE_SIZE = 224  # must match training/train.py's IMAGE_SIZE


class ModelLoadError(Exception):
    """A validation or loading failure. Messages must stay sanitized -- no
    local absolute paths, no raw tracebacks, no checkpoint internals."""


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class ModelMetadata:
    """Immutable, API-safe model metadata. Deliberately excludes any
    filesystem path, checkpoint internals, or optimizer state."""

    architecture: str
    model_version: str
    class_count: int
    classes: Tuple[str, ...]
    input_width: int
    input_height: int
    input_channels: int
    confidence_method: str
    confidence_threshold: float
    confidence_production_calibrated: bool
    frozen_test_accuracy: Optional[float]
    frozen_test_macro_f1: Optional[float]
    dataset_context: str
    limitations: Tuple[str, ...]
    device: str


def _validate_and_build(settings) -> Tuple[torch.nn.Module, ModelMetadata]:
    checkpoint_path = settings.resolved_model_checkpoint_path()
    policy_path = settings.resolved_confidence_policy_path()
    class_map_path = settings.resolved_class_map_path()
    model_scope_path = settings.resolved_model_scope_path()

    for label, path in (
        ("class map", class_map_path),
        ("model scope", model_scope_path),
        ("confidence policy", policy_path),
        ("checkpoint", checkpoint_path),
    ):
        if not path.is_file():
            raise ModelLoadError(f"required {label} file is missing")

    try:
        class_index_by_name = load_class_index_by_name(class_map_path)
        active_classes = load_active_classes(model_scope_path)
    except Exception as e:
        raise ModelLoadError("class map / model scope validation failed") from e

    if len(active_classes) != REQUIRED_ACTIVE_CLASS_COUNT:
        raise ModelLoadError(
            f"expected {REQUIRED_ACTIVE_CLASS_COUNT} active classes, found {len(active_classes)}"
        )

    try:
        with open(policy_path) as f:
            policy = json.load(f)
    except Exception as e:
        raise ModelLoadError("confidence policy failed to parse") from e

    if policy.get("status") != APPROVED_POLICY_STATUS:
        raise ModelLoadError("confidence policy is not approved")
    if policy.get("model_architecture") != ARCHITECTURE_NAME:
        raise ModelLoadError("confidence policy architecture does not match the expected architecture")
    if policy.get("confidence_method") not in SUPPORTED_CONFIDENCE_METHODS:
        raise ModelLoadError("confidence policy uses an unsupported confidence method")

    threshold = policy.get("selected_threshold")
    if threshold is None or isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise ModelLoadError("confidence policy threshold is not numeric")

    actual_checkpoint_sha256 = _sha256_file(checkpoint_path)
    if actual_checkpoint_sha256 != policy.get("checkpoint_sha256"):
        raise ModelLoadError("checkpoint does not match the approved confidence policy")

    device = select_device(settings.preferred_device)

    try:
        ckpt = torch.load(checkpoint_path, map_location=device, weights_only=False)
    except Exception as e:
        raise ModelLoadError("checkpoint failed to load") from e

    if ckpt.get("architecture") != ARCHITECTURE_NAME:
        raise ModelLoadError("checkpoint architecture does not match the expected architecture")

    class_names = ckpt.get("class_names")
    class_to_index = ckpt.get("class_to_index")
    expected_class_to_index = {name: class_index_by_name[name] for name in active_classes}
    if class_to_index != expected_class_to_index:
        raise ModelLoadError("checkpoint class mapping does not match the approved active scope")
    expected_class_names = [name for name, _ in sorted(expected_class_to_index.items(), key=lambda kv: kv[1])]
    if class_names != expected_class_names:
        raise ModelLoadError("checkpoint class order does not match the approved active scope")

    try:
        model = build_model(num_classes=len(class_names), pretrained=False)
        model.load_state_dict(ckpt["model_state_dict"])  # state_dict only, never a pickled full model
    except Exception as e:
        raise ModelLoadError("model construction or weight loading failed") from e

    model.to(device)
    model.eval()

    metadata = ModelMetadata(
        architecture=ARCHITECTURE_NAME,
        model_version=checkpoint_path.parent.name,
        class_count=len(class_names),
        classes=tuple(class_names),
        input_width=INPUT_IMAGE_SIZE,
        input_height=INPUT_IMAGE_SIZE,
        input_channels=3,
        confidence_method=policy["confidence_method"],
        confidence_threshold=float(threshold),
        confidence_production_calibrated=False,
        frozen_test_accuracy=settings.frozen_test_accuracy,
        frozen_test_macro_f1=settings.frozen_test_macro_f1,
        dataset_context=settings.dataset_context,
        limitations=tuple(settings.model_limitations),
        device=str(device),
    )
    return model, metadata


class ModelLoader:
    """Loads the approved model at most once per process.

    Thread-safe: concurrent callers to `load()` block on the same
    initialization and every caller observes the same final state. Once
    loaded (or once failed), `load()` is a no-op -- there is no retry-on-
    every-request behavior and no per-request model mutation, since M6
    performs no inference.
    """

    def __init__(self, settings):
        self._settings = settings
        self._lock = threading.Lock()
        self._loaded = False
        self._model: Optional[torch.nn.Module] = None
        self._metadata: Optional[ModelMetadata] = None
        self._failure_reason: Optional[str] = None
        self._load_duration_seconds: Optional[float] = None

    @property
    def is_ready(self) -> bool:
        return self._loaded and self._model is not None

    @property
    def failure_reason(self) -> Optional[str]:
        return self._failure_reason

    @property
    def metadata(self) -> Optional[ModelMetadata]:
        return self._metadata

    @property
    def load_duration_seconds(self) -> Optional[float]:
        return self._load_duration_seconds

    def load(self) -> None:
        with self._lock:
            if self._loaded or self._failure_reason is not None:
                return  # idempotent: already loaded, or already failed once
            start = time.monotonic()
            try:
                model, metadata = _validate_and_build(self._settings)
            except ModelLoadError as e:
                self._failure_reason = str(e)
                logger.error("Model loading failed: %s", self._failure_reason)
                return
            self._model = model
            self._metadata = metadata
            self._loaded = True
            self._load_duration_seconds = time.monotonic() - start
            logger.info(
                "Model loaded successfully: architecture=%s classes=%d device=%s duration=%.3fs",
                metadata.architecture, metadata.class_count, metadata.device, self._load_duration_seconds,
            )

    def get_model(self) -> torch.nn.Module:
        if not self.is_ready:
            raise ModelLoadError("model is not loaded")
        return self._model

    def release(self) -> None:
        """Drops the model reference. Called at shutdown only -- never
        during request handling."""
        with self._lock:
            self._model = None
