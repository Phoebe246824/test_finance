from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

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
    routes_webhook,
)
from backend.app.core.config import settings
from backend.app.services.runtime_state import runtime_state

logger = logging.getLogger(__name__)

_CLEANUP_INTERVAL = 300


async def _periodic_task_cleanup() -> None:
    while True:
        await asyncio.sleep(_CLEANUP_INTERVAL)
        try:
            removed = runtime_state.cleanup_stale_tasks()
            if removed:
                logger.info("Periodic cleanup removed %d stale tasks", removed)
        except Exception:
            logger.exception("Error in periodic task cleanup")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    task = asyncio.create_task(_periodic_task_cleanup())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
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
    app.include_router(routes_webhook.router)
    app.include_router(routes_model_services.router)
    app.include_router(routes_notifications.router)
    return app


app = create_app()
