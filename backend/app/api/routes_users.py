from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.app.core.security import CurrentUser, require_roles
from backend.app.services.audit_service import write_audit_log
from backend.app.services.settings_service import (
    add_user,
    delete_user,
    get_user,
    list_users,
    reset_user_password,
    update_user,
    toggle_user_status,
)

router = APIRouter(prefix="/api/users", tags=["users"])


class UserCreatePayload(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    role: str = Field(..., min_length=1, max_length=64)
    status: str = Field(default="启用", max_length=32)
    password: str = Field(default="", max_length=128)


class UserUpdatePayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    role: str = Field(..., min_length=1, max_length=64)


class PasswordResetPayload(BaseModel):
    new_password: str = Field(..., min_length=4, max_length=128)


@router.get("")
async def api_list_users(
    _: CurrentUser = Depends(require_roles("admin")),
) -> dict:
    users = list_users()
    return {"users": users, "total": len(users)}


@router.get("/{username}")
async def api_get_user(
    username: str,
    _: CurrentUser = Depends(require_roles("admin")),
) -> dict:
    user = get_user(username)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"user": user}


@router.post("")
async def api_create_user(
    payload: UserCreatePayload,
    user: CurrentUser = Depends(require_roles("admin")),
) -> dict:
    created = add_user(
        username=payload.username,
        name=payload.name,
        role=payload.role,
        status=payload.status,
        password=payload.password,
    )
    write_audit_log(
        actor=user,
        action="user.create",
        resource_type="user",
        resource_id=payload.username,
        detail={"name": payload.name, "role": payload.role},
    )
    return {"user": created}


@router.put("/{username}")
async def api_update_user(
    username: str,
    payload: UserUpdatePayload,
    user: CurrentUser = Depends(require_roles("admin")),
) -> dict:
    updated = update_user(username, name=payload.name, role=payload.role)
    if updated is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    write_audit_log(
        actor=user,
        action="user.update",
        resource_type="user",
        resource_id=username,
        detail={"name": payload.name, "role": payload.role},
    )
    return {"user": updated}


@router.delete("/{username}")
async def api_delete_user(
    username: str,
    user: CurrentUser = Depends(require_roles("admin")),
) -> dict:
    deleted = delete_user(username)
    if not deleted:
        raise HTTPException(status_code=404, detail="用户不存在")
    write_audit_log(
        actor=user,
        action="user.delete",
        resource_type="user",
        resource_id=username,
    )
    return {"deleted": True, "username": username}


@router.post("/{username}/reset-password")
async def api_reset_password(
    username: str,
    payload: PasswordResetPayload,
    user: CurrentUser = Depends(require_roles("admin")),
) -> dict:
    updated = reset_user_password(username, payload.new_password)
    if updated is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    write_audit_log(
        actor=user,
        action="user.reset_password",
        resource_type="user",
        resource_id=username,
    )
    return {"user": updated}


@router.post("/{username}/toggle-status")
async def api_toggle_status(
    username: str,
    user: CurrentUser = Depends(require_roles("admin")),
) -> dict:
    updated = toggle_user_status(username)
    if updated is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    write_audit_log(
        actor=user,
        action="user.toggle_status",
        resource_type="user",
        resource_id=username,
        detail={"new_status": updated.get("status")},
    )
    return {"user": updated}
