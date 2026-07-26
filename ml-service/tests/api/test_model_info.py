"""Tests for GET /api/model-info (Milestone M6)."""

from __future__ import annotations

from conftest import CLASS_NAMES


def test_model_info_success_shape(app_client, make_settings):
    settings = make_settings(eager_model_load=True)
    client = app_client(settings)
    with client:
        r = client.get("/api/model-info")
    assert r.status_code == 200
    body = r.json()

    assert body["status"] == "available"
    assert body["architecture"] == "efficientnet_b0"
    assert body["class_count"] == 6
    assert body["classes"] == CLASS_NAMES  # exact order matches the approved scope
    assert body["confidence"]["threshold"] == 0.5
    assert body["confidence"]["label"] == "model confidence"
    assert body["confidence"]["production_calibrated"] is False
    assert body["input"] == {"width": 224, "height": 224, "channels": 3}


def test_model_info_does_not_expose_checkpoint_path(app_client, make_settings, synthetic_env):
    settings = make_settings(eager_model_load=True)
    client = app_client(settings)
    with client:
        r = client.get("/api/model-info")
    body_text = r.text
    assert str(synthetic_env["checkpoint_path"]) not in body_text
    assert ".pt" not in body_text
    assert str(synthetic_env["root"]) not in body_text


def test_model_info_never_claims_certainty_or_production_readiness(app_client, make_settings):
    settings = make_settings(eager_model_load=True)
    client = app_client(settings)
    with client:
        r = client.get("/api/model-info")
    body = r.json()

    # The confidence label itself must be exactly "model confidence" -- never
    # "certainty" or "probability of truth".
    assert body["confidence"]["label"] == "model confidence"
    assert body["confidence"]["production_calibrated"] is False

    # The word "certainty" is allowed to appear only inside the disclaimer
    # that explicitly *denies* it (e.g. "is not certainty..."); it must
    # never appear as an affirmative claim.
    for limitation in body["limitations"]:
        lower = limitation.lower()
        if "certainty" in lower or "probability of truth" in lower:
            assert "not" in lower, f"limitation asserts certainty without negation: {limitation!r}"

    body_text = r.text.lower()
    assert "production ready" not in body_text
    assert "production-ready" not in body_text
    assert '"is certainty"' not in body_text


def test_model_info_unavailable_returns_503(app_client, make_settings, synthetic_env):
    settings = make_settings(model_checkpoint_path=synthetic_env["root"] / "missing.pt", eager_model_load=True)
    client = app_client(settings)
    with client:
        r = client.get("/api/model-info")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "unavailable"
    assert "reason" in body


def test_model_info_unavailable_response_is_sanitized(app_client, make_settings, synthetic_env):
    settings = make_settings(model_checkpoint_path=synthetic_env["root"] / "missing.pt", eager_model_load=True)
    client = app_client(settings)
    with client:
        r = client.get("/api/model-info")
    body_text = r.text
    assert str(synthetic_env["root"]) not in body_text
    assert "Traceback" not in body_text
