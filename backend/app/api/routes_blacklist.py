from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.app.core.security import CurrentUser, require_roles
from backend.app.services import store_provider
from backend.app.services.audit_service import write_audit_log

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


def _stored_value(item_type: str, value: str) -> str:
    if item_type == "person":
        return value.upper()
    return value


async def _append_item(item_type: str, payload: BlacklistCreate) -> None:
    store = _store_for(item_type)
    if item_type == "person":
        await store.append_person(
            payload.value,
            summary=payload.summary,
            description=payload.description,
        )
    elif item_type == "keyword":
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


def _item_exists(item_type: str, value: str) -> bool:
    stored = _stored_value(item_type, value)
    return any(
        str(row.get("value") or "") == stored for row in _store_for(item_type).list_items()
    )


async def _remove_item(item_type: str, value: str) -> bool:
    store = _store_for(item_type)
    return await {
        "person": store.remove_person,
        "keyword": store.remove_keyword,
        "event": store.remove_event,
    }[item_type](value)


@router.get("/{item_type}")
async def list_blacklist_items(item_type: str) -> dict:
    normalized = _normalize_item_type(item_type)
    return {"items": _store_for(normalized).list_items()}


@router.post("/{item_type}")
async def create_blacklist_item(
    item_type: str,
    payload: BlacklistCreate,
    user: CurrentUser = Depends(require_roles("admin")),
) -> dict:
    normalized = _normalize_item_type(item_type)
    await _append_item(normalized, payload)
    write_audit_log(
        actor=user,
        action="blacklist.create",
        resource_type=normalized,
        resource_id=payload.value,
        detail={"summary": payload.summary, "description": payload.description},
    )
    return {"created": True, "item_type": normalized, "value": payload.value}


@router.put("/{item_type}/{value}")
async def update_blacklist_item(
    item_type: str,
    value: str,
    payload: BlacklistCreate,
    user: CurrentUser = Depends(require_roles("admin")),
) -> dict:
    normalized = _normalize_item_type(item_type)
    if not _item_exists(normalized, value):
        raise HTTPException(status_code=404, detail="blacklist item not found")
    await _append_item(normalized, payload)
    if _stored_value(normalized, payload.value) != _stored_value(normalized, value):
        await _remove_item(normalized, value)
    write_audit_log(
        actor=user,
        action="blacklist.update",
        resource_type=normalized,
        resource_id=payload.value,
        detail={
            "old_value": value,
            "new_value": payload.value,
            "summary": payload.summary,
            "description": payload.description,
        },
    )
    return {"updated": True, "item_type": normalized, "value": payload.value}


@router.delete("/{item_type}/{value}")
async def delete_blacklist_item(
    item_type: str,
    value: str,
    user: CurrentUser = Depends(require_roles("admin")),
) -> dict:
    normalized = _normalize_item_type(item_type)
    removed = await _remove_item(normalized, value)
    if not removed:
        raise HTTPException(status_code=404, detail="blacklist item not found")
    write_audit_log(
        actor=user,
        action="blacklist.delete",
        resource_type=normalized,
        resource_id=value,
    )
    return {"deleted": True, "item_type": normalized, "value": value}
