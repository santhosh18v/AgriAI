"""Tests for GET /api/health and GET /api/ready (Milestone M6)."""

from __future__ import annotations

from conftest import write_policy


def test_health_returns_200_with_correct_schema(app_client, make_settings):
    settings = make_settings()
    client = app_client(settings)
    with client:
        r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == settings.app_name
    assert body["version"] == settings.app_version
    assert body["environment"] == settings.environment


def test_health_does_not_require_model_to_be_loaded(app_client, make_settings, synthetic_env):
    # Point at a nonexistent checkpoint so eager load fails, but health
    # must still succeed -- it has no dependency on the model at all.
    settings = make_settings(model_checkpoint_path=synthetic_env["root"] / "missing.pt", eager_model_load=True)
    client = app_client(settings)
    with client:
        r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_health_exposes_no_sensitive_paths(app_client, make_settings, synthetic_env):
    settings = make_settings()
    client = app_client(settings)
    with client:
        r = client.get("/api/health")
    body_text = r.text
    assert str(synthetic_env["root"]) not in body_text
    assert "/Users/" not in body_text


def test_ready_returns_200_when_model_loaded(app_client, make_settings):
    settings = make_settings(eager_model_load=True)
    client = app_client(settings)
    with client:
        r = client.get("/api/ready")
    assert r.status_code == 200
    body = r.json()
    assert body == {
        "status": "ready",
        "model_loaded": True,
        "confidence_policy_loaded": True,
        "class_count": 6,
    }


def test_ready_returns_503_when_model_missing(app_client, make_settings, synthetic_env):
    settings = make_settings(model_checkpoint_path=synthetic_env["root"] / "missing.pt", eager_model_load=True)
    client = app_client(settings)
    with client:
        r = client.get("/api/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "not_ready"
    assert body["model_loaded"] is False
    assert "reason" in body


def test_ready_503_response_is_sanitized(app_client, make_settings, synthetic_env):
    bad_policy_path = write_policy(synthetic_env["root"], "wrong-hash", filename="p.json")
    settings = make_settings(confidence_policy_path=bad_policy_path, eager_model_load=True)
    client = app_client(settings)
    with client:
        r = client.get("/api/ready")
    assert r.status_code == 503
    body_text = r.text
    assert str(synthetic_env["root"]) not in body_text
    assert "/Users/" not in body_text
    assert "Traceback" not in body_text


def test_ready_never_reports_ready_from_file_existence_alone(app_client, make_settings, synthetic_env):
    # The checkpoint file exists, the policy file exists -- but the policy
    # is not approved, so readiness must still be false.
    bad_policy_path = write_policy(
        synthetic_env["root"], synthetic_env["checkpoint_sha256"],
        filename="unapproved.json", status="blocked_threshold_selection",
    )
    settings = make_settings(confidence_policy_path=bad_policy_path, eager_model_load=True)
    client = app_client(settings)
    with client:
        r = client.get("/api/ready")
    assert r.status_code == 503
    assert r.json()["model_loaded"] is False


def test_ready_with_lazy_loading_reports_not_ready_until_loaded(app_client, make_settings):
    settings = make_settings(eager_model_load=False)
    client = app_client(settings)
    with client:
        r = client.get("/api/ready")
    assert r.status_code == 503
    assert r.json()["model_loaded"] is False
