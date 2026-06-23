from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from blacklist.stores.events_store import EventsStore
from models import EventSource, NormalizedEvent, RiskLevel
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


@pytest.fixture
def client() -> FakeMilvusClient:
    return FakeMilvusClient()


@pytest.fixture
def store(client: FakeMilvusClient) -> EventsStore:
    return EventsStore(
        client=client,
        embedding_fn=fake_embed,
        embedding_dim=3,
        ttl_days=30,
    )


@pytest.mark.asyncio
async def test_upsert_event_creates_events_collection_and_full_row(
    store: EventsStore,
    client: FakeMilvusClient,
    now: datetime,
) -> None:
    event = make_event("E001", "客户 P102 工资入账后日常消费", now)

    written = await store.upsert_event(
        event,
        person_ids=["p102"],
        status="stashed",
        blacklist_decision="miss",
    )

    assert written == 1
    assert client.create_calls[0]["collection_name"] == "events"
    row = client.rows["events"]["E001"]
    assert row["event_id"] == "E001"
    assert row["content_hash"]
    assert row["raw_content"] == "客户 P102 工资入账后日常消费"
    assert row["title"] == "E001"
    assert row["source"] == "transaction"
    assert row["person_ids"] == ["P102"]
    assert row["status"] == "stashed"
    assert row["blacklist_decision"] == "miss"
    assert row["embedding"] == [0.0, 1.0, 0.0]
    assert row["is_graph_built"] is False
    assert row["created_at"] == now.isoformat()
    assert row["expire_at"] == (now + timedelta(days=30)).isoformat()


@pytest.mark.asyncio
async def test_stash_event_deduplicates_by_content_hash(
    store: EventsStore,
    client: FakeMilvusClient,
    now: datetime,
) -> None:
    first = make_event("E001", "客户 P102 工资入账后日常消费", now)
    duplicate = make_event("E002", "客户 P102   工资入账后日常消费", now)

    assert await store.stash_event(first, ["P102"]) == 1
    assert await store.stash_event(duplicate, ["P102"]) == 0
    assert list(client.rows["events"]) == ["E001"]


@pytest.mark.asyncio
async def test_upsert_event_keeps_pending_duplicate_content_with_new_event_id(
    store: EventsStore,
    client: FakeMilvusClient,
    now: datetime,
) -> None:
    stashed = make_event("STASHED", "客户 P102 工资入账后日常消费", now)
    pending = make_event("PENDING", "客户 P102   工资入账后日常消费", now)

    assert await store.stash_event(stashed, ["P102"]) == 1
    written = await store.upsert_event(
        pending,
        person_ids=["P102"],
        status="pending",
    )

    assert written == 1
    assert sorted(client.rows["events"]) == ["PENDING", "STASHED"]
    assert client.rows["events"]["PENDING"]["status"] == "pending"


@pytest.mark.asyncio
async def test_fetch_related_events_merges_same_person_and_semantic_matches(
    store: EventsStore,
    now: datetime,
) -> None:
    await store.stash_event(make_event("E001", "alpha P102 分拆转账前置交易", now), ["P102"])
    await store.stash_event(make_event("E002", "alpha P999 相似跨境分拆转账", now), ["P999"])
    await store.stash_event(make_event("E003", "beta P102 工资入账", now), ["P102"])

    results = await store.fetch_related_events(
        make_event("E999", "alpha P102 当前可疑分拆转账", now),
        ["P102"],
        top_k_semantic=2,
        max_per_person=10,
    )

    assert [(item["event_id"], item["match_source"]) for item in results] == [
        ("E001", "both"),
        ("E003", "person_match"),
        ("E002", "semantic_match"),
    ]


