from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.app.repositories.events import EventRepository

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("")
async def list_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    risk_level: str | None = None,
    keyword: str | None = None,
) -> dict:
    return EventRepository().list_events(
        page=page,
        page_size=page_size,
        risk_level=risk_level,
        keyword=keyword,
    )


@router.get("/{event_id}")
async def get_event(event_id: str) -> dict:
    event = EventRepository().get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")
    return event


@router.delete("/{event_id}")
async def delete_event(event_id: str) -> dict:
    deleted = EventRepository().delete_event(event_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="event not found")
    return {"deleted": True, "event_id": event_id}
