from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.app.core.security import CurrentUser, require_roles
from backend.app.services.audit_service import write_audit_log
from backend.app.services.settings_service import (
    list_notification_channels,
    update_notification_channel,
    test_notification_channel,
)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class NotificationChannelUpdatePayload(BaseModel):
    enabled: bool = Field(default=True)
    target: str = Field(..., min_length=1, max_length=512)


@router.get("")
async def api_list_notification_channels(
    _: CurrentUser = Depends(require_roles("admin")),
) -> dict:
    channels = list_notification_channels()
    return {"channels": channels, "total": len(channels)}


@router.put("/{channel_name:path}")
async def api_update_notification_channel(
    channel_name: str,
    payload: NotificationChannelUpdatePayload,
    user: CurrentUser = Depends(require_roles("admin")),
) -> dict:
    updated = update_notification_channel(
        channel_name,
        enabled=payload.enabled,
        target=payload.target,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="通知渠道不存在")
    write_audit_log(
        actor=user,
        action="notification.update",
        resource_type="notification_channel",
        resource_id=channel_name,
        detail={"enabled": payload.enabled, "target": payload.target},
    )
    return {"channel": updated}


@router.post("/{channel_name:path}/test")
async def api_test_notification_channel(
    channel_name: str,
    user: CurrentUser = Depends(require_roles("admin")),
) -> dict:
    result = test_notification_channel(channel_name)
    if result is None:
        raise HTTPException(status_code=404, detail="通知渠道不存在")
    write_audit_log(
        actor=user,
        action="notification.test",
        resource_type="notification_channel",
        resource_id=channel_name,
    )
    return result
