"""Typed, validated application configuration (Milestone M6).

Uses pydantic-settings so invalid configuration fails fast and clearly at
startup, rather than surfacing as a confusing failure deep inside model
loading or a request handler. All environment variables use the AGRI_ML_
prefix (see .env.example). No secrets are read or required here -- this
service has no authentication in M6.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent

ALLOWED_ENVIRONMENTS = {"development", "test", "production"}
ALLOWED_DEVICES = {"auto", "cpu", "mps", "cuda"}

# Frozen M5 results. Not read from confidence_policy_v1.json because that
# file is deliberately validation-only (see docs/MODEL_EVALUATION.md /
# M5's design) and never contains test-derived values. These two numbers
# are cited, immutable facts from the one-time frozen test evaluation,
# recorded in docs/MODEL_EVALUATION.md -- test.csv must not be re-evaluated
# to "re-derive" them.
FROZEN_TEST_ACCURACY = 0.9889
FROZEN_TEST_MACRO_F1 = 0.9841
DATASET_CONTEXT = "PlantVillage-derived controlled-image evaluation"

# Curated, cited safety disclosures for GET /api/model-info. Sourced from
# training/confidence_policy_v1.json's own limitations (softmax is not
# certainty; not production-calibrated) plus the frozen M5 test result
# documented in docs/MODEL_EVALUATION.md (the threshold rejected zero test
# samples). Not mechanically merged from those files at runtime -- this is
# a small, stable, human-reviewed summary, not free-form scattered text.
DEFAULT_MODEL_LIMITATIONS = [
    "The confidence score is not certainty or probability of truth.",
    "The threshold rejected no samples in the frozen test evaluation.",
    "Real-world farm-photo validation is still required.",
    "The model currently supports six Tomato and Potato classes only.",
]

DEFAULT_CORS_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGRI_ML_",
        env_file=str(ML_SERVICE_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Identity ----------------------------------------------------
    app_name: str = "AgriAI ML Service"
    app_version: str = "Phase 2 development version"
    environment: str = "development"

    # --- Server --------------------------------------------------------
    host: str = "127.0.0.1"
    port: int = Field(default=8001, ge=1, le=65535)
    log_level: str = "info"

    # --- Approved model artifacts (paths only; never returned in API
    # responses -- see app/schemas.py) ---------------------------------
    model_checkpoint_path: Optional[Path] = None
    confidence_policy_path: Optional[Path] = None
    class_map_path: Optional[Path] = None
    model_scope_path: Optional[Path] = None

    # --- Model loading ---------------------------------------------------
    preferred_device: str = "auto"
    eager_model_load: bool = True

    # --- HTTP ------------------------------------------------------------
    # NoDecode: skip pydantic-settings' default JSON decoding of list-typed
    # env vars so a plain comma-separated string (see the validator below)
    # works without requiring JSON array quoting in a .env file.
    cors_origins: Annotated[List[str], NoDecode] = Field(default_factory=lambda: list(DEFAULT_CORS_ORIGINS))
    request_id_header: str = "X-Request-ID"

    # --- Frozen M5 evaluation context (see module docstring above) -------
    frozen_test_accuracy: float = FROZEN_TEST_ACCURACY
    frozen_test_macro_f1: float = FROZEN_TEST_MACRO_F1
    dataset_context: str = DATASET_CONTEXT
    model_limitations: List[str] = Field(default_factory=lambda: list(DEFAULT_MODEL_LIMITATIONS))

    @field_validator("environment")
    @classmethod
    def _validate_environment(cls, v: str) -> str:
        if v not in ALLOWED_ENVIRONMENTS:
            raise ValueError(f"environment must be one of {sorted(ALLOWED_ENVIRONMENTS)}, got {v!r}")
        return v

    @field_validator("preferred_device")
    @classmethod
    def _validate_device(cls, v: str) -> str:
        if v not in ALLOWED_DEVICES:
            raise ValueError(f"preferred_device must be one of {sorted(ALLOWED_DEVICES)}, got {v!r}")
        return v

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v):
        """Accepts either a JSON array (pydantic-settings default for list
        fields) or a simple comma-separated string, so a plain .env line
        like `AGRI_ML_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000`
        works without requiring JSON quoting."""
        if isinstance(v, str):
            stripped = v.strip()
            if stripped.startswith("["):
                import json

                return json.loads(stripped)
            return [origin.strip() for origin in stripped.split(",") if origin.strip()]
        return v

    def resolved_model_checkpoint_path(self) -> Path:
        return self.model_checkpoint_path or (
            ML_SERVICE_ROOT / "data" / "training-runs" / "m4-efficientnet-b0-seed42" / "best_model.pt"
        )

    def resolved_confidence_policy_path(self) -> Path:
        return self.confidence_policy_path or (ML_SERVICE_ROOT / "training" / "confidence_policy_v1.json")

    def resolved_class_map_path(self) -> Path:
        return self.class_map_path or (ML_SERVICE_ROOT / "training" / "class_map.json")

    def resolved_model_scope_path(self) -> Path:
        return self.model_scope_path or (ML_SERVICE_ROOT / "training" / "model_scope_v1.json")


@lru_cache
def get_settings() -> Settings:
    """Process-wide cached settings instance. Use get_settings.cache_clear()
    in tests that need a fresh instance (e.g. after changing environment
    variables)."""
    return Settings()
