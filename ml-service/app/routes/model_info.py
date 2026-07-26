"""Model-information endpoint (Milestone M6).

Returns safe, public model metadata only -- never a checkpoint path, never
checkpoint/optimizer internals, and never a call into the model. Image
classification is M7 scope and does not exist here.
"""

from __future__ import annotations

from typing import Union

from fastapi import APIRouter, Depends, Response, status

from ..dependencies import get_model_loader
from ..model_loader import ModelLoader
from ..schemas import (
    ConfidenceInfo,
    EvaluationInfo,
    InputSpec,
    ModelInfoResponse,
    ModelUnavailableResponse,
)

router = APIRouter()


@router.get(
    "/model-info",
    response_model=Union[ModelInfoResponse, ModelUnavailableResponse],
    responses={503: {"model": ModelUnavailableResponse}},
)
def get_model_info(
    response: Response, loader: ModelLoader = Depends(get_model_loader)
) -> Union[ModelInfoResponse, ModelUnavailableResponse]:
    if not loader.is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ModelUnavailableResponse(
            status="unavailable",
            reason=loader.failure_reason or "model is not loaded",
        )

    m = loader.metadata
    return ModelInfoResponse(
        status="available",
        architecture=m.architecture,
        model_version=m.model_version,
        class_count=m.class_count,
        classes=list(m.classes),
        input=InputSpec(width=m.input_width, height=m.input_height, channels=m.input_channels),
        confidence=ConfidenceInfo(
            method=m.confidence_method,
            threshold=m.confidence_threshold,
            label="model confidence",
            production_calibrated=m.confidence_production_calibrated,
        ),
        evaluation=EvaluationInfo(
            frozen_test_accuracy=m.frozen_test_accuracy,
            frozen_test_macro_f1=m.frozen_test_macro_f1,
            dataset_context=m.dataset_context,
        ),
        limitations=list(m.limitations),
    )
