from __future__ import annotations

from fastapi import APIRouter
from redis.asyncio import Redis

from backend.app.core.config import settings
from main import load_config
from sentinel_edge import collect_hardware_profile

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/health")
async def health() -> dict:
    config = load_config()
    checks = {"api": True, "redis": False, "database": settings.database_path.exists()}
    redis = Redis(
        host=config["redis"]["host"],
        port=config["redis"]["port"],
        password=config["redis"]["password"] or None,
        db=config["redis"]["blacklist_db"],
    )
    try:
        checks["redis"] = bool(await redis.ping())
    finally:
        await redis.aclose()
    return checks


@router.get("/hardware")
async def hardware() -> dict:
    return collect_hardware_profile().to_dict()
