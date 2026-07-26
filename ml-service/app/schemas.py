"""Typed Pydantic response models for the API (Milestones M6 + M7).

Health, readiness, model-information, disease-prediction, and generic
error response shapes are defined here.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


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


# --- Disease prediction (Milestone M7) --------------------------------

class ClassPredictionOut(BaseModel):
    class_name: str
    class_index: int
    model_confidence: float = Field(ge=0.0, le=1.0)


class PredictionOut(BaseModel):
    class_name: str
    class_index: int
    model_confidence: float = Field(ge=0.0, le=1.0)
    accepted: bool
    uncertain: bool
    message: Optional[str] = None

    @model_validator(mode="after")
    def _accepted_and_uncertain_are_opposites(self) -> "PredictionOut":
        if self.accepted == self.uncertain:
            raise ValueError("accepted and uncertain must be logical opposites")
        return self


class UploadedImageInfo(BaseModel):
    filename: str
    content_type: str
    width: int
    height: int


class TimingInfo(BaseModel):
    preprocessing: float
    inference: float
    total: float


class PredictSuccessResponse(BaseModel):
    status: Literal["success"]
    prediction: PredictionOut
    top_predictions: List[ClassPredictionOut]
    # Reuses ConfidenceInfo (already defined above for /api/model-info) so
    # the confidence-policy shape can never drift between the two
    # endpoints -- both are populated from the same loaded ModelMetadata.
    confidence_policy: ConfidenceInfo
    input: UploadedImageInfo
    timing_ms: TimingInfo
    limitations: List[str]
