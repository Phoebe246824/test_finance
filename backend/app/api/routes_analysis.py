from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sse_starlette import EventSourceResponse

from backend.app.core.config import settings
from backend.app.core.security import (
    CurrentUser,
    _user_from_token,
    get_current_user,
    require_roles,
)
from backend.app.schemas.analysis import AnalyzeRequest, AnalyzeResponse
from backend.app.services.analysis_service import AnalysisService
from backend.app.services.audit_service import write_audit_log
from backend.app.services.runtime_state import runtime_state
from backend.app.services.task_service import TaskService
from scripts.finance_demo_cases import FINANCE_CASES

router = APIRouter(prefix="/api", tags=["analysis"])


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    payload: AnalyzeRequest,
    user: CurrentUser = Depends(require_roles("admin", "reviewer")),
) -> dict:
    result = await AnalysisService().analyze(payload.text)
    write_audit_log(
        actor=user,
        action="analysis.sync",
        resource_type="event",
        resource_id=result.get("event_id"),
        detail={"text_length": len(payload.text)},
    )
    return result


@router.post("/tasks/analyze")
async def create_analysis_task(
    payload: AnalyzeRequest,
    background_tasks: BackgroundTasks,
    user: CurrentUser = Depends(require_roles("admin", "reviewer")),
) -> dict:
    service = TaskService()
    task_id = service.create_analysis_task()
    background_tasks.add_task(service.run_analysis_task, task_id, payload.text)
    write_audit_log(
        actor=user,
        action="analysis.enqueue",
        resource_type="analysis_task",
        resource_id=task_id,
        detail={"text_length": len(payload.text)},
    )
    return service.get_task(task_id)


@router.get("/tasks/{task_id}")
async def get_analysis_task(
    task_id: str,
    _: CurrentUser = Depends(get_current_user),
) -> dict:
    task = TaskService().get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task


@router.get("/tasks/{task_id}/stream")
async def stream_task(
    task_id: str,
    request: Request,
    token: str | None = None,
) -> EventSourceResponse:
    """SSE endpoint for task progress streaming.

    Note: EventSource API does not support custom headers, so auth token
    is passed as query parameter. This means the token may appear in
    server logs, browser history, and proxy records. For production use,
    consider short-lived stream tokens or cookie-based auth.
    """
    if settings.auth_enabled:
        user = _user_from_token(token)
        if user is None:
            raise HTTPException(status_code=401, detail="missing or invalid token")

    task = runtime_state.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")

    async def generate():
        q = runtime_state.subscribe_task(task_id)
        try:
            if runtime_state.get_task(task_id) is None:
                q.put_nowait(None)
                return
            while True:
                if await request.is_disconnected():
                    break
                try:
                    snapshot = await asyncio.wait_for(q.get(), timeout=30)
                except asyncio.TimeoutError:
                    if await request.is_disconnected():
                        break
                    task = runtime_state.get_task(task_id)
                    if task is None:
                        break
                    yield {"event": "update", "data": json.dumps(task)}
                    continue
                if snapshot is None:
                    break
                yield {"event": "update", "data": json.dumps(snapshot)}
                if snapshot.get("status") in ("success", "failed"):
                    break
        except asyncio.CancelledError:
            pass
        finally:
            runtime_state.unsubscribe_task(task_id, q)

    return EventSourceResponse(generate(), ping=15, send_timeout=30)


@router.get("/demo-cases")
async def demo_cases() -> dict:
    return {
        "items": [
            {
                "id": case["id"],
                "title": case["title"],
                "text": case["text"],
                "expect": case.get("expect", []),
            }
            for case in FINANCE_CASES
        ]
    }
