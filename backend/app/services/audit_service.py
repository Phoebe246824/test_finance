from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from backend.app.core.security import CurrentUser
from backend.app.services.runtime_state import runtime_state


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
    runtime_state.append_audit_log(
        {
            "actor": actor.username,
            "role": actor.role,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "detail": detail or {},
            "detail_json": json.dumps(detail or {}, ensure_ascii=False),
            "created_at": _now(),
        }
    )
