from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.app.core.security import CurrentUser, require_roles
from backend.app.services.audit_service import write_audit_log
from backend.app.services.settings_service import load_app_settings, save_app_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


class AppSettingsPayload(BaseModel):
    system_config: dict[str, Any] = Field(default_factory=dict)
    model_params: dict[str, Any] = Field(default_factory=dict)
    model_services: list[dict[str, Any]] = Field(default_factory=list)
    users: list[dict[str, Any]] = Field(default_factory=list)
    data_management: dict[str, Any] = Field(default_factory=dict)
    notification_channels: list[dict[str, Any]] = Field(default_factory=list)
    notification_events: list[str] = Field(default_factory=list)


@router.get("")
async def get_settings() -> dict:
    settings, updated_at = load_app_settings()
    return {"settings": settings, "updated_at": updated_at}


@router.put("")
async def update_settings(
    payload: AppSettingsPayload,
    user: CurrentUser = Depends(require_roles("admin")),
) -> dict:
    settings, updated_at = save_app_settings(payload.model_dump())
    write_audit_log(
        actor=user,
        action="settings.update",
        resource_type="app_settings",
        resource_id="default",
        detail={"updated_at": updated_at},
    )
    return {"settings": settings, "updated_at": updated_at}
