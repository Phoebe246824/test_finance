from datetime import datetime

import pytest

import main
from backend.app.db.session import init_db
from blacklist import runtime_storage
from blacklist.sqlite_stash import SQLiteStashStore
from models import EventSource, NormalizedEvent


@pytest.mark.asyncio
async def test_process_message_detailed_stashes_to_sqlite_without_milvus(
    monkeypatch,
    tmp_path,
) -> None:
    db_path = tmp_path / "sentinel.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("BLACKLIST_BACKEND", "sqlite")
    monkeypatch.setenv("STASH_BACKEND", "sqlite")
    init_db()

    event = NormalizedEvent(
        event_id="E-SQLITE-STASH",
        source=EventSource.NEWS,
        raw_content="客户 P102 工资入账后日常消费",
        title="低风险历史",
        timestamp=datetime(2026, 6, 22, 10, 0, 0),
    )

    async def fake_normalize_payload_to_event(payload, config):
        return event

    def fail_milvus_from_config(config):
        raise AssertionError("default runtime must not initialize Milvus")

    monkeypatch.setattr(main, "normalize_payload_to_event", fake_normalize_payload_to_event)
    monkeypatch.setattr(
        runtime_storage.MilvusStashStore,
        "from_config",
        fail_milvus_from_config,
    )

    result = await main.process_message_detailed("客户 P102 工资入账后日常消费")

    stash_store = SQLiteStashStore.from_database_url(f"sqlite:///{db_path}")
    recalled = await stash_store.fetch_related_events(
        NormalizedEvent(
            event_id="CURRENT",
            source=EventSource.NEWS,
            raw_content="客户 P102 后续可疑转账",
            title="触发事件",
        ),
        ["P102"],
    )
    assert result["status"] == "stashed"
    assert result["storage"]["blacklist_backend"] == "sqlite"
    assert result["storage"]["stash_backend"] == "sqlite"
    assert [item["event_id"] for item in recalled] == ["E-SQLITE-STASH"]
