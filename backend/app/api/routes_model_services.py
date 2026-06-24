from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.app.core.security import CurrentUser, require_roles
from backend.app.services.audit_service import write_audit_log
from backend.app.services.settings_service import (
    add_model_service,
    delete_model_service,
    list_model_services,
    update_model_service,
    list_notification_channels,
    update_notification_channel,
    test_notification_channel,
)

router = APIRouter(prefix="/api/model-services", tags=["model-services"])


class ModelServiceCreatePayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    type: str = Field(..., min_length=1, max_length=64)
    deployment: str = Field(default="本地部署", max_length=64)
    endpoint: str = Field(..., min_length=1, max_length=512)
    status: str = Field(default="未运行", max_length=32)
    default: bool = Field(default=False)


class ModelServiceUpdatePayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    type: str = Field(..., min_length=1, max_length=64)
    deployment: str = Field(default="本地部署", max_length=64)
    endpoint: str = Field(..., min_length=1, max_length=512)
    default: bool = Field(default=False)


@router.get("")
async def api_list_model_services(
    _: CurrentUser = Depends(require_roles("admin")),
) -> dict:
    services = list_model_services()
    return {"services": services, "total": len(services)}


@router.post("")
async def api_create_model_service(
    payload: ModelServiceCreatePayload,
    user: CurrentUser = Depends(require_roles("admin")),
) -> dict:
    created = add_model_service(
        name=payload.name,
        type=payload.type,
        deployment=payload.deployment,
        endpoint=payload.endpoint,
        status=payload.status,
        default=payload.default,
    )
    write_audit_log(
        actor=user,
        action="model_service.create",
        resource_type="model_service",
        resource_id=payload.name,
    )
    return {"service": created}


@router.put("/{service_name:path}")
async def api_update_model_service(
    service_name: str,
    payload: ModelServiceUpdatePayload,
    user: CurrentUser = Depends(require_roles("admin")),
) -> dict:
    updated = update_model_service(
        service_name,
        name=payload.name,
        type=payload.type,
        deployment=payload.deployment,
        endpoint=payload.endpoint,
        default=payload.default,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="模型服务不存在")
    write_audit_log(
        actor=user,
        action="model_service.update",
        resource_type="model_service",
        resource_id=service_name,
    )
    return {"service": updated}


@router.delete("/{service_name:path}")
async def api_delete_model_service(
    service_name: str,
    user: CurrentUser = Depends(require_roles("admin")),
) -> dict:
    deleted = delete_model_service(service_name)
    if not deleted:
        raise HTTPException(status_code=404, detail="模型服务不存在")
    write_audit_log(
        actor=user,
        action="model_service.delete",
        resource_type="model_service",
        resource_id=service_name,
    )
    return {"deleted": True, "name": service_name}
