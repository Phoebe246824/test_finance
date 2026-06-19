from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from redis.asyncio import Redis

from backend.app.db.session import get_connection
from main import load_config
from blacklist.store import BlacklistStore

router = APIRouter(prefix="/api/blacklist", tags=["blacklist"])


class BlacklistCreate(BaseModel):
    value: str = Field(..., min_length=1)
    summary: str = ""
    description: str = ""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


async def _store() -> tuple[Redis, BlacklistStore]:
    config = load_config()
    redis = Redis(
        host=config["redis"]["host"],
        port=config["redis"]["port"],
        password=config["redis"]["password"] or None,
        db=config["redis"]["blacklist_db"],
        decode_responses=False,
    )
    return redis, BlacklistStore(redis)


def _upsert_item(item_type: str, value: str, summary: str, description: str) -> None:
    now = _now()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO blacklist_items (
                item_type, value, summary, description, enabled, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(item_type, value) DO UPDATE SET
                summary=excluded.summary,
                description=excluded.description,
                enabled=1,
                updated_at=excluded.updated_at
            """,
            (item_type, value, summary, description, now, now),
        )


def _list_items(item_type: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM blacklist_items
            WHERE item_type = ? AND enabled = 1
            ORDER BY updated_at DESC
            """,
            (item_type,),
        ).fetchall()
    return [dict(row) for row in rows]


def _disable_item(item_type: str, value: str) -> bool:
    with get_connection() as conn:
        result = conn.execute(
            """
            UPDATE blacklist_items
            SET enabled = 0, updated_at = ?
            WHERE item_type = ? AND value = ?
            """,
            (_now(), item_type, value),
        )
    return result.rowcount > 0


@router.get("/{item_type}")
async def list_blacklist_items(item_type: str) -> dict:
    if item_type not in {"persons", "keywords", "events"}:
        raise HTTPException(status_code=404, detail="unknown blacklist type")
    normalized = {"persons": "person", "keywords": "keyword", "events": "event"}[
        item_type
    ]
    return {"items": _list_items(normalized)}


@router.post("/{item_type}")
async def create_blacklist_item(item_type: str, payload: BlacklistCreate) -> dict:
    if item_type not in {"persons", "keywords", "events"}:
        raise HTTPException(status_code=404, detail="unknown blacklist type")

    redis, store = await _store()
    try:
        if item_type == "persons":
            await store.append_person(payload.value)
            normalized = "person"
        elif item_type == "keywords":
            await store.append_keyword(payload.value)
            normalized = "keyword"
        else:
            await store.append_event(payload.value, payload.summary or payload.description)
            normalized = "event"
        _upsert_item(normalized, payload.value, payload.summary, payload.description)
        return {"created": True, "item_type": normalized, "value": payload.value}
    finally:
        await redis.aclose()


@router.delete("/{item_type}/{value}")
async def delete_blacklist_item(item_type: str, value: str) -> dict:
    if item_type not in {"persons", "keywords", "events"}:
        raise HTTPException(status_code=404, detail="unknown blacklist type")

    redis, store = await _store()
    try:
        if item_type == "persons":
            removed = await store.remove_person(value)
            normalized = "person"
        elif item_type == "keywords":
            removed = await store.remove_keyword(value)
            normalized = "keyword"
        else:
            removed = await store.remove_event(value)
            normalized = "event"
        db_removed = _disable_item(normalized, value)
        if not removed and not db_removed:
            raise HTTPException(status_code=404, detail="blacklist item not found")
        return {"deleted": True, "item_type": normalized, "value": value}
    finally:
        await redis.aclose()
