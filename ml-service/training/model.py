"""EfficientNet-B0 classifier factory and device selection (Milestone M4).

No FastAPI inference endpoint is created here -- this module only builds
the torch.nn.Module and picks a torch.device. Serving is a later milestone.
"""

from __future__ import annotations

import torch
from torch import nn
from torchvision.models import EfficientNet_B0_Weights, efficientnet_b0

ARCHITECTURE_NAME = "efficientnet_b0"
REQUIRED_NUM_CLASSES = 6  # frozen for M4 per the approved 6-class active scope


class ModelConfigError(Exception):
    pass


def pretrained_weights_id() -> str:
    """The exact torchvision weights identifier used, recorded in metadata."""
    return f"{EfficientNet_B0_Weights.IMAGENET1K_V1!s}"


def build_model(num_classes: int, pretrained: bool = True) -> nn.Module:
    if num_classes != REQUIRED_NUM_CLASSES:
        raise ModelConfigError(
            f"M4 requires exactly {REQUIRED_NUM_CLASSES} classes (the approved active "
            f"scope), got {num_classes}. Corn re-inclusion or any other scope change "
            f"is out of scope for this milestone."
        )

    weights = EfficientNet_B0_Weights.IMAGENET1K_V1 if pretrained else None
    model = efficientnet_b0(weights=weights)

    in_features = model.classifier[1].in_features
    model.classifier[1] = nn.Linear(in_features, num_classes)
    return model


def select_device(preferred: str = "auto") -> torch.device:
    """Resolve the requested device, auto-selecting MPS then CPU.

    CUDA is included for portability (per M4 instructions: "support MPS,
    CUDA if ever available, and CPU fallback") even though this dev machine
    has no CUDA device.
    """
    if preferred == "auto":
        if torch.backends.mps.is_available():
            return torch.device("mps")
        if torch.cuda.is_available():
            return torch.device("cuda")
        return torch.device("cpu")

    device = torch.device(preferred)
    if device.type == "mps" and not torch.backends.mps.is_available():
        raise ModelConfigError("MPS requested but not available on this machine")
    if device.type == "cuda" and not torch.cuda.is_available():
        raise ModelConfigError("CUDA requested but not available on this machine")
    return device
