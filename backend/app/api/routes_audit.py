from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.app.core.security import CurrentUser, require_roles
from backend.app.services.runtime_state import runtime_state

router = APIRouter(prefix="/api/audit-logs", tags=["audit"])


@router.get("")
async def list_audit_logs(
    _: CurrentUser = Depends(require_roles("admin")),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict:
    return runtime_state.list_audit_logs(page=page, page_size=page_size)
