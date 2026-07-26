"""POST /api/predict/disease -- the M7 disease-prediction endpoint.

Accepts exactly one image upload (multipart field name: "file"). Validates
it in memory, preprocesses it with the exact M4 validation transform, runs
the already-loaded EfficientNet-B0 model once, and returns a structured
prediction using the frozen, validation-selected confidence threshold.
Never accepts a caller-supplied threshold. Never persists the upload to
disk. Returns HTTP 200 for any completed prediction, including uncertain
ones -- uncertainty is a normal, expected outcome, not an error.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.responses import JSONResponse

from ..config import Settings
from ..dependencies import get_model_loader, get_settings_dep
from ..image_validation import ImageValidationError, read_upload_bounded, validate_upload
from ..inference import run_inference
from ..model_loader import ModelLoader
from ..schemas import (
    ClassPredictionOut,
    ConfidenceInfo,
    ErrorResponse,
    PredictionOut,
    PredictSuccessResponse,
    TimingInfo,
    UploadedImageInfo,
)

logger = logging.getLogger("agri_ml.predict")
router = APIRouter()

_UNCERTAIN_MESSAGE = "The model confidence is below the configured threshold."

_ERROR_STATUS_BY_CODE = {
    "invalid_file": status.HTTP_400_BAD_REQUEST,
    "malformed_image": status.HTTP_400_BAD_REQUEST,
    "mime_mismatch": status.HTTP_400_BAD_REQUEST,
    "animated_image_not_supported": status.HTTP_400_BAD_REQUEST,
    "image_too_large": status.HTTP_400_BAD_REQUEST,
    "file_too_large": status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
    "unsupported_media_type": status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
}


def _error_response(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=ErrorResponse(status="error", detail=detail).model_dump())


@router.post(
    "/predict/disease",
    response_model=PredictSuccessResponse,
    responses={
        400: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
        415: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def predict_disease(
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings_dep),
    loader: ModelLoader = Depends(get_model_loader),
):
    if not loader.is_ready:
        return _error_response(status.HTTP_503_SERVICE_UNAVAILABLE, loader.failure_reason or "model is not loaded")

    try:
        raw_bytes = read_upload_bounded(file.file, settings.max_upload_bytes)
        validated = validate_upload(
            filename=file.filename,
            content_type=file.content_type,
            raw_bytes=raw_bytes,
            max_upload_bytes=settings.max_upload_bytes,
            allowed_extensions=set(settings.allowed_image_extensions),
            allowed_mime_types=set(settings.allowed_image_mime_types),
            max_decode_pixels=settings.image_decode_max_pixels,
        )
    except ImageValidationError as e:
        status_code = _ERROR_STATUS_BY_CODE.get(e.error_code, status.HTTP_400_BAD_REQUEST)
        logger.info("Prediction upload rejected: category=%s", e.error_code)
        return _error_response(status_code, e.message)

    try:
        result = run_inference(loader, validated.image, top_k=settings.top_k_predictions)
    except Exception:
        logger.exception("Unexpected inference failure")
        return _error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "internal server error")

    metadata = loader.metadata
    logger.info(
        "Prediction complete: accepted=%s class=%s confidence=%.4f preprocessing_ms=%.1f inference_ms=%.1f",
        result.accepted, result.top_prediction.class_name, round(result.top_prediction.confidence, 4),
        result.preprocessing_ms, result.inference_ms,
    )

    return PredictSuccessResponse(
        status="success",
        prediction=PredictionOut(
            class_name=result.top_prediction.class_name,
            class_index=result.top_prediction.class_index,
            model_confidence=result.top_prediction.confidence,
            accepted=result.accepted,
            uncertain=result.uncertain,
            message=None if result.accepted else _UNCERTAIN_MESSAGE,
        ),
        top_predictions=[
            ClassPredictionOut(class_name=c.class_name, class_index=c.class_index, model_confidence=c.confidence)
            for c in result.top_predictions
        ],
        confidence_policy=ConfidenceInfo(
            method=metadata.confidence_method,
            threshold=metadata.confidence_threshold,
            label="model confidence",
            production_calibrated=metadata.confidence_production_calibrated,
        ),
        input=UploadedImageInfo(
            filename=validated.filename,
            content_type=validated.content_type,
            width=validated.original_width,
            height=validated.original_height,
        ),
        timing_ms=TimingInfo(
            preprocessing=round(result.preprocessing_ms, 2),
            inference=round(result.inference_ms, 2),
            total=round(result.total_ms, 2),
        ),
        limitations=list(metadata.limitations),
    )
