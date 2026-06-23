from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api import (
    routes_analysis,
    routes_blacklist,
    routes_dashboard,
    routes_events,
    routes_graph,
    routes_system,
)
from backend.app.core.config import settings


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(routes_analysis.router)
    app.include_router(routes_dashboard.router)
    app.include_router(routes_events.router)
    app.include_router(routes_blacklist.router)
    app.include_router(routes_graph.router)
    app.include_router(routes_system.router)
    return app


app = create_app()
