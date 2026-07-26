"""Tests for app/inference.py (Milestone M7).

Uses a fake, duck-typed ModelLoader with a fixed-logits fake nn.Module so
predicted confidences are exactly controllable -- never the real random-
weight synthetic checkpoint (used only for endpoint-level tests) and never
the real trained checkpoint.
"""

from __future__ import annotations

import inspect

import torch
from PIL import Image

from app.inference import run_inference
from app.model_loader import ModelMetadata

CLASS_NAMES = ("A", "B", "C", "D", "E", "F")


class _FixedLogitsModel(torch.nn.Module):
    def __init__(self, logits: torch.Tensor):
        super().__init__()
        self.register_buffer("_logits", logits)
        self.forward_call_count = 0
        self.training_mode_seen = []

    def forward(self, x):
        self.forward_call_count += 1
        self.training_mode_seen.append(self.training)
        batch = x.shape[0]
        return self._logits.unsqueeze(0).expand(batch, -1).clone()


class _FakeLoader:
    def __init__(self, model, metadata):
        self._model = model
        self._metadata = metadata

    @property
    def is_ready(self) -> bool:
        return True

    @property
    def metadata(self):
        return self._metadata

    def get_model(self):
        return self._model


def _make_metadata(threshold=0.5, classes=CLASS_NAMES, device="cpu"):
    return ModelMetadata(
        architecture="efficientnet_b0",
        model_version="test-version",
        class_count=len(classes),
        classes=tuple(classes),
        input_width=224,
        input_height=224,
        input_channels=3,
        confidence_method="maximum_softmax_probability",
        confidence_threshold=threshold,
        confidence_production_calibrated=False,
        frozen_test_accuracy=0.9889,
        frozen_test_macro_f1=0.9841,
        dataset_context="test",
        limitations=("limitation one",),
        device=device,
    )


def _tiny_rgb_image():
    return Image.new("RGB", (50, 50), (120, 60, 30))


def test_preprocessed_tensor_has_expected_shape(monkeypatch):
    import app.inference as inference_module

    captured = {}
    original = inference_module.preprocess_image

    def _spy(image):
        tensor = original(image)
        captured["shape"] = tuple(tensor.shape)
        return tensor

    monkeypatch.setattr(inference_module, "preprocess_image", _spy)

    model = _FixedLogitsModel(torch.zeros(6))
    loader = _FakeLoader(model, _make_metadata())
    run_inference(loader, _tiny_rgb_image(), top_k=3)
    assert captured["shape"] == (1, 3, 224, 224)


def test_model_forward_never_runs_in_training_mode():
    model = _FixedLogitsModel(torch.tensor([5.0, 1.0, 0.0, 0.0, 0.0, 0.0]))
    model.eval()
    loader = _FakeLoader(model, _make_metadata())
    run_inference(loader, _tiny_rgb_image(), top_k=3)
    assert model.training_mode_seen == [False]


def test_model_instance_is_reused_across_calls_not_reconstructed():
    model = _FixedLogitsModel(torch.tensor([5.0, 1.0, 0.0, 0.0, 0.0, 0.0]))
    loader = _FakeLoader(model, _make_metadata())
    run_inference(loader, _tiny_rgb_image(), top_k=3)
    run_inference(loader, _tiny_rgb_image(), top_k=3)
    assert loader.get_model() is model
    assert model.forward_call_count == 2


def test_class_order_preserved_from_metadata():
    logits = torch.tensor([0.0, 0.0, 0.0, 10.0, 0.0, 0.0])  # index 3 = "D"
    model = _FixedLogitsModel(logits)
    loader = _FakeLoader(model, _make_metadata())
    result = run_inference(loader, _tiny_rgb_image(), top_k=3)
    assert result.top_prediction.class_name == "D"
    assert result.top_prediction.class_index == 3


