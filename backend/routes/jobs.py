"""Job polling."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.deps import get_state
from backend.runtime import AppState

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("")
def list_active_jobs(state: AppState = Depends(get_state)) -> dict:
    return {"jobs": [job.to_dict() for job in state.tasks.active()]}


@router.get("/{job_id}")
def get_job(job_id: str, state: AppState = Depends(get_state)) -> dict:
    job = state.tasks.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job.to_dict()
