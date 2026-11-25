"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend import __version__
from backend.routes import events, jobs, recordings, settings, system
from backend.runtime import AppState, RuntimePaths


def create_app(data_dir: str | None = None) -> FastAPI:
    paths = RuntimePaths.resolve(data_dir)
    state = AppState(paths)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            yield
        finally:
            state.shutdown()

    app = FastAPI(
        title="Local Interview Agent",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.interview = state

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for router in (system.router, recordings.router, jobs.router, settings.router, events.router):
        app.include_router(router, prefix="/api")

    @app.get("/health")
    def health() -> dict:
        return system.build_health(state)

    return app