def test_top_predictions_sorted_descending_with_correct_count():
    logits = torch.tensor([1.0, 5.0, 3.0, 0.0, 2.0, 4.0])
    model = _FixedLogitsModel(logits)
    loader = _FakeLoader(model, _make_metadata())
    result = run_inference(loader, _tiny_rgb_image(), top_k=3)
    assert len(result.top_predictions) == 3
    confidences = [c.confidence for c in result.top_predictions]
    assert confidences == sorted(confidences, reverse=True)
    assert result.top_predictions[0].class_name == "B"


def test_top_k_never_exceeds_class_count():
    model = _FixedLogitsModel(torch.zeros(6))
    loader = _FakeLoader(model, _make_metadata())
    result = run_inference(loader, _tiny_rgb_image(), top_k=100)
    assert len(result.top_predictions) == 6


def test_probabilities_sum_to_approximately_one():
    logits = torch.tensor([1.0, 5.0, 3.0, 0.0, 2.0, 4.0])
    model = _FixedLogitsModel(logits)
    loader = _FakeLoader(model, _make_metadata())
    result = run_inference(loader, _tiny_rgb_image(), top_k=6)
    assert abs(sum(c.confidence for c in result.top_predictions) - 1.0) < 1e-5


def test_accepted_when_confidence_equals_threshold_exactly():
    # softmax([0, 0, -100, -100, -100, -100]) -> top two classes split
    # probability exactly 0.5/0.5 (the other four are numerically negligible).
    logits = torch.tensor([0.0, 0.0, -100.0, -100.0, -100.0, -100.0])
    model = _FixedLogitsModel(logits)
    loader = _FakeLoader(model, _make_metadata(threshold=0.5))
    result = run_inference(loader, _tiny_rgb_image(), top_k=3)
    assert abs(result.top_prediction.confidence - 0.5) < 1e-6
    assert result.accepted is True
    assert result.uncertain is False


def test_uncertain_when_confidence_below_threshold():
    logits = torch.tensor([0.1, 0.05, 0.05, 0.05, 0.05, 0.05])
    model = _FixedLogitsModel(logits)
    loader = _FakeLoader(model, _make_metadata(threshold=0.9))
    result = run_inference(loader, _tiny_rgb_image(), top_k=3)
    assert result.top_prediction.confidence < 0.9
    assert result.accepted is False
    assert result.uncertain is True


def test_accepted_and_uncertain_are_always_opposite():
    for threshold in (0.1, 0.5, 0.9, 0.999):
        logits = torch.tensor([3.0, 1.0, 0.5, 0.2, 0.1, 0.0])
        model = _FixedLogitsModel(logits)
        loader = _FakeLoader(model, _make_metadata(threshold=threshold))
        result = run_inference(loader, _tiny_rgb_image(), top_k=3)
        assert result.accepted != result.uncertain


def test_threshold_cannot_be_passed_as_a_request_parameter():
    sig = inspect.signature(run_inference)
    assert "threshold" not in sig.parameters
    assert set(sig.parameters) == {"loader", "image", "top_k"}


def test_confidences_are_plain_floats_never_raw_logits():
    logits = torch.tensor([50.0, -50.0, 0.0, 0.0, 0.0, 0.0])  # extreme logits
    model = _FixedLogitsModel(logits)
    loader = _FakeLoader(model, _make_metadata())
    result = run_inference(loader, _tiny_rgb_image(), top_k=6)
    for c in result.top_predictions:
        assert isinstance(c.confidence, float)
        assert 0.0 <= c.confidence <= 1.0  # a raw logit (e.g. 50.0) would fail this


def test_no_gradients_are_tracked():
    logits = torch.tensor([1.0, 0.0, 0.0, 0.0, 0.0, 0.0], requires_grad=True)
    model = _FixedLogitsModel(logits.detach().clone())
    loader = _FakeLoader(model, _make_metadata())
    result = run_inference(loader, _tiny_rgb_image(), top_k=3)
    assert all(isinstance(c.confidence, float) for c in result.top_predictions)
