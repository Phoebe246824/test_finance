from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.app.core.security import CurrentUser, require_roles
from backend.app.db.session import get_connection
from backend.app.repositories.events import EventRepository
from backend.app.services.audit_service import write_audit_log

router = APIRouter(prefix="/api/events", tags=["events"])


class ReviewActionCreate(BaseModel):
    action_type: str = Field(..., min_length=1)
    comment: str = ""


@router.get("")
async def list_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    risk_level: str | None = None,
    keyword: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    return EventRepository().list_events(
        page=page,
        page_size=page_size,
        risk_level=risk_level,
        keyword=keyword,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/{event_id}")
async def get_event(event_id: str) -> dict:
    event = EventRepository().get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM review_actions WHERE event_id = ? ORDER BY created_at DESC",
            (event_id,),
        ).fetchall()
    event["review_actions"] = [dict(row) for row in rows]
    return event


@router.delete("/{event_id}")
async def delete_event(
    event_id: str,
    user: CurrentUser = Depends(require_roles("admin")),
) -> dict:
    deleted = EventRepository().delete_event(event_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="event not found")
    write_audit_log(
        actor=user,
        action="event.delete",
        resource_type="event",
        resource_id=event_id,
    )
    return {"deleted": True, "event_id": event_id}


@router.post("/{event_id}/review-actions")
async def create_review_action(
    event_id: str,
    payload: ReviewActionCreate,
    user: CurrentUser = Depends(require_roles("admin", "reviewer")),
) -> dict:
    event = EventRepository().get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")
    created_at = datetime.now().isoformat(timespec="seconds")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO review_actions (event_id, action_type, comment, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (event_id, payload.action_type, payload.comment, created_at),
        )
    write_audit_log(
        actor=user,
        action="event.review",
        resource_type="event",
        resource_id=event_id,
        detail={"action_type": payload.action_type, "comment": payload.comment},
    )
    return {
        "created": True,
        "event_id": event_id,
        "action_type": payload.action_type,
        "created_at": created_at,
    }
