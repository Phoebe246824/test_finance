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
    assert embedded_texts == ["客户 P200 日常消费"]
    assert fake_client.rows["events"]["E-SINGLE-STASH"]["status"] == "stashed"
