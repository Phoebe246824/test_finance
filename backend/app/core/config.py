from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    app_name: str = "Sentinel Edge API"
    cors_origins: tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    )

    @property
    def auth_enabled(self) -> bool:
        return os.getenv("AUTH_ENABLED", "true").lower() not in {"0", "false", "no"}

    @property
    def admin_token(self) -> str:
        return os.getenv("SENTINEL_ADMIN_TOKEN", "sentinel-admin-token")

    @property
    def reviewer_token(self) -> str:
        return os.getenv("SENTINEL_REVIEWER_TOKEN", "sentinel-reviewer-token")


settings = Settings()
