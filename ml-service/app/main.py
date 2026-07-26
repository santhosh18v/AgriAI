"""AgriAI ML Service -- FastAPI application.

Implements process health, readiness, model-information, and (as of
Milestone M7) the disease-prediction endpoint. There is still no upload
persistence, no prediction history, no Gemini fallback, and no Next.js
integration -- those are later milestones.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .model_loader import ModelLoader
from .routes import health, model_info, predict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("agri_ml.main")


def _build_lifespan(settings):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info(
            "Starting %s v%s (environment=%s, preferred_device=%s)",
            settings.app_name, settings.app_version, settings.environment, settings.preferred_device,
        )

        loader = ModelLoader(settings)
        app.state.settings = settings
        app.state.model_loader = loader

        if settings.eager_model_load:
            loader.load()
            if loader.is_ready:
                logger.info(
                    "Startup model load succeeded: device=%s duration=%.3fs",
                    loader.metadata.device, loader.load_duration_seconds,
                )
            else:
                # Sanitized reason only -- ModelLoadError messages never
                # contain paths or tracebacks. The app stays alive for
                # health diagnostics; readiness/model-info correctly report
                # unavailable.
                logger.warning("Startup model load failed: %s", loader.failure_reason)
        else:
            logger.info("Eager model loading disabled (AGRI_ML_EAGER_MODEL_LOAD=false); model is not loaded yet")

        yield

        logger.info("Shutting down %s", settings.app_name)
        if loader.is_ready and loader.metadata.device == "mps":
            try:
                import torch

                if torch.backends.mps.is_available():
                    torch.mps.empty_cache()
            except Exception:
                logger.debug("MPS cache clear skipped during shutdown", exc_info=False)
        loader.release()

    return lifespan


def create_app(settings=None) -> FastAPI:
    """Builds a fresh FastAPI app bound to `settings` (defaults to the
    process-wide cached Settings). Each call gets its own lifespan closure
    and its own ModelLoader -- used directly by tests to exercise a fully
    isolated app instance against a synthetic environment."""
    settings = settings or get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=_build_lifespan(settings),
    )

    # No credentials (cookies/auth headers) are used by this service, so
    # allow_credentials stays False even though allow_origins is a
    # specific, configured allowlist rather than "*". POST was added in M7
    # for the prediction endpoint; every other route remains GET-only.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api", tags=["health"])
    app.include_router(model_info.router, prefix="/api", tags=["model-info"])
    app.include_router(predict.router, prefix="/api", tags=["predict"])

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # Full detail (including traceback) is logged locally only; the API
        # response never includes it, an absolute path, or an environment
        # variable value.
        logger.exception("Unhandled exception while handling %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"status": "error", "detail": "internal server error"})

    return app


app = create_app()
