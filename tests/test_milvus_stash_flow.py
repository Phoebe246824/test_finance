from datetime import datetime

import pytest

import main
from models import EventSource, NormalizedEvent, RiskLevel


class FakeStashStore:
    def __init__(self, events: list[dict]):
        self.events = events
        self.marked_event_ids: list[str] = []

    async def fetch_related_events(
        self,
        event: NormalizedEvent,
        id_numbers: list[str],
        top_k_semantic: int,
        max_per_person: int,
    ) -> list[dict]:
        return self.events

    async def mark_events_graph_built(self, event_ids: list[str]) -> int:
        self.marked_event_ids.extend(event_ids)
        return len(event_ids)


def make_event() -> NormalizedEvent:
    return NormalizedEvent(
        event_id="TRIGGER",
        source=EventSource.NEWS,
        raw_content="trigger P01",
        title="trigger",
        timestamp=datetime(2026, 5, 26, 12, 0, 0),
    )


@pytest.fixture
def config() -> dict:
    return {
        "classification": {"risk_threshold": 0.2},
        "graphiti": {"episode_source_name": "sentinel", "dry_run": True},
        "milvus": {"semantic_top_k": 5, "max_per_person": 7},
        "search": {"risk_num_results": 20, "num_results": 10},
    }


@pytest.mark.asyncio
async def test_batch_graph_marks_only_consumed_stashed_events_on_success(
    monkeypatch, config
):
    stash_store = FakeStashStore(
        [
            {
                "event_id": "E001",
                "raw_content": "history one",
                "created_at": "2026-05-25T12:00:00",
            },
            {
                "event_id": "E002",
                "raw_content": "history two",
                "created_at": "2026-05-24T12:00:00",
            },
        ]
    )
    batch_inputs = []

    async def fake_init_graph_client(config):
        return object()

    async def fake_close_graph_client(graphiti):
        return None

    async def fake_batch_add_to_graph(graphiti, events, group_id, dry_run):
        batch_inputs.extend(events)
        return [{"success": True} for _ in events]

    monkeypatch.setattr(main, "init_graph_client", fake_init_graph_client)
    monkeypatch.setattr(main, "close_graph_client", fake_close_graph_client)
    monkeypatch.setattr(main, "batch_add_to_graph", fake_batch_add_to_graph)

    summary = await main.batch_graph_event_with_related_stash(
        config,
        stash_store,
        ["P01"],
        make_event(),
    )

    assert [item["text"] for item in batch_inputs] == ["history one", "history two"]
    assert stash_store.marked_event_ids == ["E001", "E002"]
    assert summary["fetched_count"] == 2
    assert summary["batched_count"] == 2


@pytest.mark.asyncio
async def test_batch_graph_skips_when_no_stashed_events(monkeypatch, config):
    stash_store = FakeStashStore([])
    called = {"batch": 0}

    async def fake_init_graph_client(config):
        return object()

    async def fake_close_graph_client(graphiti):
        return None

    async def fake_batch_add_to_graph(graphiti, events, group_id, dry_run):
        called["batch"] += 1
        return [{"success": True} for _ in events]

    monkeypatch.setattr(main, "init_graph_client", fake_init_graph_client)
    monkeypatch.setattr(main, "close_graph_client", fake_close_graph_client)
    monkeypatch.setattr(main, "batch_add_to_graph", fake_batch_add_to_graph)

    summary = await main.batch_graph_event_with_related_stash(
        config,
        stash_store,
        ["P01"],
        make_event(),
    )

    assert called["batch"] == 0
    assert stash_store.marked_event_ids == []
    assert summary["fetched_count"] == 0
    assert summary["batched_count"] == 0


