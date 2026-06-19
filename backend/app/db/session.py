from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

from backend.app.core.config import settings


def _database_file() -> Path:
    url = settings.database_url
    if not url.startswith("sqlite:///"):
        raise RuntimeError("MVP storage currently expects a sqlite:/// DATABASE_URL")
    return Path(url.removeprefix("sqlite:///"))


def get_connection() -> sqlite3.Connection:
    db_path = _database_file()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def connection_scope() -> Iterator[sqlite3.Connection]:
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS financial_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT UNIQUE NOT NULL,
                title TEXT,
                raw_content TEXT NOT NULL,
                source TEXT,
                event_type TEXT,
                summary TEXT,
                status TEXT NOT NULL,
                risk_level TEXT,
                risk_score REAL,
                reasoning TEXT,
                blacklist_decision TEXT,
                matched_persons_json TEXT,
                matched_keywords_json TEXT,
                event_similarity_json TEXT,
                dimension_scores_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS analysis_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT UNIQUE NOT NULL,
                event_id TEXT,
                status TEXT NOT NULL,
                error_message TEXT,
                started_at TEXT NOT NULL,
                finished_at TEXT
            );

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
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(financial_events)").fetchall()
        }
        if "dimension_scores_json" not in columns:
            conn.execute(
                "ALTER TABLE financial_events ADD COLUMN dimension_scores_json TEXT"
            )
