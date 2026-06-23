from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from backend.app.db.session import get_connection
from backend.app.services.analysis_service import AnalysisService


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class TaskService:
    def create_analysis_task(self) -> str:
        task_id = f"task_{uuid.uuid4().hex}"
        now = _now()
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO analysis_tasks (task_id, status, started_at)
                VALUES (?, ?, ?)
                """,
                (task_id, "queued", now),
            )
        return task_id

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM analysis_tasks
                WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()
        return dict(row) if row else None

    def _mark_running(self, task_id: str) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE analysis_tasks
                SET status = ?, started_at = ?
                WHERE task_id = ?
                """,
                ("running", _now(), task_id),
            )

    def _mark_success(self, task_id: str, event_id: str | None) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE analysis_tasks
                SET status = ?, event_id = ?, finished_at = ?
                WHERE task_id = ?
                """,
                ("success", event_id, _now(), task_id),
            )

    def _mark_failed(self, task_id: str, error_message: str) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE analysis_tasks
                SET status = ?, error_message = ?, finished_at = ?
                WHERE task_id = ?
                """,
                ("failed", error_message[:2000], _now(), task_id),
            )

    async def run_analysis_task(self, task_id: str, text: str) -> None:
        self._mark_running(task_id)
        try:
            result = await AnalysisService().analyze(text)
            self._mark_success(task_id, result.get("event_id"))
        except Exception as exc:
            self._mark_failed(task_id, str(exc))
            raise
