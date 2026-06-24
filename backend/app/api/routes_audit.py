from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from backend.app.core.security import CurrentUser, require_roles
from backend.app.services.runtime_state import runtime_state

router = APIRouter(prefix="/api/audit-logs", tags=["audit"])


@router.get("")
async def list_audit_logs(
    _: CurrentUser = Depends(require_roles("admin")),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    actor: str | None = Query(None, max_length=64),
    action: str | None = Query(None, max_length=128),
    resource_type: str | None = Query(None, max_length=64),
    date_from: str | None = Query(None, max_length=32),
    date_to: str | None = Query(None, max_length=32),
) -> dict:
    result = runtime_state.list_audit_logs(page=1, page_size=10000)
    items = result["items"]

    if actor:
        items = [r for r in items if actor.lower() in str(r.get("actor", "")).lower()]
    if action:
        items = [r for r in items if action in str(r.get("action", ""))]
    if resource_type:
        items = [r for r in items if resource_type in str(r.get("resource_type", ""))]
    if date_from:
        items = [r for r in items if str(r.get("created_at", "")) >= date_from]
    if date_to:
        items = [r for r in items if str(r.get("created_at", "")) <= date_to]

    total = len(items)
    offset = (page - 1) * page_size
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items[offset: offset + page_size],
    }
