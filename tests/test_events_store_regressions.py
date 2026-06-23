from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from blacklist.stores.events_store import EventsStore
from models import EventSource, NormalizedEvent
from tests.fakes.fake_milvus import FakeMilvusClient


def fake_embed(text: str) -> list[float]:
    if "分拆转账" in text or "alpha" in text:
        return [1.0, 0.0, 0.0]
    if "工资入账" in text or "beta" in text:
        return [0.0, 1.0, 0.0]
    return [0.0, 0.0, 1.0]


def make_event(event_id: str, text: str, timestamp: datetime) -> NormalizedEvent:
    return NormalizedEvent(
        event_id=event_id,
        source=EventSource.TRANSACTION,
        raw_content=text,
        title=event_id,
        timestamp=timestamp,
        summary=text[:20],
    )


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 6, 23, 9, 0, 0)


@pytest.mark.asyncio
async def test_fetch_related_events_filters_semantic_matches_below_threshold(
    now: datetime,
) -> None:
    client = FakeMilvusClient()
    store = EventsStore(
        client=client,
        embedding_fn=fake_embed,
        embedding_dim=3,
        semantic_score_threshold=0.5,
    )
    await store.stash_event(make_event("SIMILAR", "alpha P999 相似分拆转账", now), ["P999"])
    await store.stash_event(make_event("LOOSE", "beta P888 工资入账", now), ["P888"])

    results = await store.fetch_related_events(
        make_event("CURRENT", "alpha P777 当前可疑分拆转账", now),
        [],
        top_k_semantic=10,
        max_per_person=10,
    )

    assert [(item["event_id"], item["semantic_score"]) for item in results] == [
        ("SIMILAR", pytest.approx(1.0)),
    ]


@pytest.mark.asyncio
async def test_fetch_related_events_ignores_empty_and_unknown_semantic_hits(
    monkeypatch: pytest.MonkeyPatch,
    now: datetime,
) -> None:
    client = FakeMilvusClient()
    store = EventsStore(client=client, embedding_fn=fake_embed, embedding_dim=3)
    await store.stash_event(make_event("ELIGIBLE", "alpha P999 相似分拆转账", now), ["P999"])

    def fake_search_empty(**kwargs: object) -> list[list[dict[str, object]]]:
        return []

    monkeypatch.setattr(client, "search", fake_search_empty)
    empty_results = await store.fetch_related_events(
        make_event("CURRENT", "alpha P777 当前可疑分拆转账", now),
        [],
    )

    def fake_search_unknown(**kwargs: object) -> list[list[dict[str, object]]]:
        return [[{"id": "UNKNOWN", "distance": 1.0, "entity": {}}]]

    monkeypatch.setattr(client, "search", fake_search_unknown)
    unknown_results = await store.fetch_related_events(
        make_event("CURRENT", "alpha P777 当前可疑分拆转账", now),
        [],
    )

    assert empty_results == []
    assert unknown_results == []


@pytest.mark.asyncio
async def test_cleanup_expired_removes_expired_and_old_built_rows(
    now: datetime,
) -> None:
    client = FakeMilvusClient()
    store = EventsStore(
        client=client,
        embedding_fn=fake_embed,
        embedding_dim=3,
        ttl_days=30,
    )
    await store.stash_event(make_event("EXPIRED", "alpha P101 expired", now - timedelta(days=31)), ["P101"])
    await store.stash_event(make_event("BUILT", "alpha P102 built", now - timedelta(days=10)), ["P102"])
    await store.stash_event(make_event("VALID", "alpha P103 valid", now), ["P103"])
    await store.mark_events_graph_built(["BUILT"])

    deleted = store.cleanup_expired(now=now, graph_built_retention_days=7)

    assert deleted == 2
    assert sorted(client.rows["events"]) == ["VALID"]


@pytest.mark.asyncio
async def test_events_store_uses_configured_collection_name(now: datetime) -> None:
    client = FakeMilvusClient()
    store = EventsStore(
        client=client,
        embedding_fn=fake_embed,
        embedding_dim=3,
        collection_name="risk_events",
    )

    await store.stash_event(make_event("E001", "alpha P102 分拆转账", now), ["P102"])

    assert client.create_calls[0]["collection_name"] == "risk_events"
    assert sorted(client.rows) == ["risk_events"]
    assert client.rows["risk_events"]["E001"]["event_id"] == "E001"
