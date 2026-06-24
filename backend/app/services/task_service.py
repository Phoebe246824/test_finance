from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, TypedDict

from pipeline_progress import (
    PIPELINE_STAGE_TOTAL,
    PipelineProgress,
    ProgressCallback,
    pipeline_progress,
)

from backend.app.services.analysis_service import AnalysisService
from backend.app.services.runtime_state import runtime_state


class AnalysisResult(TypedDict, total=False):
    event_id: str | None
    status: str


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
                **pipeline_progress(
                    "queued",
                    "等待分析",
                    0,
                    "任务已进入队列，等待后端执行流水线",
                ).as_task_values(),
                "stage_updated_at": now,
            },
        )
        return task_id

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        return runtime_state.get_task(task_id)

    def _mark_running(self, task_id: str) -> None:
        now = _now()
        runtime_state.update_task(
            task_id,
            {
                "status": "running",
                "started_at": now,
                **pipeline_progress(
                    "running",
                    "准备分析",
                    0,
                    "后端任务已启动，正在准备流水线配置",
                ).as_task_values(),
                "stage_updated_at": now,
            },
        )

    def _update_progress(
        self,
        task_id: str,
        progress: PipelineProgress,
    ) -> None:
        runtime_state.update_task(
            task_id,
            {
                **progress.as_task_values(),
                "stage_updated_at": _now(),
            },
        )

    def _success_progress(self, task_id: str, result: AnalysisResult) -> PipelineProgress:
        task = runtime_state.get_task(task_id) or {}
        if result.get("status") == "stashed":
            stage_key = str(task.get("stage_key") or "")
            return PipelineProgress(
                stage_key="stash",
                stage_label="事件暂存",
                stage_index=int(task.get("stage_index") if stage_key == "stash" else 3),
                stage_total=PIPELINE_STAGE_TOTAL,
                stage_detail=str(
                    task.get("stage_detail")
                    if stage_key == "stash"
                    else "事件已暂存，等待后续高危事件回捞"
                ),
            )
        return pipeline_progress(
            "complete",
            "完成",
            PIPELINE_STAGE_TOTAL,
            "事件处理流水线已完成",
        )

    def _mark_success(self, task_id: str, result: AnalysisResult) -> None:
        now = _now()
        runtime_state.update_task(
            task_id,
            {
                "status": "success",
                "event_id": result.get("event_id"),
                "finished_at": now,
                **self._success_progress(task_id, result).as_task_values(),
                "stage_updated_at": now,
            },
        )

    def _mark_failed(self, task_id: str, error_message: str) -> None:
        task = runtime_state.get_task(task_id) or {}
        stage_index = int(task.get("stage_index") or 0)
        now = _now()
        runtime_state.update_task(
            task_id,
            {
                "status": "failed",
                "error_message": error_message[:2000],
                "finished_at": now,
                **PipelineProgress(
                    stage_key="failed",
                    stage_label="分析失败",
                    stage_index=stage_index,
                    stage_total=PIPELINE_STAGE_TOTAL,
                    stage_detail=error_message[:200],
                ).as_task_values(),
                "stage_updated_at": now,
            },
        )

    def _progress_callback(self, task_id: str) -> ProgressCallback:
        def update(progress: PipelineProgress) -> None:
            self._update_progress(task_id, progress)

        return update

    async def run_analysis_task(self, task_id: str, text: str) -> None:
        self._mark_running(task_id)
        try:
            result = await AnalysisService().analyze(
                text,
                progress_callback=self._progress_callback(task_id),
            )
            self._mark_success(task_id, result)
        except Exception as exc:
            self._mark_failed(task_id, str(exc))
            raise
