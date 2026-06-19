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
    database_path: Path = ROOT / "data" / "sentinel_edge.db"
    cors_origins: tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    )

    @property
    def database_url(self) -> str:
        return os.getenv("DATABASE_URL") or f"sqlite:///{self.database_path}"


settings = Settings()