@pytest.mark.asyncio
async def test_batch_graph_keeps_stashed_events_unmarked_on_failure(
    monkeypatch, config
):
    stash_store = FakeStashStore(
        [
            {
                "event_id": "E001",
                "raw_content": "history one",
                "created_at": "2026-05-25T12:00:00",
            }
        ]
    )

    async def fake_init_graph_client(config):
        return object()

    async def fake_close_graph_client(graphiti):
        return None

    async def fake_batch_add_to_graph(graphiti, events, group_id, dry_run):
        return [{"success": False}]

    monkeypatch.setattr(main, "init_graph_client", fake_init_graph_client)
    monkeypatch.setattr(main, "close_graph_client", fake_close_graph_client)
    monkeypatch.setattr(main, "batch_add_to_graph", fake_batch_add_to_graph)

    summary = await main.batch_graph_event_with_related_stash(
        config,
        stash_store,
        ["P01"],
        make_event(),
    )

    assert stash_store.marked_event_ids == []
    assert summary["success"] is False


@pytest.mark.asyncio
async def test_low_risk_flow_reuses_first_context_and_skips_batch_path(
    monkeypatch, config
):
    event = make_event()
    dashboard_calls = []
    batch_calls = []

    async def fake_simulate_classification(config, normalized_event):
        normalized_event.event_type = "社区活动"
        normalized_event.summary = "低风险事件"
        return normalized_event

    async def fake_simulate_graph_build(config, normalized_event):
        return [{"event_id": normalized_event.event_id, "success": True}]

    async def fake_evaluate_risk(config, normalized_event, results=None):
        return {
            "risk_level": RiskLevel.LOW,
            "risk_score": 0.1,
            "reasoning": "低风险",
        }

    async def fake_simulate_search(config, normalized_event, num_results=None):
        return {
            "results": [{"type": "edge", "text": "first context"}],
            "reranked_edges": [{"text": "first context"}],
            "reranked_episodes": [],
        }

    async def fake_batch_graph_event_with_related_stash(
        config, stash_store, id_numbers, normalized_event
    ):
        batch_calls.append(normalized_event.event_id)
        return {"success": True}

    async def fake_simulate_dashboard(config, normalized_event, results):
        dashboard_calls.append(normalized_event.event_id)
        return None

    monkeypatch.setattr(main, "simulate_classification", fake_simulate_classification)
    monkeypatch.setattr(main, "simulate_graph_build", fake_simulate_graph_build)
    monkeypatch.setattr(main, "evaluate_risk", fake_evaluate_risk)
    monkeypatch.setattr(main, "simulate_search", fake_simulate_search)
    monkeypatch.setattr(
        main,
        "batch_graph_event_with_related_stash",
        fake_batch_graph_event_with_related_stash,
    )
    monkeypatch.setattr(main, "simulate_dashboard", fake_simulate_dashboard)

    stash_store = FakeStashStore([])
    flow = main.SentinelPipelineFlow(
        config,
        event,
        stash_store=stash_store,
        id_numbers=["P01"],
    )

    await flow.kickoff_async()

    assert batch_calls == []
    assert dashboard_calls == []
    assert "TRIGGER" in stash_store.marked_event_ids


