"""Inference-time image preprocessing (Milestone M7).

Reconstructs the exact M4 validation transform -- Resize(256) ->
CenterCrop(224) -> ToTensor() -> ImageNet normalization -- applied to a
single already-decoded, EXIF-corrected, RGB image. Never applies training-
time augmentation (random crop/flip/rotation/color-jitter).

Deliberately reconstructed here rather than importing
training/train.py's build_transforms(): train.py pulls in scikit-learn at
module level, which is a training-only dependency (requirements-training.txt)
not present in the deployed runtime's requirements.txt. The constants below
are the exact values training/train.py defines (IMAGE_SIZE, IMAGENET_MEAN,
IMAGENET_STD) and training/model_loader.py cross-validates every loaded
checkpoint's own recorded `preprocessing_config` against them at startup
(see model_loader.py's `_validate_preprocessing_config`) -- if a future
checkpoint ever used different preprocessing, model loading fails safely
rather than silently running inference through the wrong pipeline.
"""

from __future__ import annotations

from functools import lru_cache

import torch
from PIL import Image
from torchvision import transforms as T

# Must match training/train.py's IMAGE_SIZE / IMAGENET_MEAN / IMAGENET_STD
# and the val_transform branch of its build_transforms() exactly.
IMAGE_SIZE = 224
RESIZE_SIZE = 256
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


class PreprocessingError(Exception):
    """Raised when an already-validated, decoded image cannot be
    preprocessed. Messages must stay sanitized (no paths, no internals)."""


@lru_cache(maxsize=1)
def _get_inference_transform() -> T.Compose:
    return T.Compose(
        [
            T.Resize(RESIZE_SIZE),
            T.CenterCrop(IMAGE_SIZE),
            T.ToTensor(),
            T.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
        ]
    )


def preprocessing_config() -> dict:
    """The config dict shape this module implements, for cross-validation
    against a checkpoint's recorded `preprocessing_config` (see
    train.py's build_transforms(), which records the identical shape)."""
    return {
        "image_size": IMAGE_SIZE,
        "normalization": {"mean": IMAGENET_MEAN, "std": IMAGENET_STD},
    }


def preprocess_image(image: Image.Image) -> torch.Tensor:
    """Applies the M4 validation transform to `image` (already decoded,
    EXIF-corrected, RGB -- see app/image_validation.py) and returns a
    batched tensor of shape (1, 3, 224, 224) on the CPU."""
    if image.mode != "RGB":
        raise PreprocessingError("image must be converted to RGB before preprocessing")

    transform = _get_inference_transform()
    try:
        tensor = transform(image)
    except Exception as e:
        raise PreprocessingError("image preprocessing failed") from e

    return tensor.unsqueeze(0)