@pytest.mark.asyncio
async def test_fetch_related_events_excludes_current_expired_and_built_events(
    store: EventsStore,
    now: datetime,
) -> None:
    await store.stash_event(make_event("CURRENT", "alpha P102 current", now), ["P102"])
    await store.stash_event(
        make_event("EXPIRED", "alpha P102 old", now - timedelta(days=40)),
        ["P102"],
    )
    await store.stash_event(make_event("BUILT", "alpha P102 built", now), ["P102"])
    await store.mark_events_graph_built(["BUILT"])
    await store.stash_event(make_event("VALID", "alpha P102 valid", now), ["P102"])

    results = await store.fetch_related_events(
        make_event("CURRENT", "alpha P102 trigger", now),
        ["P102"],
        top_k_semantic=10,
        max_per_person=10,
    )

    assert [item["event_id"] for item in results] == ["VALID"]


@pytest.mark.asyncio
async def test_upsert_analysis_result_updates_event_fields(
    store: EventsStore,
    now: datetime,
) -> None:
    event = make_event("E001", "alpha P102 分拆转账", now)
    await store.upsert_event(event, person_ids=["P102"], status="pending")

    await store.upsert_analysis_result(
        {
            "event_id": "E001",
            "raw_content": event.raw_content,
            "title": event.title,
            "event_type": "反洗钱",
            "summary": "疑似分拆交易",
            "status": "analyzed",
            "risk_level": RiskLevel.HIGH,
            "risk_score": 0.92,
            "reasoning": "多账户拆分",
            "blacklist": {
                "decision": "PASS",
                "matched_persons": ["P102"],
                "matched_keywords": ["分拆交易"],
                "event_similarity": {"hit": True, "score": 0.88},
            },
            "dimension_scores": {"transaction_behavior": 0.9},
            "trend_report": {"trend": "rising"},
        }
    )

    row = store.get_event("E001")
    assert row is not None
    assert row["event_type"] == "反洗钱"
    assert row["risk_level"] == "high"
    assert row["risk_score"] == pytest.approx(0.92)
    assert row["matched_keywords"] == ["分拆交易"]
    assert row["event_similarity"] == {"hit": True, "score": 0.88}
    assert row["dimension_scores"] == {"transaction_behavior": 0.9}
    assert row["trend_report"] == {"trend": "rising"}


def test_list_events_filters_and_orders_by_updated_at(
    store: EventsStore,
    client: FakeMilvusClient,
    now: datetime,
) -> None:
    client.rows["events"] = {
        "E001": {
            "event_id": "E001",
            "raw_content": "低风险工资入账",
            "title": "工资",
            "summary": "工资",
            "status": "stashed",
            "risk_level": "low",
            "risk_score": 0.0,
            "event_type": "正常交易",
            "created_at": "2026-06-22T09:00:00",
            "updated_at": "2026-06-22T09:00:00",
            "matched_keywords": "[]",
            "matched_persons": "[]",
            "event_similarity": "{}",
            "dimension_scores": "{}",
            "trend_report": "{}",
        },
        "E002": {
            "event_id": "E002",
            "raw_content": "疑似分拆交易",
            "title": "分拆",
            "summary": "分拆",
            "status": "analyzed",
            "risk_level": "high",
            "risk_score": 0.91,
            "event_type": "反洗钱",
            "created_at": "2026-06-23T09:00:00",
            "updated_at": "2026-06-23T09:00:00",
            "matched_keywords": "[\"分拆交易\"]",
            "matched_persons": "[\"P102\"]",
            "event_similarity": "{}",
            "dimension_scores": "{}",
            "trend_report": "{}",
        },
    }

    result = store.list_events(page=1, page_size=20, risk_level="high", keyword="分拆")

    assert result["total"] == 1
    assert [item["event_id"] for item in result["items"]] == ["E002"]


@pytest.mark.asyncio
async def test_cleanup_duplicate_content_preserves_non_stashed_duplicate_events(
    store: EventsStore,
    client: FakeMilvusClient,
    now: datetime,
) -> None:
    stashed = make_event("STASHED", "客户 P102 工资入账后日常消费", now)
    pending = make_event("PENDING", "客户 P102   工资入账后日常消费", now)

    await store.stash_event(stashed, ["P102"])
    await store.upsert_event(pending, person_ids=["P102"], status="pending")

    deleted = store.cleanup_duplicate_content()

    assert deleted == 0
    assert sorted(client.rows["events"]) == ["PENDING", "STASHED"]
