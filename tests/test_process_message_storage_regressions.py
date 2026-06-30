from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

import main
from blacklist.stores import factory
from models import EventSource, NormalizedEvent
from tests.fakes.fake_milvus import FakeMilvusClient


@pytest.mark.asyncio
async def test_process_message_detailed_stashes_miss_with_single_embedding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeMilvusClient()
    embedded_texts: list[str] = []

    async def fake_normalize_payload_to_event(
        payload: dict[str, str],
        config: dict[str, Any],
    ) -> NormalizedEvent:
        return NormalizedEvent(
            event_id="E-SINGLE-STASH",
            source=EventSource.TRANSACTION,
            raw_content="客户 P200 日常消费",
            title="低风险历史",
            timestamp=datetime(2026, 6, 23, 11, 0, 0),
        )

    def fake_create_client(config: Any) -> FakeMilvusClient:
        return fake_client

    def fake_create_embedding_fn(embedder_config: dict[str, Any]) -> Any:
        def embed(text: str) -> list[float]:
            embedded_texts.append(text)
            return [0.0, 1.0, 0.0]

        return embed

    monkeypatch.setattr(main, "normalize_payload_to_event", fake_normalize_payload_to_event)
    monkeypatch.setattr(factory, "create_milvus_client", fake_create_client)
    monkeypatch.setattr(factory, "create_embedding_fn", fake_create_embedding_fn)

    result = await main.process_message_detailed(
        "客户 P200 日常消费",
        config=main.load_config(),
    )

    assert result["status"] == "stashed"
    assert result["stashed_count"] == 1
    assert embedded_texts == ["客户 P200 日常消费", "客户 P200 日常消费"]
    assert fake_client.rows["stashed_events"]["E-SINGLE-STASH"]["status"] == "stashed"
    assert fake_client.rows["events"]["E-SINGLE-STASH"]["status"] == "stashed"


@pytest.mark.asyncio
async def test_process_message_detailed_does_not_stash_blacklist_hit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeMilvusClient()

    async def fake_normalize_payload_to_event(
        payload: dict[str, str],
        config: dict[str, Any],
    ) -> NormalizedEvent:
        return NormalizedEvent(
            event_id="E-BLACKLIST-HIT",
            source=EventSource.TRANSACTION,
            raw_content="客户 P102 分拆交易",
            title="高危事件",
            timestamp=datetime(2026, 6, 23, 11, 0, 0),
        )

    def fake_create_client(config: Any) -> FakeMilvusClient:
        return fake_client

    def fake_create_embedding_fn(embedder_config: dict[str, Any]) -> Any:
        return lambda text: [0.0, 1.0, 0.0]

    class FakeBlacklistResult:
        should_proceed = True
        matched_persons = ["P102"]
        matched_keywords = ["分拆交易"]
        event_similarity = type(
            "FakeEventSimilarity",
            (),
            {
                "hit": True,
                "score": 0.9,
                "threshold": 0.6,
                "event_id": None,
                "summary": None,
            },
        )()
        event_hit = True

    class FakeBlacklistFilter:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def check_with_details(self, event: NormalizedEvent) -> FakeBlacklistResult:
            return FakeBlacklistResult()

    class FakeFlow:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.state = {
                "risk_result": {"dimension_scores": {}},
                "trend_report": {},
                "graph_result": None,
                "second_risk_applied": False,
            }

        async def kickoff_async(self) -> None:
            return None

    monkeypatch.setattr(main, "normalize_payload_to_event", fake_normalize_payload_to_event)
    monkeypatch.setattr(factory, "create_milvus_client", fake_create_client)
    monkeypatch.setattr(factory, "create_embedding_fn", fake_create_embedding_fn)
    monkeypatch.setattr(main, "BlacklistFilter", FakeBlacklistFilter)
    monkeypatch.setattr(main, "SentinelPipelineFlow", FakeFlow)

    result = await main.process_message_detailed(
        "客户 P102 分拆交易",
        config=main.load_config(),
    )

    assert result["status"] == "analyzed"
    assert "stashed_events" not in fake_client.rows or "E-BLACKLIST-HIT" not in fake_client.rows["stashed_events"]
