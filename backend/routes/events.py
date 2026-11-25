"""Server-sent events consumed by the desktop UI."""

from __future__ import annotations

import asyncio
import json
import queue

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from backend.deps import get_state
from backend.runtime import AppState

router = APIRouter(tags=["events"])

_HEARTBEAT_SECONDS = 15


@router.get("/events")
async def stream_events(
    request: Request,
    state: AppState = Depends(get_state),
) -> StreamingResponse:
    channel = state.events.subscribe()

    async def generate():
        try:
            yield ": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.to_thread(
                        channel.get, True, _HEARTBEAT_SECONDS
                    )
                except queue.Empty:
                    yield ": ping\n\n"
                    continue
                payload = json.dumps(event, ensure_ascii=False)
                yield f"data: {payload}\n\n"
        finally:
            state.events.unsubscribe(channel)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
