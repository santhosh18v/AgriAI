"""Tests for training/model.py."""

import pytest
import torch

from model import ModelConfigError, build_model, select_device


def test_build_model_output_shape_matches_num_classes():
    model = build_model(num_classes=6, pretrained=False)
    model.eval()
    dummy = torch.randn(2, 3, 224, 224)
    with torch.no_grad():
        out = model(dummy)
    assert out.shape == (2, 6)


def test_build_model_rejects_wrong_class_count():
    for bad_count in (5, 7, 8, 0):
        with pytest.raises(ModelConfigError):
            build_model(num_classes=bad_count, pretrained=False)


def test_select_device_cpu_always_available():
    device = select_device("cpu")
    assert device.type == "cpu"


def test_select_device_auto_returns_valid_device():
    device = select_device("auto")
    assert device.type in ("mps", "cuda", "cpu")


def test_select_device_rejects_unavailable_cuda_on_this_machine():
    if torch.cuda.is_available():
        pytest.skip("CUDA is available on this machine; nothing to assert")
    with pytest.raises(ModelConfigError):
        select_device("cuda")
