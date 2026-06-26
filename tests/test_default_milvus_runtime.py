from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

import main
from backend.app.services import analysis_service
from backend.app.services.analysis_service import AnalysisService
from blacklist.stores import factory
from blacklist.stores.runtime import reset_runtime_store_bundle_cache
from models import EventSource, NormalizedEvent
from tests.fakes.fake_milvus import FakeMilvusClient


@pytest.fixture(autouse=True)
def clear_runtime_store_cache() -> None:
    reset_runtime_store_bundle_cache()
    yield
    reset_runtime_store_bundle_cache()


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


@pytest.mark.asyncio
async def test_process_message_detailed_reuses_default_store_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeMilvusClient()
    created_clients: list[FakeMilvusClient] = []
    created_embedders: list[dict[str, Any]] = []
    event_ids = iter(["E-CACHED-1", "E-CACHED-2"])

    async def fake_normalize_payload_to_event(
        payload: dict[str, str],
        config: dict[str, Any],
    ) -> NormalizedEvent:
        return NormalizedEvent(
            event_id=next(event_ids),
            source=EventSource.TRANSACTION,
            raw_content=str(payload["data"]),
            title="低风险历史",
            timestamp=datetime(2026, 6, 23, 10, 0, 0),
        )

    def fake_create_client(config: Any) -> FakeMilvusClient:
        created_clients.append(fake_client)
        return fake_client

    def fake_create_embedding_fn(
        embedder_config: dict[str, Any],
    ) -> Any:
        created_embedders.append(dict(embedder_config))
        return lambda text: [0.0, 1.0, 0.0]

    monkeypatch.setattr(
        main,
        "normalize_payload_to_event",
        fake_normalize_payload_to_event,
    )
    monkeypatch.setattr(factory, "create_milvus_client", fake_create_client)
    monkeypatch.setattr(factory, "create_embedding_fn", fake_create_embedding_fn)

    first = await main.process_message_detailed("客户 P102 日常消费")
    second = await main.process_message_detailed("客户 P103 日常消费")

    assert first["status"] == "stashed"
    assert second["status"] == "stashed"
    assert len(created_clients) == 1
    assert len(created_embedders) == 1


@pytest.mark.asyncio
async def test_analysis_service_uses_default_runtime_store_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process_configs: list[dict[str, Any]] = []

    async def fake_process_message_detailed(
        text: str,
        config: dict[str, Any],
    ) -> dict[str, str]:
        process_configs.append(config)
        return {"event_id": "E001", "status": "stashed", "raw_content": text}

    monkeypatch.setattr(
        analysis_service,
        "process_message_detailed",
        fake_process_message_detailed,
    )

    result = await AnalysisService().analyze("客户 P102 日常消费")

    assert result["event_id"] == "E001"
    assert process_configs
    assert process_configs[0]["storage"] == {"backend": "milvus"}
    assert process_configs[0]["milvus"]["stash_collection"] == "events"
