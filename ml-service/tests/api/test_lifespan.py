"""Tests for application startup/shutdown lifecycle (Milestone M6)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_startup_success_with_eager_load(make_settings):
    settings = make_settings(eager_model_load=True)
    app = create_app(settings)
    with TestClient(app) as client:
        assert app.state.model_loader.is_ready is True
        r = client.get("/api/ready")
        assert r.status_code == 200


def test_startup_model_load_failure_leaves_health_alive_but_readiness_false(make_settings, synthetic_env):
    settings = make_settings(model_checkpoint_path=synthetic_env["root"] / "missing.pt", eager_model_load=True)
    app = create_app(settings)
    with TestClient(app) as client:
        assert app.state.model_loader.is_ready is False

        health_response = client.get("/api/health")
        assert health_response.status_code == 200

        ready_response = client.get("/api/ready")
        assert ready_response.status_code == 503


def test_lazy_loading_does_not_load_model_at_startup(make_settings):
    settings = make_settings(eager_model_load=False)
    app = create_app(settings)
    with TestClient(app):
        assert app.state.model_loader.is_ready is False


def test_shutdown_does_not_raise(make_settings):
    settings = make_settings(eager_model_load=True)
    app = create_app(settings)
    with TestClient(app) as client:
        client.get("/api/health")
    # Exiting the `with` block runs the lifespan shutdown path; reaching
    # here without an exception is the assertion.
    assert app.state.model_loader.is_ready is False  # released on shutdown


def test_shutdown_does_not_raise_when_model_never_loaded(make_settings, synthetic_env):
    settings = make_settings(model_checkpoint_path=synthetic_env["root"] / "missing.pt", eager_model_load=True)
    app = create_app(settings)
    with TestClient(app):
        pass  # startup fails to load; shutdown must still complete cleanly


def test_unhandled_exception_returns_sanitized_500(make_settings, synthetic_env):
    """An unexpected exception inside a route handler must never reach the
    client as a traceback or leak local paths -- app.main's global handler
    must catch it and return a generic, sanitized 500."""
    from app.dependencies import get_model_loader

    settings = make_settings(eager_model_load=True)
    app = create_app(settings)

    class ExplodingLoader:
        @property
        def is_ready(self):
            raise RuntimeError(f"boom: simulated failure referencing {synthetic_env['root']}")

    app.dependency_overrides[get_model_loader] = lambda: ExplodingLoader()

    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.get("/api/ready")

    assert r.status_code == 500
    assert r.json() == {"status": "error", "detail": "internal server error"}
    body_text = r.text
    assert "RuntimeError" not in body_text
    assert "Traceback" not in body_text
    assert str(synthetic_env["root"]) not in body_text
    assert "/Users/" not in body_text
