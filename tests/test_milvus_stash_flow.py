from datetime import datetime

import pytest

import main
from models import EventSource, NormalizedEvent


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
        "graphiti": {"episode_source_name": "sentinel", "dry_run": True},
        "milvus": {"semantic_top_k": 5, "max_per_person": 7},
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

    await main._maybe_batch_graph_stashed_events(
        config,
        stash_store,
        ["P01"],
        make_event(),
    )

    assert [item["text"] for item in batch_inputs] == [
        "trigger P01",
        "history one",
        "history two",
    ]
    assert stash_store.marked_event_ids == ["E001", "E002"]


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
            },
        ]
    )

    async def fake_init_graph_client(config):
        return object()

    async def fake_close_graph_client(graphiti):
        return None

    async def fake_batch_add_to_graph(graphiti, events, group_id, dry_run):
        return [{"success": True}, {"success": False}]

    monkeypatch.setattr(main, "init_graph_client", fake_init_graph_client)
    monkeypatch.setattr(main, "close_graph_client", fake_close_graph_client)
    monkeypatch.setattr(main, "batch_add_to_graph", fake_batch_add_to_graph)

    await main._maybe_batch_graph_stashed_events(
        config,
        stash_store,
        ["P01"],
        make_event(),
    )

    assert stash_store.marked_event_ids == []
