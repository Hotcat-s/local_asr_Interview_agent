"""Health, model discovery and engine lifecycle."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from core.models.manager import ModelManager

from backend import __version__
from backend.deps import get_state
from backend.runtime import AppState

router = APIRouter(tags=["system"])


def build_health(state: AppState) -> dict:
    models = ModelManager().list_available()
    return {
        "status": "healthy",
        "version": __version__,
        "data_dir": str(state.paths.data_dir),
        "config_path": str(state.paths.config_path),
        "db_path": str(state.paths.db_path),
        "engine_loaded": state.engine_loaded,
        "models": models,
        "models_ready": all(item["exists"] for item in models),
        "active_jobs": [job.to_dict() for job in state.tasks.active()],
    }


@router.get("/health")
def health(state: AppState = Depends(get_state)) -> dict:
    return build_health(state)


@router.get("/models")
def list_models() -> dict:
    return {"models": ModelManager().list_available()}


@router.post("/models/reload")
def reload_models(state: AppState = Depends(get_state)) -> dict:
    state.unload_engine()
    return {"ok": True, "engine_loaded": False}


@router.post("/engine/unload")
def unload_engine(state: AppState = Depends(get_state)) -> dict:
    state.unload_engine()
    return {"ok": True, "engine_loaded": False}
