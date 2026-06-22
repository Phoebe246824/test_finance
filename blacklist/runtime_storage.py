from __future__ import annotations

import os
from typing import Protocol

from redis.asyncio import Redis

from blacklist.milvus_stash import MilvusStashStore
from blacklist.sqlite_stash import SQLiteStashStore
from blacklist.sqlite_store import SQLiteBlacklistStore
from blacklist.store import BlacklistStore
from models import NormalizedEvent


class StashStore(Protocol):
    async def stash_event(self, event: NormalizedEvent, id_numbers: list[str]) -> int:
        ...

    async def fetch_related_events(
        self,
        event: NormalizedEvent,
        id_numbers: list[str],
        top_k_semantic: int = 10,
        max_per_person: int = 20,
    ) -> list[dict]:
        ...

    async def mark_events_graph_built(self, event_ids: list[str]) -> int:
        ...


def default_database_url() -> str:
    return f"sqlite:///{os.path.join(os.getcwd(), 'data', 'sentinel_edge.db')}"


def storage_config(config: dict) -> dict:
    config_storage = config.setdefault("storage", {})
    config_storage.setdefault(
        "database_url", os.getenv("DATABASE_URL") or default_database_url()
    )
    config_storage.setdefault(
        "blacklist_backend", (os.getenv("BLACKLIST_BACKEND") or "sqlite").lower()
    )
    config_storage.setdefault(
        "stash_backend", (os.getenv("STASH_BACKEND") or "sqlite").lower()
    )
    return config_storage


def create_blacklist_store(
    config: dict,
) -> tuple[BlacklistStore | SQLiteBlacklistStore, Redis | None]:
    config_storage = storage_config(config)
    backend = config_storage.get("blacklist_backend", "sqlite")
    if backend == "redis":
        redis_client = Redis(
            host=config["redis"]["host"],
            port=config["redis"]["port"],
            password=config["redis"]["password"] or None,
            db=config["redis"]["blacklist_db"],
            decode_responses=False,
        )
        return BlacklistStore(redis_client), redis_client
    return SQLiteBlacklistStore.from_database_url(
        config_storage["database_url"]
    ), None


def create_stash_store(config: dict) -> StashStore:
    config_storage = storage_config(config)
    backend = config_storage.get("stash_backend", "sqlite")
    if backend == "milvus":
        return MilvusStashStore.from_config(config)
    return SQLiteStashStore.from_database_url(
        config_storage["database_url"],
        ttl_days=int(config.get("milvus", {}).get("stash_ttl_days") or 90),
    )
