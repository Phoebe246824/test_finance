from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from models import NormalizedEvent


ConnectionFactory = Callable[[], sqlite3.Connection]
NowFn = Callable[[], datetime]


def _database_path_from_url(database_url: str) -> Path:
    if not database_url.startswith("sqlite:///"):
        raise RuntimeError("SQLiteStashStore expects a sqlite:/// DATABASE_URL")
    return Path(database_url.removeprefix("sqlite:///"))


def connection_factory_from_url(database_url: str) -> ConnectionFactory:
    db_path = _database_path_from_url(database_url)

    def _connect() -> sqlite3.Connection:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    return _connect


def _content_hash(raw_content: str) -> str:
    return hashlib.sha256(raw_content.encode("utf-8")).hexdigest()


class SQLiteStashStore:
    def __init__(
        self,
        connection_factory: ConnectionFactory,
        *,
        now_fn: NowFn | None = None,
        ttl_days: int = 90,
    ) -> None:
        self._connection_factory = connection_factory
        self._now_fn = now_fn or datetime.now
        self._ttl_days = ttl_days
        self._init_schema()

    @classmethod
    def from_database_url(
        cls,
        database_url: str,
        *,
        now_fn: NowFn | None = None,
        ttl_days: int = 90,
    ) -> SQLiteStashStore:
        return cls(
            connection_factory_from_url(database_url),
            now_fn=now_fn,
            ttl_days=ttl_days,
        )

    def _init_schema(self) -> None:
        with self._connection_factory() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS stashed_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT UNIQUE NOT NULL,
                    person_ids_json TEXT NOT NULL,
                    raw_content TEXT NOT NULL,
                    content_hash TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL,
                    expire_at TEXT NOT NULL,
                    is_graph_built INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_stashed_events_graph_expire
                    ON stashed_events(is_graph_built, expire_at);
                """
            )

    async def stash_event(self, event: NormalizedEvent, id_numbers: list[str]) -> int:
        content_hash = _content_hash(event.raw_content)
        person_ids = sorted({pid.upper() for pid in id_numbers})
        created_at = event.timestamp
        expire_at = created_at + timedelta(days=self._ttl_days)
        with self._connection_factory() as conn:
            result = conn.execute(
                """
                INSERT OR IGNORE INTO stashed_events (
                    event_id, person_ids_json, raw_content, content_hash,
                    created_at, expire_at, is_graph_built
                ) VALUES (?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    event.event_id,
                    json.dumps(person_ids, ensure_ascii=False),
                    event.raw_content,
                    content_hash,
                    created_at.isoformat(),
                    expire_at.isoformat(),
                ),
            )
        return int(result.rowcount)

    async def fetch_related_events(
        self,
        event: NormalizedEvent,
        id_numbers: list[str],
        top_k_semantic: int = 10,
        max_per_person: int = 20,
    ) -> list[dict]:
        del top_k_semantic
        now = self._now_fn().isoformat()
        current_person_ids = {pid.upper() for pid in id_numbers}
        rows = self._eligible_rows(event.event_id, now)

        matches: list[dict] = []
        for row in rows:
            person_ids = self._person_ids(row)
            if not current_person_ids.intersection(person_ids):
                continue
            matches.append(
                {
                    "event_id": row["event_id"],
                    "person_ids": person_ids,
                    "raw_content": row["raw_content"],
                    "content_hash": row["content_hash"],
                    "created_at": row["created_at"],
                    "expire_at": row["expire_at"],
                    "is_graph_built": bool(row["is_graph_built"]),
                    "match_source": "person_match",
                }
            )
            if len(matches) >= max_per_person:
                break
        return matches

    async def mark_events_graph_built(self, event_ids: list[str]) -> int:
        unique_ids = sorted({event_id for event_id in event_ids if event_id})
        if not unique_ids:
            return 0
        placeholders = ", ".join("?" for _ in unique_ids)
        with self._connection_factory() as conn:
            result = conn.execute(
                f"""
                UPDATE stashed_events
                SET is_graph_built = 1
                WHERE event_id IN ({placeholders})
                """,
                unique_ids,
            )
        return int(result.rowcount)

    def _eligible_rows(self, current_event_id: str, now: str) -> list[sqlite3.Row]:
        with self._connection_factory() as conn:
            return conn.execute(
                """
                SELECT * FROM stashed_events
                WHERE event_id != ?
                  AND is_graph_built = 0
                  AND expire_at > ?
                ORDER BY created_at DESC, event_id ASC
                """,
                (current_event_id, now),
            ).fetchall()

    @staticmethod
    def _person_ids(row: sqlite3.Row) -> list[str]:
        raw = row["person_ids_json"]
        data = json.loads(raw) if raw else []
        return [str(item).upper() for item in data]
