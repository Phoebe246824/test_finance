from __future__ import annotations

from typing import TypeAlias

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.core.security import CurrentUser, require_roles
from backend.app.services.audit_service import write_audit_log
from backend.app.services.data_management_service import apply_data_management_settings
from backend.app.services.settings_response import (
    preserve_masked_runtime_secrets,
    public_settings_response,
)
from backend.app.services.settings_runtime_catalog import is_list_env, load_env_catalog
from backend.app.services.settings_runtime_values import field_scalar_type
from backend.app.services.settings_service import (
    load_app_settings,
    save_app_settings,
    update_settings_section,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])

RuntimeConfigValue: TypeAlias = bool | int | float | str | list[str]


def _runtime_catalog() -> dict[str, str]:
    return {field.env: field_scalar_type(field) for field in load_env_catalog()}


def _runtime_type_matches(env: str, scalar_type: str, value: RuntimeConfigValue) -> bool:
    if is_list_env(env):
        return isinstance(value, list) and all(isinstance(item, str) for item in value)
    match scalar_type:
        case "bool":
            return isinstance(value, bool)
        case "int":
            return isinstance(value, int) and not isinstance(value, bool)
        case "float":
            return isinstance(value, (float, int)) and not isinstance(value, bool)
        case "string":
            return isinstance(value, str)
        case _:
            return False


def _settings_payload(settings: dict, updated_at: str) -> dict:
    return {
        "settings": public_settings_response(settings),
        "updated_at": updated_at,
    }


class ModelParamsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    maxTokens: int = Field(default=2048, gt=0, le=131072)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    topP: float = Field(default=0.9, ge=0.0, le=1.0)
    repetitionPenalty: float = Field(default=1.1, ge=0.0, le=2.0)
    timeout: int = Field(default=60, gt=0, le=3600)
    concurrency: int = Field(default=2, gt=0, le=128)


class SystemConfigPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="")
    description: str = Field(default="")
    timezone: str = Field(default="Asia/Shanghai (UTC+08:00)")
    dateFormat: str = Field(default="YYYY-MM-DD HH:mm:ss")
    language: str = Field(default="简体中文")


class ModelServicePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=128)
    type: str = Field(..., min_length=1, max_length=64)
    deployment: str = Field(default="本地部署", max_length=64)
    endpoint: str = Field(..., min_length=1, max_length=512)
    status: str = Field(default="未验证", max_length=32)
    default: bool = Field(default=False)
    updatedAt: str = Field(default="", max_length=64)
    pendingDefault: bool = Field(default=False)


class UserPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(default="", max_length=128)
    name: str = Field(default="", max_length=128)
    role: str = Field(default="", max_length=64)
    status: str = Field(default="", max_length=32)
    lastLogin: str = Field(default="", max_length=64)


class DataSummaryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(default="", max_length=64)
    value: str = Field(default="", max_length=64)


class DataManagementPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: list[DataSummaryPayload] = Field(default_factory=list)
    retentionDays: int = Field(default=180, ge=1, le=3650)


class NotificationChannelPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=64)
    enabled: bool = Field(default=True)
    target: str = Field(..., min_length=1, max_length=512)


class RuntimeMetadataPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    env: str = Field(..., min_length=1)
    group: str = Field(..., min_length=1)
    key_path: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    help: str = Field(default="")
    scalar_type: str = Field(..., min_length=1)
    default: RuntimeConfigValue
    secret: bool
    editable: bool
    effective_scope: str = Field(..., min_length=1)


class AppSettingsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system_config: SystemConfigPayload = Field(default_factory=SystemConfigPayload)
    model_params: ModelParamsPayload = Field(default_factory=ModelParamsPayload)
    model_services: list[ModelServicePayload] = Field(default_factory=list)
    users: list[UserPayload] = Field(default_factory=list)
    data_management: DataManagementPayload = Field(default_factory=DataManagementPayload)
    notification_channels: list[NotificationChannelPayload] = Field(default_factory=list)
    notification_events: list[str] = Field(default_factory=list)
    runtime_config: dict[str, RuntimeConfigValue] | None = Field(default=None)
    runtime_config_metadata: list[RuntimeMetadataPayload] | None = Field(default=None)

    @field_validator("runtime_config")
    @classmethod
    def validate_runtime_config(
        cls,
        runtime_config: dict[str, RuntimeConfigValue] | None,
    ) -> dict[str, RuntimeConfigValue] | None:
        if runtime_config is None:
            return None
        catalog = _runtime_catalog()
        for env, value in runtime_config.items():
            scalar_type = catalog.get(env)
            if scalar_type is None:
                raise ValueError(f"Unsupported runtime config key: {env}")
            if not _runtime_type_matches(env, scalar_type, value):
                raise ValueError(f"Invalid runtime config value type for {env}")
        return runtime_config


@router.get("")
async def get_settings(
    _: CurrentUser = Depends(require_roles("admin")),
) -> dict:
    settings, updated_at = load_app_settings()
    return _settings_payload(settings, updated_at)


@router.put("")
async def update_settings(
    payload: AppSettingsPayload,
    user: CurrentUser = Depends(require_roles("admin")),
) -> dict:
    previous, _ = load_app_settings()
    payload_dict = payload.model_dump()
    if payload.runtime_config is None:
        payload_dict.pop("runtime_config", None)
    if payload.runtime_config_metadata is None:
        payload_dict.pop("runtime_config_metadata", None)
    payload_dict = preserve_masked_runtime_secrets(payload_dict, previous)
    try:
        settings, updated_at = save_app_settings(payload_dict)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    write_audit_log(
        actor=user,
        action="settings.update",
        resource_type="app_settings",
        resource_id="default",
        detail={
            "updated_at": updated_at,
            "data_management_changed": payload_dict["data_management"]
            != previous.get("data_management"),
        },
    )
    return _settings_payload(settings, updated_at)


@router.put("/system-config")
async def update_system_config(
    payload: SystemConfigPayload,
    user: CurrentUser = Depends(require_roles("admin")),
) -> dict:
    settings, updated_at = update_settings_section("system_config", payload.model_dump())
    write_audit_log(
        actor=user,
        action="settings.update.system_config",
        resource_type="app_settings",
        resource_id="system_config",
        detail={"updated_at": updated_at},
    )
    return _settings_payload(settings, updated_at)


@router.put("/model-params")
async def update_model_params(
    payload: ModelParamsPayload,
    user: CurrentUser = Depends(require_roles("admin")),
) -> dict:
    settings, updated_at = update_settings_section("model_params", payload.model_dump())
    write_audit_log(
        actor=user,
        action="settings.update.model_params",
        resource_type="app_settings",
        resource_id="model_params",
        detail={"updated_at": updated_at},
    )
    return _settings_payload(settings, updated_at)


@router.put("/data-management")
async def update_data_management(
    payload: DataManagementPayload,
    user: CurrentUser = Depends(require_roles("admin")),
) -> dict:
    settings, updated_at = update_settings_section("data_management", payload.model_dump())
    write_audit_log(
        actor=user,
        action="settings.update.data_management",
        resource_type="app_settings",
        resource_id="data_management",
        detail={"updated_at": updated_at},
    )
    return _settings_payload(settings, updated_at)


@router.put("/notification-events")
async def update_notification_events(
    notification_events: list[str],
    user: CurrentUser = Depends(require_roles("admin")),
) -> dict:
    settings, updated_at = update_settings_section("notification_events", notification_events)
    write_audit_log(
        actor=user,
        action="settings.update.notification_events",
        resource_type="app_settings",
        resource_id="notification_events",
        detail={"updated_at": updated_at},
    )
    return _settings_payload(settings, updated_at)


@router.post("/data-management/cleanup")
async def cleanup_data_management(
    user: CurrentUser = Depends(require_roles("admin")),
) -> dict:
    settings, _ = load_app_settings()
    result = apply_data_management_settings(
        data_management=settings["data_management"],
        actor=user,
    )
    return result
