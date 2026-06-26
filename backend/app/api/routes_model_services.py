from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.app.core.security import CurrentUser, require_roles
from backend.app.services.audit_service import write_audit_log
from backend.app.services.settings_response import mask_model_service_api_key
from backend.app.services.settings_service import (
    add_model_service,
    delete_model_service,
    get_model_service,
    list_model_services,
    test_model_endpoint,
    update_model_service,
    update_model_service_status,
)

router = APIRouter(prefix="/api/model-services", tags=["model-services"])


def _public_model_service(service: dict) -> dict:
    public_service = dict(service)
    api_key = public_service.get("apiKey")
    if isinstance(api_key, str):
        public_service["apiKey"] = mask_model_service_api_key(api_key)
    return public_service


def _preserved_model_service_api_key(
    current_service: dict | None,
    submitted_api_key: str,
) -> str:
    if current_service is None:
        return submitted_api_key
    current_api_key = current_service.get("apiKey")
    if not isinstance(current_api_key, str):
        return submitted_api_key
    if submitted_api_key == mask_model_service_api_key(current_api_key):
        return current_api_key
    return submitted_api_key


class ModelServiceCreatePayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    type: str = Field(..., min_length=1, max_length=64)
    deployment: str = Field(default="本地部署", max_length=64)
    endpoint: str = Field(..., min_length=1, max_length=512)
    apiKey: str = Field(default="", max_length=512)
    status: str = Field(default="未验证", max_length=32)
    default: bool = Field(default=False)


class ModelServiceUpdatePayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    type: str = Field(..., min_length=1, max_length=64)
    deployment: str = Field(default="本地部署", max_length=64)
    endpoint: str = Field(..., min_length=1, max_length=512)
    apiKey: str = Field(default="", max_length=512)
    default: bool = Field(default=False)


class ModelServiceTestPayload(BaseModel):
    endpoint: str = Field(..., min_length=1, max_length=512)
    type: str = Field(default="大语言模型", min_length=1, max_length=64)
    apiKey: str = Field(default="", max_length=512)


@router.get("")
async def api_list_model_services(
    _: CurrentUser = Depends(require_roles("admin")),
) -> dict:
    services = list_model_services()
    public_services = [_public_model_service(service) for service in services]
    return {"services": public_services, "total": len(public_services)}


@router.post("")
async def api_create_model_service(
    payload: ModelServiceCreatePayload,
    user: CurrentUser = Depends(require_roles("admin")),
) -> dict:
    try:
        created = add_model_service(
            name=payload.name,
            type=payload.type,
            deployment=payload.deployment,
            endpoint=payload.endpoint,
            api_key=payload.apiKey,
            status=payload.status,
            default=payload.default,
        )
    except ValueError as exc:
        status_code = 409 if "已存在" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    write_audit_log(
        actor=user,
        action="model_service.create",
        resource_type="model_service",
        resource_id=payload.name,
    )
    return {"service": _public_model_service(created)}


@router.post("/test")
async def api_test_model_service(
    payload: ModelServiceTestPayload,
    _: CurrentUser = Depends(require_roles("admin")),
) -> dict:
    return await test_model_endpoint(payload.endpoint, payload.type, payload.apiKey)


@router.post("/{service_name:path}/test")
async def api_test_saved_model_service(
    service_name: str,
    _: CurrentUser = Depends(require_roles("admin")),
) -> dict:
    service = get_model_service(service_name)
    if service is None:
        raise HTTPException(status_code=404, detail="模型服务不存在")
    result = await test_model_endpoint(
        str(service.get("endpoint") or ""),
        str(service.get("type") or "大语言模型"),
        str(service.get("apiKey") or ""),
    )
    updated = update_model_service_status(
        service_name,
        status="运行中" if result.get("success") else "异常",
    )
    return {"result": result, "service": _public_model_service(updated or service)}


@router.put("/{service_name:path}")
async def api_update_model_service(
    service_name: str,
    payload: ModelServiceUpdatePayload,
    user: CurrentUser = Depends(require_roles("admin")),
) -> dict:
    current_service = get_model_service(service_name)
    try:
        updated = update_model_service(
            service_name,
            name=payload.name,
            type=payload.type,
            deployment=payload.deployment,
            endpoint=payload.endpoint,
            api_key=_preserved_model_service_api_key(current_service, payload.apiKey),
            default=payload.default,
        )
    except ValueError as exc:
        status_code = 409 if "已存在" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="模型服务不存在")
    write_audit_log(
        actor=user,
        action="model_service.update",
        resource_type="model_service",
        resource_id=service_name,
    )
    return {"service": _public_model_service(updated)}


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
