"""Endpoint tests for POST /api/predict/disease (Milestone M7).

Uses the synthetic random-weight EfficientNet-B0 checkpoint (see
conftest.py) -- exercises the full HTTP/validation/inference stack, not
prediction correctness (which real-model manual verification covers).
"""

from __future__ import annotations

import io

from conftest import CLASS_NAMES, write_policy
from PIL import Image


def _jpeg_bytes(size=(120, 120), color=(80, 140, 60)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return buf.getvalue()


def test_valid_image_returns_200_with_valid_schema(app_client, make_settings):
    settings = make_settings(eager_model_load=True)
    client = app_client(settings)
    with client:
        r = client.post("/api/predict/disease", files={"file": ("leaf.jpg", _jpeg_bytes(), "image/jpeg")})

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["prediction"]["class_name"] in CLASS_NAMES
    assert 0.0 <= body["prediction"]["model_confidence"] <= 1.0
    assert body["prediction"]["accepted"] != body["prediction"]["uncertain"]
    assert len(body["top_predictions"]) == 3
    confidences = [p["model_confidence"] for p in body["top_predictions"]]
    assert confidences == sorted(confidences, reverse=True)
    assert body["confidence_policy"] == {
        "method": "maximum_softmax_probability",
        "threshold": 0.5,
        "label": "model confidence",
        "production_calibrated": False,
    }
    assert body["input"]["filename"] == "leaf.jpg"
    assert body["input"]["content_type"] == "image/jpeg"
    assert body["input"]["width"] == 120
    assert body["input"]["height"] == 120
    assert set(body["timing_ms"]) == {"preprocessing", "inference", "total"}
    assert isinstance(body["limitations"], list) and len(body["limitations"]) > 0


def test_model_unavailable_returns_503(app_client, make_settings, synthetic_env):
    settings = make_settings(model_checkpoint_path=synthetic_env["root"] / "missing.pt", eager_model_load=True)
    client = app_client(settings)
    with client:
        r = client.post("/api/predict/disease", files={"file": ("leaf.jpg", _jpeg_bytes(), "image/jpeg")})
    assert r.status_code == 503
    assert r.json()["status"] == "error"


def test_oversized_file_returns_413(app_client, make_settings):
    settings = make_settings(eager_model_load=True, max_upload_bytes=1000)
    client = app_client(settings)
    big = _jpeg_bytes(size=(300, 300))
    assert len(big) > 1000
    with client:
        r = client.post("/api/predict/disease", files={"file": ("leaf.jpg", big, "image/jpeg")})
    assert r.status_code == 413
    assert r.json()["status"] == "error"


def test_unsupported_media_type_returns_415(app_client, make_settings):
    settings = make_settings(eager_model_load=True)
    client = app_client(settings)
    with client:
        r = client.post("/api/predict/disease", files={"file": ("notes.txt", b"not an image", "text/plain")})
    assert r.status_code == 415
    assert r.json()["status"] == "error"


def test_malformed_image_returns_400(app_client, make_settings):
    settings = make_settings(eager_model_load=True)
    client = app_client(settings)
    with client:
        r = client.post(
            "/api/predict/disease",
            files={"file": ("leaf.jpg", b"not a real jpeg, just some bytes " * 5, "image/jpeg")},
        )
    assert r.status_code == 400
    assert r.json()["status"] == "error"


def test_error_responses_never_leak_paths_or_tracebacks(app_client, make_settings, synthetic_env):
    settings = make_settings(model_checkpoint_path=synthetic_env["root"] / "missing.pt", eager_model_load=True)
    client = app_client(settings)
    with client:
        r = client.post("/api/predict/disease", files={"file": ("leaf.jpg", _jpeg_bytes(), "image/jpeg")})
    body_text = r.text
    assert str(synthetic_env["root"]) not in body_text
    assert "/Users/" not in body_text
    assert "Traceback" not in body_text


def test_uncertain_prediction_returns_200_with_correct_flags(app_client, make_settings, synthetic_env):
    # An unreachably high threshold forces "uncertain" deterministically,
    # regardless of the random synthetic model's actual output.
    high_threshold_policy = write_policy(
        synthetic_env["root"], synthetic_env["checkpoint_sha256"],
        filename="high_threshold_policy.json", selected_threshold=0.999999,
    )
    settings = make_settings(confidence_policy_path=high_threshold_policy, eager_model_load=True)
    client = app_client(settings)
    with client:
        r = client.post("/api/predict/disease", files={"file": ("leaf.jpg", _jpeg_bytes(), "image/jpeg")})

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["prediction"]["accepted"] is False
    assert body["prediction"]["uncertain"] is True
    assert body["prediction"]["message"] == "The model confidence is below the configured threshold."


def test_missing_file_field_returns_422(app_client, make_settings):
    settings = make_settings(eager_model_load=True)
    client = app_client(settings)
    with client:
        r = client.post("/api/predict/disease", data={})
    assert r.status_code == 422


def test_no_predict_alias_route_exists(app_client, make_settings):
    settings = make_settings(eager_model_load=True)
    client = app_client(settings)
    with client:
        r = client.post("/api/predict", files={"file": ("leaf.jpg", _jpeg_bytes(), "image/jpeg")})
    assert r.status_code == 404


def test_health_ready_model_info_still_work_alongside_predict(app_client, make_settings):
    settings = make_settings(eager_model_load=True)
    client = app_client(settings)
    with client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/ready").status_code == 200
        assert client.get("/api/model-info").status_code == 200
