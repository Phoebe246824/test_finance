from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import datetime
from pathlib import Path


ConnectionFactory = Callable[[], sqlite3.Connection]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _database_path_from_url(database_url: str) -> Path:
    if not database_url.startswith("sqlite:///"):
        raise RuntimeError("SQLiteBlacklistStore expects a sqlite:/// DATABASE_URL")
    return Path(database_url.removeprefix("sqlite:///"))


def connection_factory_from_url(database_url: str) -> ConnectionFactory:
    db_path = _database_path_from_url(database_url)

    def _connect() -> sqlite3.Connection:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    return _connect


class SQLiteBlacklistStore:
    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._connection_factory = connection_factory
        self._init_schema()

    @classmethod
    def from_database_url(cls, database_url: str) -> SQLiteBlacklistStore:
        return cls(connection_factory_from_url(database_url))

    def _init_schema(self) -> None:
        with self._connection_factory() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS blacklist_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_type TEXT NOT NULL,
                    value TEXT NOT NULL,
                    summary TEXT,
                    description TEXT,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(item_type, value)
                );
                """
            )

    async def query_person(self, id_number: str) -> float | None:
        row = self._get_item("person", id_number.upper())
        return 1.0 if row is not None else None

    async def query_keywords(self) -> list[str]:
        with self._connection_factory() as conn:
            rows = conn.execute(
                """
                SELECT value FROM blacklist_items
                WHERE item_type = 'keyword' AND enabled = 1
                ORDER BY updated_at DESC, value ASC
                """
            ).fetchall()
        return [str(row["value"]) for row in rows]

    async def query_event(self, event_id: str) -> dict[str, str] | None:
        row = self._get_item("event", event_id)
        if row is None:
            return None
        return {
            "event_id": str(row["value"]),
            "summary": str(row["description"] or row["summary"] or ""),
        }

    async def append_person(self, id_number: str) -> int:
        self._upsert_item("person", id_number.upper(), "", "")
        return 1

    async def append_keyword(self, keyword: str) -> int:
        self._upsert_item("keyword", keyword, "", "")
        return 1

    async def append_event(self, event_id: str, summary: str) -> int:
        self._upsert_item("event", event_id, "", summary)
        return 1

    async def remove_person(self, id_number: str) -> bool:
        return self._disable_item("person", id_number.upper())

    async def remove_keyword(self, keyword: str) -> bool:
        return self._disable_item("keyword", keyword)

    async def remove_event(self, event_id: str) -> bool:
        return self._disable_item("event", event_id)

    async def get_person_stats(self) -> dict[str, float]:
        return self._stats_for_type("person")

    async def get_keyword_stats(self) -> dict[str, float]:
        return self._stats_for_type("keyword")

    async def get_event_count(self) -> int:
        with self._connection_factory() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS count FROM blacklist_items
                WHERE item_type = 'event' AND enabled = 1
                """
            ).fetchone()
        return int(row["count"])

    async def get_event_summaries(self) -> dict[str, str]:
        with self._connection_factory() as conn:
            rows = conn.execute(
                """
                SELECT value, summary, description FROM blacklist_items
                WHERE item_type = 'event' AND enabled = 1
                ORDER BY updated_at DESC, value ASC
                """
            ).fetchall()
        return {
            str(row["value"]): json.dumps(
                {
                    "event_id": str(row["value"]),
                    "summary": str(row["description"] or row["summary"] or ""),
                },
                ensure_ascii=False,
            )
            for row in rows
        }

    def _get_item(self, item_type: str, value: str) -> sqlite3.Row | None:
        with self._connection_factory() as conn:
            return conn.execute(
                """
                SELECT * FROM blacklist_items
                WHERE item_type = ? AND value = ? AND enabled = 1
                """,
                (item_type, value),
            ).fetchone()

    def _upsert_item(
        self,
        item_type: str,
        value: str,
        summary: str,
        description: str,
    ) -> None:
        now = _now()
        with self._connection_factory() as conn:
            conn.execute(
                """
                INSERT INTO blacklist_items (
                    item_type, value, summary, description, enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(item_type, value) DO UPDATE SET
                    summary=CASE
                        WHEN excluded.summary != '' THEN excluded.summary
                        ELSE blacklist_items.summary
                    END,
                    description=CASE
                        WHEN excluded.description != '' THEN excluded.description
                        ELSE blacklist_items.description
                    END,
                    enabled=1,
                    updated_at=excluded.updated_at
                """,
                (item_type, value, summary, description, now, now),
            )

    def _disable_item(self, item_type: str, value: str) -> bool:
        with self._connection_factory() as conn:
            result = conn.execute(
                """
                UPDATE blacklist_items
                SET enabled = 0, updated_at = ?
                WHERE item_type = ? AND value = ? AND enabled = 1
                """,
                (_now(), item_type, value),
            )
        return result.rowcount > 0

    def _stats_for_type(self, item_type: str) -> dict[str, float]:
        with self._connection_factory() as conn:
            rows = conn.execute(
                """
                SELECT value FROM blacklist_items
                WHERE item_type = ? AND enabled = 1
                ORDER BY updated_at DESC, value ASC
                """,
                (item_type,),
            ).fetchall()
        return {str(row["value"]): 1.0 for row in rows}
