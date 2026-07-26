"""Health and readiness endpoints (Milestone M6).

GET /api/health confirms only that the FastAPI process is running -- it
never depends on the model being loaded and performs no I/O.

GET /api/ready reports whether the service can serve future predictions:
true only after the checkpoint, confidence policy, and class mapping have
all been validated and loaded successfully. It never reports ready based
on file existence alone.
"""

from __future__ import annotations

from typing import Union

from fastapi import APIRouter, Depends, Response, status

from ..config import Settings
from ..dependencies import get_model_loader, get_settings_dep
from ..model_loader import ModelLoader
from ..schemas import HealthResponse, NotReadyResponse, ReadyResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def get_health(settings: Settings = Depends(get_settings_dep)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )


@router.get(
    "/ready",
    response_model=Union[ReadyResponse, NotReadyResponse],
    responses={503: {"model": NotReadyResponse}},
)
def get_ready(
    response: Response, loader: ModelLoader = Depends(get_model_loader)
) -> Union[ReadyResponse, NotReadyResponse]:
    if not loader.is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return NotReadyResponse(
            status="not_ready",
            model_loaded=False,
            reason=loader.failure_reason or "model has not been loaded yet",
        )

    metadata = loader.metadata
    return ReadyResponse(
        status="ready",
        model_loaded=True,
        confidence_policy_loaded=True,
        class_count=metadata.class_count,
    )
