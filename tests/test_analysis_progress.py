from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta

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


@pytest.fixture(autouse=True)
def reset_tasks() -> None:
    runtime_state.tasks.clear()
    runtime_state._subscribers.clear()
    runtime_state._task_finished_at.clear()


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
async def test_task_cancel_keeps_cancelled_status_after_worker_finishes(
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
                pipeline_progress("single_graph", "单条构图", 4, "正在写入图谱")
            )
            service.cancel_task(task_id)
            return {"event_id": "E-CANCELLED"}

    monkeypatch.setattr(task_service, "AnalysisService", FakeAnalysisService)

    await service.run_analysis_task(task_id, "客户 P102 疑似高危交易")

    task = service.get_task(task_id)
    assert task is not None
    assert task["status"] == "cancelled"
    assert task["event_id"] is None
    assert task["stage_key"] == "cancelled"


@pytest.mark.asyncio
async def test_task_cancel_keeps_cancelled_status_after_worker_error(
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
            service.cancel_task(task_id)
            raise RuntimeError("late failure after cancel")

    monkeypatch.setattr(task_service, "AnalysisService", FakeAnalysisService)

    await service.run_analysis_task(task_id, "客户 P102 疑似高危交易")

    task = service.get_task(task_id)
    assert task is not None
    assert task["status"] == "cancelled"
    assert task["stage_key"] == "cancelled"


@pytest.mark.asyncio
async def test_update_task_signals_subscriber_and_cleanup_notifies_removal() -> None:
    service = TaskService()
    task_id = service.create_analysis_task()
    q = runtime_state.subscribe_task(task_id)

    try:
        initial = await asyncio.wait_for(q.get(), timeout=1.0)
        assert initial is not None
        assert initial["status"] == "queued"

        running = pipeline_progress("single_graph", "单条构图", 4, "正在写入图谱")
        service._update_progress(task_id, running)
        updated = await asyncio.wait_for(q.get(), timeout=1.0)
        assert updated is not None
        assert updated["stage_key"] == "single_graph"

        service.cancel_task(task_id)
        cancelled = await asyncio.wait_for(q.get(), timeout=1.0)
        assert cancelled is not None
        assert cancelled["status"] == "cancelled"

        removed = runtime_state.cleanup_stale_tasks(ttl=-1)
        assert removed == 1
        assert await asyncio.wait_for(q.get(), timeout=1.0) is None
        assert service.get_task(task_id) is None
    finally:
        runtime_state.unsubscribe_task(task_id, q)


def test_sse_stream_yields_task_updates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_ENABLED", "false")
    client = TestClient(app)

    class FakeAnalysisService:
        async def analyze(
            self,
            text: str,
            progress_callback: ProgressCallback | None = None,
            actor: CurrentUser | None = None,
        ) -> dict[str, str]:
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
    assert updates[-1]["status"] == "success"


def test_cleanup_stale_tasks_removes_stuck_nonterminal_tasks() -> None:
    service = TaskService()
    task_id = service.create_analysis_task()
    old_started_at = (datetime.now() - timedelta(hours=2)).isoformat(timespec="seconds")
    runtime_state.update_task(task_id, {"started_at": old_started_at, "status": "running"})

    removed = runtime_state.cleanup_stale_tasks()

    assert removed == 1
    assert service.get_task(task_id) is None


@pytest.mark.asyncio
async def test_analysis_tasks_respect_saved_model_concurrency(monkeypatch: pytest.MonkeyPatch) -> None:
    service = TaskService()
    first_task = service.create_analysis_task()
    second_task = service.create_analysis_task()
    active = 0
    max_active = 0
    started: list[str] = []

    class FakeAnalysisService:
        async def analyze(
            self,
            text: str,
            progress_callback: ProgressCallback | None = None,
            actor: CurrentUser | None = None,
        ) -> dict[str, str]:
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            started.append(text)
            await asyncio.sleep(0.02)
            active -= 1
            return {"event_id": text}

    monkeypatch.setattr(task_service, "AnalysisService", FakeAnalysisService)
    monkeypatch.setattr(task_service, "model_concurrency_limit", lambda: 1)

    started_at = time.perf_counter()
    await asyncio.gather(
        service.run_analysis_task(first_task, "E-1"),
        service.run_analysis_task(second_task, "E-2"),
    )
    elapsed = time.perf_counter() - started_at

    assert started == ["E-1", "E-2"]
    assert max_active == 1
    assert elapsed >= 0.04


@pytest.mark.asyncio
async def test_app_lifespan_runs_stale_task_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.app.main as app_main

    calls = 0
    original_sleep = asyncio.sleep

    async def fast_sleep(delay: float) -> None:
        await original_sleep(0)

    class FakeRuntimeState:
        def cleanup_stale_tasks(self) -> int:
            nonlocal calls
            calls += 1
            return 0

    monkeypatch.setattr(app_main, "_CLEANUP_INTERVAL", 0.001)
    monkeypatch.setattr(app_main.asyncio, "sleep", fast_sleep)
    monkeypatch.setattr(app_main, "runtime_state", FakeRuntimeState())

    app = app_main.create_app()
    async with app.router.lifespan_context(app):
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    assert calls >= 1
