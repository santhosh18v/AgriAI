"""Pydantic request/response schemas for the ml-service FastAPI endpoints.

Schema definitions only — no routes, no model loading, no inference logic.
Endpoint implementations are added in later milestones (M6/M7).
"""

from typing import List, Literal, Tuple

from pydantic import BaseModel, Field


class ClassPrediction(BaseModel):
    class_name: str
    confidence: float = Field(ge=0.0, le=1.0)


class PredictDiseaseResponse(BaseModel):
    status: Literal["ok"]
    predictions: List[ClassPrediction]
    top_prediction: ClassPrediction
    is_uncertain: bool
    # NOTE: intentionally not named `is_supported_image`. This is a
    # confidence/margin heuristic, not true out-of-distribution detection —
    # see plan section 16. A valid photo of an unsupported crop/disease
    # should surface as low reliability, not a definitive "unsupported"
    # classification.
    prediction_reliable: bool
    model_version: str
    inference_ms: float


class PredictErrorResponse(BaseModel):
    status: Literal["error"]
    error_code: Literal[
        "invalid_file",       # wrong MIME type or oversized
        "unreadable_image",   # fails decode/verify, or exceeds pixel/dimension caps
        "internal_error",
    ]
    message: str


class HealthResponse(BaseModel):
    status: Literal["ok"]
    model_loaded: bool
    uptime_seconds: float


class ModelInfoResponse(BaseModel):
    model_name: str
    model_version: str
    dataset_version: str
    classes: List[str]
    input_size: Tuple[int, int]
    trained_at: str
    test_accuracy: float
    test_macro_f1: float
    uncertainty_threshold: float


class ModelNotLoadedResponse(BaseModel):
    status: Literal["not_loaded"]
    message: str
