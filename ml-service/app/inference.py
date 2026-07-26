"""Model inference for the disease-prediction endpoint (Milestone M7).

Runs the already-loaded, already-validated EfficientNet-B0 model under
torch.inference_mode() against a single preprocessed image. Never trains,
never mutates model weights, and never accepts a caller-supplied confidence
threshold -- the threshold always comes from the model's validated, loaded
metadata (training/confidence_policy_v1.json, verified once at startup by
model_loader.py's `_validate_and_build`).

Concurrency: no lock is taken around inference. The model is in eval()
mode (no Dropout, no BatchNorm running-stats updates), so a forward pass
over a frozen nn.Module has no shared mutable state that concurrent
requests could race on -- this matches PyTorch's own documented guidance
that concurrent read-only forward passes on an eval()-mode module are
safe. FastAPI runs this module's synchronous route handler in a worker
thread pool, so concurrency is bounded by that pool, not serialized here
without reason.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List

import torch
from PIL import Image

from .model_loader import ModelLoader
from .preprocessing import preprocess_image


@dataclass(frozen=True)
class ClassScore:
    class_name: str
    class_index: int
    confidence: float


@dataclass(frozen=True)
class InferenceResult:
    top_prediction: ClassScore
    top_predictions: List[ClassScore]
    accepted: bool
    uncertain: bool
    preprocessing_ms: float
    inference_ms: float
    total_ms: float


def run_inference(loader: ModelLoader, image: Image.Image, top_k: int) -> InferenceResult:
    """`loader.is_ready` must already be True -- callers (routes/predict.py)
    check readiness before calling this, so a not-ready model surfaces as a
    503 there rather than an exception here."""
    metadata = loader.metadata
    model = loader.get_model()

    total_start = time.perf_counter()

    pre_start = time.perf_counter()
    input_tensor = preprocess_image(image)
    preprocessing_ms = (time.perf_counter() - pre_start) * 1000

    device = torch.device(metadata.device)
    input_tensor = input_tensor.to(device)

    infer_start = time.perf_counter()
    with torch.inference_mode():
        logits = model(input_tensor)
        probabilities = torch.softmax(logits, dim=1)[0]
    if device.type == "mps":
        # MPS ops are asynchronous by default; synchronize only so the
        # measured duration reflects actual completion, not kernel launch.
        torch.mps.synchronize()
    inference_ms = (time.perf_counter() - infer_start) * 1000

    probs = probabilities.detach().cpu().tolist()
    class_names = metadata.classes

    scored = [
        ClassScore(class_name=class_names[i], class_index=i, confidence=float(probs[i]))
        for i in range(len(class_names))
    ]
    scored_sorted = sorted(scored, key=lambda s: -s.confidence)

    k = max(1, min(top_k, len(class_names)))
    top_predictions = scored_sorted[:k]
    top_prediction = scored_sorted[0]

    threshold = metadata.confidence_threshold
    accepted = top_prediction.confidence >= threshold
    uncertain = not accepted

    total_ms = (time.perf_counter() - total_start) * 1000

    return InferenceResult(
        top_prediction=top_prediction,
        top_predictions=top_predictions,
        accepted=accepted,
        uncertain=uncertain,
        preprocessing_ms=preprocessing_ms,
        inference_ms=inference_ms,
        total_ms=total_ms,
    )
