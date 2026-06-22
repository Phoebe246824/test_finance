from datetime import datetime, timedelta

import pytest

from blacklist.sqlite_stash import SQLiteStashStore
from models import EventSource, NormalizedEvent


def make_event(
    event_id: str,
    raw_content: str,
    timestamp: datetime,
) -> NormalizedEvent:
    return NormalizedEvent(
        event_id=event_id,
        source=EventSource.NEWS,
        raw_content=raw_content,
        title=event_id,
        timestamp=timestamp,
    )


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 6, 22, 10, 30, 0)


@pytest.fixture
def store(tmp_path, now) -> SQLiteStashStore:
    return SQLiteStashStore.from_database_url(
        f"sqlite:///{tmp_path / 'sentinel.db'}",
        now_fn=lambda: now,
        ttl_days=30,
    )


@pytest.mark.asyncio
async def test_sqlite_stash_store_writes_and_deduplicates_content(store, now) -> None:
    first = make_event("E001", "客户 P102 工资入账后日常消费", now)
    duplicate = make_event("E002", "客户 P102 工资入账后日常消费", now)

    first_count = await store.stash_event(first, ["p102"])
    duplicate_count = await store.stash_event(duplicate, ["P102"])

    assert first_count == 1
    assert duplicate_count == 0


@pytest.mark.asyncio
async def test_sqlite_stash_store_recalls_unbuilt_same_person_events(store, now) -> None:
    await store.stash_event(
        make_event("HISTORY", "客户 P102 多笔接近阈值转账", now - timedelta(days=1)),
        ["P102"],
    )
    await store.stash_event(
        make_event("OTHER", "客户 P999 普通消费", now - timedelta(days=1)),
        ["P999"],
    )

    results = await store.fetch_related_events(
        make_event("CURRENT", "客户 P102 向涉诈账户转账", now),
        ["P102"],
        top_k_semantic=10,
        max_per_person=10,
    )

    assert [item["event_id"] for item in results] == ["HISTORY"]
    assert results[0]["person_ids"] == ["P102"]
    assert results[0]["match_source"] == "person_match"


@pytest.mark.asyncio
async def test_sqlite_stash_store_excludes_expired_current_and_built_rows(
    store, now
) -> None:
    await store.stash_event(make_event("CURRENT", "客户 P102 当前事件", now), ["P102"])
    await store.stash_event(
        make_event("EXPIRED", "客户 P102 过期历史", now - timedelta(days=40)),
        ["P102"],
    )
    await store.stash_event(make_event("BUILT", "客户 P102 已构图历史", now), ["P102"])
    await store.mark_events_graph_built(["BUILT"])

    results = await store.fetch_related_events(
        make_event("CURRENT", "客户 P102 当前事件", now),
        ["P102"],
        top_k_semantic=10,
        max_per_person=10,
    )

    assert results == []
