from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.app.core.config import settings


@dataclass(frozen=True)
class CurrentUser:
    username: str
    role: str


bearer = HTTPBearer(auto_error=False)


def _user_from_token(token: str | None) -> CurrentUser | None:
    if token == settings.admin_token:
        return CurrentUser(username="admin", role="admin")
    if token == settings.reviewer_token:
        return CurrentUser(username="reviewer", role="reviewer")
    return None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> CurrentUser:
    if not settings.auth_enabled:
        return CurrentUser(username="dev", role="admin")
    user = _user_from_token(credentials.credentials if credentials else None)
    if user is None:
        raise HTTPException(status_code=401, detail="missing or invalid token")
    return user


def require_roles(*roles: str):
    async def _dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="insufficient permissions")
        return user

    return _dependency
