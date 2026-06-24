from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from backend.app.services.analysis_service import AnalysisService
from backend.app.services.runtime_state import runtime_state


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class TaskService:
    def create_analysis_task(self) -> str:
        task_id = f"task_{uuid.uuid4().hex}"
        now = _now()
        runtime_state.create_task(
            task_id,
            {
                "task_id": task_id,
                "status": "queued",
                "event_id": None,
                "error_message": "",
                "started_at": now,
                "finished_at": "",
            },
        )
        return task_id

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        return runtime_state.get_task(task_id)

    def _mark_running(self, task_id: str) -> None:
        runtime_state.update_task(task_id, {"status": "running", "started_at": _now()})

    def _mark_success(self, task_id: str, event_id: str | None) -> None:
        runtime_state.update_task(
            task_id,
            {"status": "success", "event_id": event_id, "finished_at": _now()},
        )

    def _mark_failed(self, task_id: str, error_message: str) -> None:
        runtime_state.update_task(
            task_id,
            {
                "status": "failed",
                "error_message": error_message[:2000],
                "finished_at": _now(),
            },
        )

    async def run_analysis_task(self, task_id: str, text: str) -> None:
        self._mark_running(task_id)
        try:
            result = await AnalysisService().analyze(text)
            self._mark_success(task_id, result.get("event_id"))
        except Exception as exc:
            self._mark_failed(task_id, str(exc))
            raise
