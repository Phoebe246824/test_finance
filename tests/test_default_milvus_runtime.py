from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

import main
from blacklist.stores import factory
from models import EventSource, NormalizedEvent
from tests.fakes.fake_milvus import FakeMilvusClient


@pytest.mark.asyncio
async def test_process_message_detailed_uses_milvus_and_configured_embedder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeMilvusClient()
    captured_embedder_configs: list[dict[str, Any]] = []

    async def fake_normalize_payload_to_event(
        payload: dict[str, str],
        config: dict[str, Any],
    ) -> NormalizedEvent:
        return NormalizedEvent(
            event_id="E-MILVUS-STASH",
            source=EventSource.TRANSACTION,
            raw_content="客户 P102 工资入账后日常消费",
            title="低风险历史",
            timestamp=datetime(2026, 6, 23, 10, 0, 0),
        )

    def fake_create_client(config: Any) -> FakeMilvusClient:
        return fake_client

    def fake_create_embedding_fn(
        embedder_config: dict[str, Any],
    ) -> Any:
        captured_embedder_configs.append(dict(embedder_config))
        return lambda text: [0.0, 1.0, 0.0]

    monkeypatch.setattr(
        main,
        "normalize_payload_to_event",
        fake_normalize_payload_to_event,
    )
    monkeypatch.setattr(factory, "create_milvus_client", fake_create_client)
    monkeypatch.setattr(factory, "create_embedding_fn", fake_create_embedding_fn)

    config = main.load_config()
    config["embedder"] = {
        "model": "BAAI/bge-m3",
        "api_key": "env-embedder-key",
        "api_base": "http://127.0.0.1:1234/v1",
    }

    result = await main.process_message_detailed(
        "客户 P102 工资入账后日常消费",
        config=config,
    )

    assert result["status"] == "stashed"
    assert result["storage"] == {
        "backend": "milvus",
        "events_collection": "events",
    }
    assert captured_embedder_configs == [config["embedder"]]
    assert fake_client.rows["events"]["E-MILVUS-STASH"]["status"] == "stashed"
