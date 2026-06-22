from __future__ import annotations

import os
import sqlite3

from fastapi import APIRouter

from backend.app.db.session import get_connection
from sentinel_edge import collect_hardware_profile

router = APIRouter(prefix="/api/system", tags=["system"])


def _database_ready() -> bool:
    try:
        with get_connection() as conn:
            conn.execute("SELECT 1").fetchone()
    except (RuntimeError, sqlite3.Error):
        return False
    return True


@router.get("/health")
async def health() -> dict:
    return {
        "api": True,
        "database": _database_ready(),
        "blacklist_backend": (os.getenv("BLACKLIST_BACKEND") or "sqlite").lower(),
        "stash_backend": (os.getenv("STASH_BACKEND") or "sqlite").lower(),
    }


@router.get("/hardware")
async def hardware() -> dict:
    return collect_hardware_profile().to_dict()
