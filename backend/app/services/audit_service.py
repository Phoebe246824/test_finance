from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from backend.app.core.security import CurrentUser
from backend.app.db.session import get_connection


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def write_audit_log(
    *,
    actor: CurrentUser,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO audit_logs (
                actor, role, action, resource_type, resource_id, detail_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                actor.username,
                actor.role,
                action,
                resource_type,
                resource_id,
                json.dumps(detail or {}, ensure_ascii=False),
                _now(),
            ),
        )
