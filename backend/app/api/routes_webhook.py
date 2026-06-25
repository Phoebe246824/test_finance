from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from backend.app.core.config import settings
from backend.app.core.security import CurrentUser
from backend.app.services.audit_service import write_audit_log

router = APIRouter(prefix="/webhook", tags=["webhook"])

SYSTEM_WEBHOOK_ACTOR = CurrentUser(username="webhook", role="system")


@router.post("/alert")
async def receive_alert_webhook(
    request: Request,
    x_sentinel_webhook_token: str | None = Header(default=None),
) -> dict[str, bool]:
    if x_sentinel_webhook_token != settings.webhook_token:
        raise HTTPException(status_code=401, detail="missing or invalid webhook token")
    payload: dict[str, Any] = await request.json()
    write_audit_log(
        actor=SYSTEM_WEBHOOK_ACTOR,
        action="webhook.received",
        resource_type="notification",
        resource_id=str(payload.get("event") or ""),
        detail=payload,
    )
    return {"accepted": True}
