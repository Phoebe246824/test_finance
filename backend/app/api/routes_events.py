from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.app.core.security import CurrentUser, require_roles
from backend.app.repositories.events import EventRepository
from backend.app.services import store_provider
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
    stores = store_provider.get_store_bundle()
    event = stores.events.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")
    event["review_actions"] = stores.review_actions.list_for_event(event_id)
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
    stores = store_provider.get_store_bundle()
    if stores.events.get_event(event_id) is None:
        raise HTTPException(status_code=404, detail="event not found")
    row = stores.review_actions.create(event_id, payload.action_type, payload.comment)
    write_audit_log(
        actor=user,
        action="event.review",
        resource_type="event",
        resource_id=event_id,
        detail={"action_type": payload.action_type, "comment": payload.comment},
    )
    return {"created": True, **row}
