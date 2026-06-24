from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.app.core.config import settings
from backend.app.core.security import CurrentUser, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    token: str = Field(..., min_length=1)


@router.post("/login")
async def login(payload: LoginRequest) -> dict:
    if not settings.auth_enabled:
        return {"access_token": payload.token, "username": "dev", "role": "admin"}
    if payload.token == settings.admin_token:
        return {"access_token": payload.token, "username": "admin", "role": "admin"}
    if payload.token == settings.reviewer_token:
        return {"access_token": payload.token, "username": "reviewer", "role": "reviewer"}
    raise HTTPException(status_code=401, detail="invalid token")


@router.get("/me")
async def me(user: CurrentUser = Depends(get_current_user)) -> dict:
    return {"username": user.username, "role": user.role}
