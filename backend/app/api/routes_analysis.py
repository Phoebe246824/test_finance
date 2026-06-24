from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from backend.app.schemas.analysis import AnalyzeRequest, AnalyzeResponse
from backend.app.core.security import CurrentUser, get_current_user, require_roles
from backend.app.services.audit_service import write_audit_log
from backend.app.services.analysis_service import AnalysisService
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
    return {"task_id": task_id, "status": "queued"}


@router.get("/tasks/{task_id}")
async def get_analysis_task(
    task_id: str,
    _: CurrentUser = Depends(get_current_user),
) -> dict:
    task = TaskService().get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task


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