@pytest.mark.asyncio
async def test_high_risk_flow_uses_second_context_after_batch_graph(
    monkeypatch, config
):
    event = make_event()
    search_calls = []
    batch_calls = []
    second_risk_calls = []
    dashboard_context_sizes = []

    async def fake_simulate_classification(config, normalized_event):
        normalized_event.event_type = "公共安全"
        normalized_event.summary = "高风险事件"
        return normalized_event

    async def fake_simulate_graph_build(config, normalized_event):
        return [{"event_id": normalized_event.event_id, "success": True}]

    async def fake_evaluate_risk(config, normalized_event, results=None):
        return {
            "risk_level": RiskLevel.HIGH,
            "risk_score": 0.9,
            "reasoning": "首次超阈值",
        }

    async def fake_batch_graph_event_with_related_stash(
        config, stash_store, id_numbers, normalized_event
    ):
        batch_calls.append(normalized_event.event_id)
        return {"success": True, "fetched_count": 2, "batched_count": 2}

    async def fake_simulate_search(config, normalized_event, num_results=None):
        search_calls.append(num_results)
        if len(search_calls) == 1:
            return {
                "results": [{"type": "edge", "text": "first context"}],
                "reranked_edges": [{"text": "first context"}],
                "reranked_episodes": [],
            }
        return {
            "results": [{"type": "edge", "text": "second context"}],
            "reranked_edges": [{"text": "second context"}],
            "reranked_episodes": [],
        }

    async def fake_second_evaluate_risk(config, normalized_event, results):
        second_risk_calls.append(len(results.get("results", [])))
        return {
            "risk_level": RiskLevel.MEDIUM,
            "risk_score": 0.6,
            "reasoning": "二次评估",
        }

    async def fake_simulate_dashboard(config, normalized_event, results):
        dashboard_context_sizes.append(len(results.get("results", [])))
        return None

    monkeypatch.setattr(main, "simulate_classification", fake_simulate_classification)
    monkeypatch.setattr(main, "simulate_graph_build", fake_simulate_graph_build)
    monkeypatch.setattr(main, "evaluate_risk", fake_evaluate_risk)
    monkeypatch.setattr(
        main,
        "batch_graph_event_with_related_stash",
        fake_batch_graph_event_with_related_stash,
    )
    monkeypatch.setattr(main, "simulate_search", fake_simulate_search)
    monkeypatch.setattr(main, "second_evaluate_risk", fake_second_evaluate_risk)
    monkeypatch.setattr(main, "simulate_dashboard", fake_simulate_dashboard)

    stash_store = FakeStashStore([])
    flow = main.SentinelPipelineFlow(
        config,
        event,
        stash_store=stash_store,
        id_numbers=["P01"],
    )

    await flow.kickoff_async()

    assert batch_calls == ["TRIGGER"]
    assert search_calls == [20, 20]
    assert second_risk_calls == [1]
    assert dashboard_context_sizes == [1]
    assert "TRIGGER" in stash_store.marked_event_ids


@pytest.mark.asyncio
async def test_second_risk_below_threshold_completes_without_dashboard(
    monkeypatch, config
):
    event = make_event()
    dashboard_calls = []

    async def fake_simulate_classification(config, normalized_event):
        normalized_event.event_type = "公共安全"
        normalized_event.summary = "高风险事件"
        return normalized_event

    async def fake_simulate_graph_build(config, normalized_event):
        return [{"event_id": normalized_event.event_id, "success": True}]

    async def fake_evaluate_risk(config, normalized_event, results=None):
        return {
            "risk_level": RiskLevel.HIGH,
            "risk_score": 0.9,
            "reasoning": "首次超阈值",
        }

    async def fake_batch_graph_event_with_related_stash(
        config, stash_store, id_numbers, normalized_event
    ):
        return {"success": True, "fetched_count": 1, "batched_count": 1}

    async def fake_simulate_search(config, normalized_event, num_results=None):
        return {
            "results": [{"type": "edge", "text": "context"}],
            "reranked_edges": [{"text": "context"}],
            "reranked_episodes": [],
        }

    async def fake_second_evaluate_risk(config, normalized_event, results):
        return {
            "risk_level": RiskLevel.MEDIUM,
            "risk_score": 0.2,
            "reasoning": "二次评估回落到阈值",
        }

    async def fake_simulate_dashboard(config, normalized_event, results):
        dashboard_calls.append(normalized_event.event_id)
        return None

    monkeypatch.setattr(main, "simulate_classification", fake_simulate_classification)
    monkeypatch.setattr(main, "simulate_graph_build", fake_simulate_graph_build)
    monkeypatch.setattr(main, "evaluate_risk", fake_evaluate_risk)
    monkeypatch.setattr(
        main,
        "batch_graph_event_with_related_stash",
        fake_batch_graph_event_with_related_stash,
    )
    monkeypatch.setattr(main, "simulate_search", fake_simulate_search)
    monkeypatch.setattr(main, "second_evaluate_risk", fake_second_evaluate_risk)
    monkeypatch.setattr(main, "simulate_dashboard", fake_simulate_dashboard)

    flow = main.SentinelPipelineFlow(
        config,
        event,
        stash_store=FakeStashStore([]),
        id_numbers=["P01"],
    )
    await flow.kickoff_async()

    assert dashboard_calls == []
