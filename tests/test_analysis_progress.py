from __future__ import annotations

import pytest
from fastapi import BackgroundTasks

from backend.app.api.routes_analysis import create_analysis_task
from backend.app.core.security import CurrentUser
from backend.app.schemas.analysis import AnalyzeRequest
from backend.app.services import analysis_service, task_service
from backend.app.services.analysis_service import AnalysisService
from pipeline_progress import (
    PipelineProgress,
    ProgressCallback,
    pipeline_progress,
)
from backend.app.services.task_service import TaskService


def test_created_analysis_task_exposes_initial_pipeline_stage() -> None:
    service = TaskService()

    task_id = service.create_analysis_task()

    task = service.get_task(task_id)
    assert task is not None
    assert task["status"] == "queued"
    assert task["stage_key"] == "queued"
    assert task["stage_label"] == "等待分析"
    assert task["stage_index"] == 0
    assert task["stage_total"] > 0
    assert task["stage_detail"]


class FakeBackgroundTasks(BackgroundTasks):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[object, tuple[object, ...]]] = []

    def add_task(self, fn: object, *args: object) -> None:
        self.calls.append((fn, args))


@pytest.mark.asyncio
async def test_create_analysis_task_response_includes_pipeline_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTH_ENABLED", "false")
    background_tasks = FakeBackgroundTasks()

    response = await create_analysis_task(
        AnalyzeRequest(text="客户 P102 疑似高危交易"),
        background_tasks,
        CurrentUser(username="dev", role="admin"),
    )

    assert response["status"] == "queued"
    assert response["stage_key"] == "queued"
    assert response["stage_label"] == "等待分析"
    assert len(background_tasks.calls) == 1


@pytest.mark.asyncio
async def test_task_progress_callback_updates_visible_task_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = TaskService()
    task_id = service.create_analysis_task()
    observed_stages: list[str] = []

    class FakeAnalysisService:
        async def analyze(
            self,
            text: str,
            progress_callback: ProgressCallback | None = None,
        ) -> dict[str, str]:
            assert text == "客户 P102 疑似高危交易"
            assert progress_callback is not None
            progress_callback(
                pipeline_progress(
                    "single_graph",
                    "单条构图",
                    4,
                    "正在写入事件图谱",
                )
            )
            current = service.get_task(task_id)
            assert current is not None
            observed_stages.append(str(current["stage_key"]))
            return {"event_id": "E-PROGRESS"}

    monkeypatch.setattr(task_service, "AnalysisService", FakeAnalysisService)

    await service.run_analysis_task(task_id, "客户 P102 疑似高危交易")

    task = service.get_task(task_id)
    assert observed_stages == ["single_graph"]
    assert task is not None
    assert task["status"] == "success"
    assert task["event_id"] == "E-PROGRESS"
    assert task["stage_key"] == "complete"
    assert task["stage_label"] == "完成"
    assert task["stage_index"] == task["stage_total"]


@pytest.mark.asyncio
async def test_analysis_service_passes_progress_callback_to_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received_callbacks: list[object] = []

    async def fake_process_message_detailed(
        text: str,
        config: dict,
        progress_callback: object = None,
    ) -> dict[str, str]:
        received_callbacks.append(progress_callback)
        return {"event_id": "E001", "status": "analyzed", "raw_content": text}

    def progress_callback(progress: PipelineProgress) -> None:
        assert progress.stage_key
        assert progress.stage_label
        assert progress.stage_index <= progress.stage_total
        assert progress.stage_detail

    monkeypatch.setattr(
        analysis_service,
        "process_message_detailed",
        fake_process_message_detailed,
    )

    result = await AnalysisService().analyze(
        "客户 P102 疑似高危交易",
        progress_callback=progress_callback,
    )

    assert result["event_id"] == "E001"
    assert received_callbacks == [progress_callback]
