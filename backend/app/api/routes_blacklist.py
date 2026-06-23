from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.services import store_provider

router = APIRouter(prefix="/api/blacklist", tags=["blacklist"])
ITEM_TYPE_MAP = {"persons": "person", "keywords": "keyword", "events": "event"}


class BlacklistCreate(BaseModel):
    value: str = Field(..., min_length=1)
    summary: str = ""
    description: str = ""


def _normalize_item_type(item_type: str) -> str:
    normalized = ITEM_TYPE_MAP.get(item_type)
    if normalized is None:
        raise HTTPException(status_code=404, detail="unknown blacklist type")
    return normalized


def _store_for(item_type: str) -> Any:
    stores = store_provider.get_store_bundle()
    return {
        "person": stores.persons,
        "keyword": stores.keywords,
        "event": stores.event_samples,
    }[item_type]


@router.get("/{item_type}")
async def list_blacklist_items(item_type: str) -> dict:
    normalized = _normalize_item_type(item_type)
    return {"items": _store_for(normalized).list_items()}


@router.post("/{item_type}")
async def create_blacklist_item(item_type: str, payload: BlacklistCreate) -> dict:
    normalized = _normalize_item_type(item_type)
    store = _store_for(normalized)
    if normalized == "person":
        await store.append_person(
            payload.value,
            summary=payload.summary,
            description=payload.description,
        )
    elif normalized == "keyword":
        await store.append_keyword(
            payload.value,
            summary=payload.summary,
            description=payload.description,
        )
    else:
        await store.append_event(
            payload.value,
            payload.summary or payload.value,
            payload.description,
        )
    return {"created": True, "item_type": normalized, "value": payload.value}


@router.delete("/{item_type}/{value}")
async def delete_blacklist_item(item_type: str, value: str) -> dict:
    normalized = _normalize_item_type(item_type)
    store = _store_for(normalized)
    removed = await {
        "person": store.remove_person,
        "keyword": store.remove_keyword,
        "event": store.remove_event,
    }[normalized](value)
    if not removed:
        raise HTTPException(status_code=404, detail="blacklist item not found")
    return {"deleted": True, "item_type": normalized, "value": value}
