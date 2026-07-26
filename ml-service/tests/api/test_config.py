"""Tests for app/config.py's validated settings (Milestone M6)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError


def test_defaults_parse():
    from app.config import Settings

    s = Settings()
    assert s.app_name == "AgriAI ML Service"
    assert s.environment == "development"
    assert s.host == "127.0.0.1"
    assert s.port == 8001
    assert s.preferred_device == "auto"
    assert s.eager_model_load is True
    assert s.cors_origins == ["http://localhost:3000", "http://127.0.0.1:3000"]


def test_environment_variable_overrides_parse(monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("AGRI_ML_APP_NAME", "Custom Name")
    monkeypatch.setenv("AGRI_ML_PORT", "9000")
    monkeypatch.setenv("AGRI_ML_PREFERRED_DEVICE", "cpu")
    monkeypatch.setenv("AGRI_ML_EAGER_MODEL_LOAD", "false")

    s = Settings()
    assert s.app_name == "Custom Name"
    assert s.port == 9000
    assert s.preferred_device == "cpu"
    assert s.eager_model_load is False


def test_invalid_device_setting_is_rejected():
    from app.config import Settings

    with pytest.raises(ValidationError, match="preferred_device"):
        Settings(preferred_device="quantum")


def test_invalid_environment_setting_is_rejected():
    from app.config import Settings

    with pytest.raises(ValidationError, match="environment"):
        Settings(environment="staging-typo")


def test_invalid_port_is_rejected():
    from app.config import Settings

    with pytest.raises(ValidationError):
        Settings(port=70000)


def test_cors_origins_parse_from_comma_separated_env(monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("AGRI_ML_CORS_ORIGINS", "http://a.example,http://b.example")
    s = Settings()
    assert s.cors_origins == ["http://a.example", "http://b.example"]


def test_cors_origins_parse_from_json_array_env(monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("AGRI_ML_CORS_ORIGINS", '["http://c.example"]')
    s = Settings()
    assert s.cors_origins == ["http://c.example"]


def test_unresolved_paths_default_to_none_and_resolve_lazily():
    from app.config import ML_SERVICE_ROOT, Settings

    s = Settings()
    assert s.model_checkpoint_path is None
    assert s.resolved_model_checkpoint_path() == (
        ML_SERVICE_ROOT / "data" / "training-runs" / "m4-efficientnet-b0-seed42" / "best_model.pt"
    )
    assert s.resolved_confidence_policy_path() == ML_SERVICE_ROOT / "training" / "confidence_policy_v1.json"


def test_explicit_path_override_is_used_verbatim(tmp_path):
    from app.config import Settings

    custom = tmp_path / "custom_checkpoint.pt"
    s = Settings(model_checkpoint_path=custom)
    assert s.resolved_model_checkpoint_path() == custom


def test_get_settings_is_cached():
    from app.config import get_settings

    get_settings.cache_clear()
    a = get_settings()
    b = get_settings()
    assert a is b
    get_settings.cache_clear()
