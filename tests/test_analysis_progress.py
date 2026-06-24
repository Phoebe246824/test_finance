from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient

from backend.app.api.routes_analysis import create_analysis_task
from backend.app.core.security import CurrentUser
from backend.app.main import app
from backend.app.schemas.analysis import AnalyzeRequest
from backend.app.services import analysis_service, task_service
from backend.app.services.analysis_service import AnalysisService
from backend.app.services.runtime_state import runtime_state
from backend.app.services.task_service import TaskService
from pipeline_progress import (
    PipelineProgress,
    ProgressCallback,
    pipeline_progress,
)


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
async def test_stashed_task_keeps_stash_stage_as_final_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = TaskService()
    task_id = service.create_analysis_task()

    class FakeAnalysisService:
        async def analyze(
            self,
            text: str,
            progress_callback: ProgressCallback | None = None,
        ) -> dict[str, str]:
            assert progress_callback is not None
            progress_callback(
                pipeline_progress(
                    "stash",
                    "事件暂存",
                    3,
                    "未命中高危规则，正在暂存事件等待后续回捞",
                )
            )
            return {"event_id": "E-STASHED", "status": "stashed"}

    monkeypatch.setattr(task_service, "AnalysisService", FakeAnalysisService)

    await service.run_analysis_task(task_id, "客户 P102 日常工资入账")

    task = service.get_task(task_id)
    assert task is not None
    assert task["status"] == "success"
    assert task["event_id"] == "E-STASHED"
    assert task["stage_key"] == "stash"
    assert task["stage_label"] == "事件暂存"
    assert task["stage_index"] == 3
    assert "暂存" in task["stage_detail"]


@pytest.mark.asyncio
async def test_stashed_task_uses_stash_stage_even_without_progress_callback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = TaskService()
    task_id = service.create_analysis_task()

    class FakeAnalysisService:
        async def analyze(
            self,
            text: str,
            progress_callback: ProgressCallback | None = None,
        ) -> dict[str, str]:
            assert progress_callback is not None
            return {"event_id": "E-STASHED-NO-CALLBACK", "status": "stashed"}

    monkeypatch.setattr(task_service, "AnalysisService", FakeAnalysisService)

    await service.run_analysis_task(task_id, "客户 P102 日常工资入账")

    task = service.get_task(task_id)
    assert task is not None
    assert task["status"] == "success"
    assert task["event_id"] == "E-STASHED-NO-CALLBACK"
    assert task["stage_key"] == "stash"
    assert task["stage_label"] == "事件暂存"
    assert task["stage_index"] == 3


@pytest.mark.asyncio
async def test_failed_task_keeps_last_stage_index_and_failure_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = TaskService()
    task_id = service.create_analysis_task()

    class FakeAnalysisService:
        async def analyze(
            self,
            text: str,
            progress_callback: ProgressCallback | None = None,
        ) -> dict[str, str]:
            assert progress_callback is not None
            progress_callback(
                pipeline_progress(
                    "single_graph",
                    "单条构图",
                    5,
                    "正在把当前事件写入知识图谱",
                )
            )
            raise RuntimeError("graph write failed")

    monkeypatch.setattr(task_service, "AnalysisService", FakeAnalysisService)

    with pytest.raises(RuntimeError, match="graph write failed"):
        await service.run_analysis_task(task_id, "客户 P102 疑似高危交易")

    task = service.get_task(task_id)
    assert task is not None
    assert task["status"] == "failed"
    assert task["stage_key"] == "failed"
    assert task["stage_label"] == "分析失败"
    assert task["stage_index"] == 5
    assert task["stage_detail"] == "graph write failed"


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


@pytest.mark.asyncio
async def test_update_task_signals_event_subscriber() -> None:
    service = TaskService()
    task_id = service.create_analysis_task()

    async def wait_and_collect():
        q = runtime_state.subscribe_task(task_id)
        try:
            return await asyncio.wait_for(q.get(), timeout=1.0)
        finally:
            runtime_state.unsubscribe_task(task_id, q)

    service._mark_running(task_id)
    result = await wait_and_collect()

    assert result is not None
    assert result["status"] == "running"


def test_sse_stream_yields_task_updates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_ENABLED", "false")
    client = TestClient(app)

    class FakeAnalysisService:
        async def analyze(self, text: str, progress_callback=None) -> dict:
            if progress_callback:
                progress_callback(
                    pipeline_progress("single_graph", "单条构图", 4, "写入图谱")
                )
            return {"event_id": "E-SSE-TEST", "status": "analyzed", "raw_content": text}

    monkeypatch.setattr(task_service, "AnalysisService", FakeAnalysisService)
    monkeypatch.setattr(analysis_service, "process_message_detailed", None)

    response = client.post("/api/tasks/analyze", json={"text": "test"})
    assert response.status_code == 200
    task_id = response.json()["task_id"]

    updates = []
    with client.stream("GET", f"/api/tasks/{task_id}/stream") as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        for line in resp.iter_lines():
            if line.startswith("data:"):
                data = json.loads(line[5:].strip())
                updates.append(data)
                if data.get("status") in ("success", "failed"):
                    break

    assert len(updates) >= 1
    assert updates[-1]["task_id"] == task_id
