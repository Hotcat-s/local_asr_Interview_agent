"""Read / update runtime configuration and test the LLM connection."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends

from core.config import AppConfig
from core.llm.client import LLMClient

from backend.deps import get_state
from backend.runtime import AppState
from backend.schemas import SettingsPayload, TestLLMRequest

router = APIRouter(prefix="/settings", tags=["settings"])

_NESTED = ("models", "llm", "analysis")
_SCALARS = ("chunk_seconds", "use_embedding_segmentation")


@router.get("")
def get_settings(state: AppState = Depends(get_state)) -> dict:
    return asdict(state.config)


@router.put("")
def update_settings(payload: SettingsPayload, state: AppState = Depends(get_state)) -> dict:
    current = asdict(state.config)
    incoming = payload.model_dump(exclude_none=True)

    for key in _NESTED:
        if key in incoming:
            current[key] = {**current[key], **incoming[key]}
    for key in _SCALARS:
        if key in incoming and incoming[key] is not None:
            current[key] = incoming[key]

    config = AppConfig.from_dict(current)
    state.update_config(config)
    return asdict(state.config)


@router.post("/test-llm")
def test_llm(payload: TestLLMRequest, state: AppState = Depends(get_state)) -> dict:
    llm = state.config.llm
    if payload.llm is not None:
        overrides = payload.llm.model_dump(exclude_none=True)
        llm = type(llm)(**{**asdict(llm), **overrides})
    ok, message = LLMClient(llm).test_connection()
    return {"ok": ok, "message": message}
