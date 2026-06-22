import sqlite3

import pytest

from blacklist.sqlite_store import SQLiteBlacklistStore


def connection_factory(db_path: str):
    def _connect() -> sqlite3.Connection:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    return _connect


@pytest.fixture
def store(tmp_path) -> SQLiteBlacklistStore:
    return SQLiteBlacklistStore(connection_factory(tmp_path / "sentinel.db"))


@pytest.mark.asyncio
async def test_sqlite_blacklist_store_matches_enabled_person_case_insensitively(
    store,
) -> None:
    await store.append_person("p105")

    assert await store.query_person("P105") == 1.0
    assert await store.query_person("p105") == 1.0


@pytest.mark.asyncio
async def test_sqlite_blacklist_store_ignores_disabled_items(store) -> None:
    await store.append_keyword("洗钱")

    removed = await store.remove_keyword("洗钱")

    assert removed is True
    assert await store.query_keywords() == []


@pytest.mark.asyncio
async def test_sqlite_blacklist_store_returns_event_payloads_for_similarity(
    store,
) -> None:
    await store.append_event("E-FIN-AML-001", "疑似分拆交易与洗钱")

    event = await store.query_event("E-FIN-AML-001")
    summaries = await store.get_event_summaries()

    assert event == {
        "event_id": "E-FIN-AML-001",
        "summary": "疑似分拆交易与洗钱",
    }
    assert list(summaries) == ["E-FIN-AML-001"]
    assert "疑似分拆交易与洗钱" in summaries["E-FIN-AML-001"]
