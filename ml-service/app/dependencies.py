"""FastAPI dependency providers (Milestone M6).

Thin accessors over `app.state`, set once in main.py's lifespan handler.
Kept separate from the route modules so routes stay free of any direct
knowledge of how the settings/model loader were constructed.
"""

from __future__ import annotations

from fastapi import Request

from .config import Settings
from .model_loader import ModelLoader


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_model_loader(request: Request) -> ModelLoader:
    return request.app.state.model_loader
