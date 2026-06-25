from __future__ import annotations

from typing import Any

from pymilvus.exceptions import MilvusException

from backend.app.core.security import CurrentUser
from backend.app.services import store_provider
from backend.app.services.audit_service import write_audit_log


def apply_data_management_settings(
    *,
    data_management: dict,
    actor: CurrentUser,
) -> dict[str, int | bool | str]:
    retention_days = int(data_management.get("retentionDays") or 180)
    try:
        stores = store_provider.get_store_bundle()
        deleted = stores.events.cleanup_expired(
            graph_built_retention_days=retention_days,
        )
    except RuntimeError as exc:
        _write_cleanup_failed_log(actor, retention_days, exc)
        return {"enabled": True, "deleted": 0, "status": "failed"}
    except OSError as exc:
        _write_cleanup_failed_log(actor, retention_days, exc)
        return {"enabled": True, "deleted": 0, "status": "failed"}
    except MilvusException as exc:
        _write_cleanup_failed_log(actor, retention_days, exc)
        return {"enabled": True, "deleted": 0, "status": "failed"}
    write_audit_log(
        actor=actor,
        action="data_management.cleanup",
        resource_type="events",
        resource_id="expired",
        detail={"retentionDays": retention_days, "deleted": deleted},
    )
    return {"enabled": True, "deleted": deleted, "status": "completed"}


def _write_cleanup_failed_log(
    actor: CurrentUser,
    retention_days: int,
    exc: Any,
) -> None:
    write_audit_log(
        actor=actor,
        action="data_management.cleanup_failed",
        resource_type="events",
        resource_id="expired",
        detail={"retentionDays": retention_days, "error": str(exc)[:200]},
    )
