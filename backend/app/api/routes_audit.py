from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query

from backend.app.core.security import CurrentUser, require_roles
from backend.app.db.session import get_connection

router = APIRouter(prefix="/api/audit-logs", tags=["audit"])


@router.get("")
async def list_audit_logs(
    _: CurrentUser = Depends(require_roles("admin")),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict:
    offset = (page - 1) * page_size
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) AS count FROM audit_logs").fetchone()["count"]
        rows = conn.execute(
            """
            SELECT * FROM audit_logs
            ORDER BY created_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (page_size, offset),
        ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["detail"] = json.loads(item.pop("detail_json") or "{}")
        items.append(item)
    return {"total": total, "page": page, "page_size": page_size, "items": items}
