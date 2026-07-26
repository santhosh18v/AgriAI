"""Tests for app/preprocessing.py (Milestone M7)."""

from __future__ import annotations

import pytest
from PIL import Image

from app.preprocessing import PreprocessingError, preprocess_image, preprocessing_config


def test_output_shape_is_1x3x224x224():
    img = Image.new("RGB", (500, 400), (10, 20, 30))
    tensor = preprocess_image(img)
    assert tuple(tensor.shape) == (1, 3, 224, 224)


def test_output_shape_is_stable_across_varied_input_sizes():
    for size in [(100, 100), (4032, 3024), (150, 900), (900, 150)]:
        img = Image.new("RGB", size, (50, 60, 70))
        tensor = preprocess_image(img)
        assert tuple(tensor.shape) == (1, 3, 224, 224)


def test_preprocessing_is_deterministic():
    img = Image.new("RGB", (300, 300), (200, 100, 50))
    t1 = preprocess_image(img)
    t2 = preprocess_image(img)
    assert bool((t1 == t2).all())


def test_preprocessing_config_matches_expected_constants():
    config = preprocessing_config()
    assert config["image_size"] == 224
    assert config["normalization"]["mean"] == [0.485, 0.456, 0.406]
    assert config["normalization"]["std"] == [0.229, 0.224, 0.225]


def test_non_rgb_image_is_rejected():
    img = Image.new("L", (100, 100))
    with pytest.raises(PreprocessingError):
        preprocess_image(img)
