from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api import (
    routes_audit,
    routes_analysis,
    routes_auth,
    routes_blacklist,
    routes_dashboard,
    routes_events,
    routes_graph,
    routes_model_services,
    routes_notifications,
    routes_risk_rules,
    routes_settings,
    routes_system,
    routes_users,
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
    app.include_router(routes_auth.router)
    app.include_router(routes_audit.router)
    app.include_router(routes_dashboard.router)
    app.include_router(routes_events.router)
    app.include_router(routes_blacklist.router)
    app.include_router(routes_graph.router)
    app.include_router(routes_risk_rules.router)
    app.include_router(routes_settings.router)
    app.include_router(routes_system.router)
    app.include_router(routes_users.router)
    app.include_router(routes_model_services.router)
    app.include_router(routes_notifications.router)
    return app


app = create_app()
