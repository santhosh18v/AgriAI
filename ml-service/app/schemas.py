"""Typed Pydantic response models for the M6 API foundation.

Only health, readiness, model-information, and generic error response
shapes are defined here. There is no image upload or disease-prediction
endpoint yet -- those schemas belong to M7 and do not exist in this file.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    environment: str


class ReadyResponse(BaseModel):
    status: Literal["ready"]
    model_loaded: bool
    confidence_policy_loaded: bool
    class_count: int


class NotReadyResponse(BaseModel):
    status: Literal["not_ready"]
    model_loaded: bool
    reason: str


class InputSpec(BaseModel):
    width: int
    height: int
    channels: int


class ConfidenceInfo(BaseModel):
    method: str
    threshold: float = Field(ge=0.0, le=1.0)
    # Literal type deliberately pins the exact required wording -- this
    # field can never be assigned "certainty" or "probability of truth".
    label: Literal["model confidence"]
    production_calibrated: bool


class EvaluationInfo(BaseModel):
    frozen_test_accuracy: Optional[float] = None
    frozen_test_macro_f1: Optional[float] = None
    dataset_context: str


class ModelInfoResponse(BaseModel):
    status: Literal["available"]
    architecture: str
    model_version: str
    class_count: int
    classes: List[str]
    input: InputSpec
    confidence: ConfidenceInfo
    evaluation: EvaluationInfo
    limitations: List[str]


class ModelUnavailableResponse(BaseModel):
    status: Literal["unavailable"]
    reason: str


class ErrorResponse(BaseModel):
    status: Literal["error"]
    detail: str
