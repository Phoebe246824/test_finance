from datetime import datetime, timedelta

import pytest

from blacklist.milvus_stash import MilvusStashStore
from models import EventSource, NormalizedEvent


class FakeMilvusClient:
    def __init__(self):
        self.rows: dict[str, dict] = {}
        self.created_collections: list[dict] = []

    def has_collection(self, collection_name: str) -> bool:
        return bool(self.created_collections)

    def create_collection(self, **kwargs) -> None:
        self.created_collections.append(kwargs)

    def create_index(self, **kwargs) -> None:
        return None

    def load_collection(self, **kwargs) -> None:
        return None

    def upsert(self, collection_name: str, data: list[dict]) -> dict:
        for row in data:
            self.rows[row["event_id"]] = dict(row)
        return {"upsert_count": len(data)}

    def query(
        self,
        collection_name: str,
        filter: str,
        output_fields: list[str],
        limit: int | None = None,
    ) -> list[dict]:
        rows = [
            {field: row.get(field) for field in output_fields}
            for row in self.rows.values()
        ]
        return rows[:limit] if limit is not None else rows

    def search(
        self,
        collection_name: str,
        data: list[list[float]],
        anns_field: str,
        filter: str,
        limit: int,
        output_fields: list[str],
    ) -> list[list[dict]]:
        query_vector = data[0]

        def score(row: dict) -> float:
            return sum(a * b for a, b in zip(query_vector, row["embedding"]))

        ranked = sorted(self.rows.values(), key=score, reverse=True)
        hits = []
        for row in ranked[:limit]:
            hits.append(
                {
                    "id": row["event_id"],
                    "distance": score(row),
                    "entity": {field: row.get(field) for field in output_fields},
                }
            )
        return [hits]

    def delete(self, collection_name: str, filter: str) -> dict:
        event_ids = [
            item.strip().strip('"').strip("'")
            for item in filter.split("[", 1)[1].split("]", 1)[0].split(",")
            if item.strip()
        ]
        deleted = 0
        for event_id in event_ids:
            if event_id in self.rows:
                del self.rows[event_id]
                deleted += 1
        return {"delete_count": deleted}


def fake_embed(text: str) -> list[float]:
    if "alpha" in text:
        return [1.0, 0.0, 0.0]
    if "beta" in text:
        return [0.0, 1.0, 0.0]
    return [0.0, 0.0, 1.0]


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 5, 26, 12, 0, 0)


@pytest.fixture
def client() -> FakeMilvusClient:
    return FakeMilvusClient()


@pytest.fixture
def store(client, now) -> MilvusStashStore:
    return MilvusStashStore(
        client=client,
        embedding_fn=fake_embed,
        now_fn=lambda: now,
        ttl_days=30,
    )


@pytest.mark.asyncio
async def test_stash_event_initializes_collection_before_first_write(client, now):
    store = MilvusStashStore(
        client=client,
        embedding_fn=fake_embed,
        now_fn=lambda: now,
        ttl_days=30,
        embedding_dim=3,
    )

    await store.stash_event(make_event("E001", "alpha P01 low signal", now), ["P01"])

    assert client.created_collections
    collection = client.created_collections[0]
    assert collection["collection_name"] == "stashed_events"
    assert collection["dimension"] == 3


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


@pytest.mark.asyncio
async def test_stash_event_writes_searchable_document(store, client, now):
    event = make_event("E001", "alpha P01 low signal", now)

    result = await store.stash_event(event, ["p01"])

    assert result == 1
    row = client.rows["E001"]
    assert row["event_id"] == "E001"
    assert row["person_ids"] == ["P01"]
    assert row["raw_content"] == "alpha P01 low signal"
    assert row["created_at"] == now.isoformat()
    assert row["expire_at"] == (now + timedelta(days=30)).isoformat()
    assert row["embedding"] == [1.0, 0.0, 0.0]
    assert row["is_graph_built"] is False


@pytest.mark.asyncio
async def test_stash_event_allows_empty_person_ids(store, client, now):
    event = make_event("E001", "alpha no person", now)

    result = await store.stash_event(event, [])

    assert result == 1
    assert client.rows["E001"]["person_ids"] == []


@pytest.mark.asyncio
async def test_fetch_related_events_returns_union_with_match_sources(
    store, client, now
):
    await store.stash_event(make_event("E001", "alpha same person", now), ["P01"])
    await store.stash_event(make_event("E002", "alpha semantic only", now), ["P99"])
    await store.stash_event(make_event("E003", "beta same person", now), ["P01"])
    trigger = make_event("E999", "alpha trigger P01", now)

    results = await store.fetch_related_events(
        trigger,
        ["P01"],
        top_k_semantic=2,
        max_per_person=10,
    )

    assert [item["event_id"] for item in results] == ["E001", "E003", "E002"]
    assert [item["match_source"] for item in results] == [
        "both",
        "person_match",
        "semantic_match",
    ]


@pytest.mark.asyncio
async def test_fetch_related_events_filters_current_expired_and_built_events(
    store, client, now
):
    await store.stash_event(make_event("CURRENT", "alpha current", now), ["P01"])
    await store.stash_event(
        make_event("EXPIRED", "alpha expired", now - timedelta(days=40)), ["P01"]
    )
    await store.stash_event(make_event("BUILT", "alpha built", now), ["P01"])
    await store.mark_events_graph_built(["BUILT"])
    await store.stash_event(make_event("VALID", "alpha valid", now), ["P01"])

    results = await store.fetch_related_events(
        make_event("CURRENT", "alpha trigger", now),
        ["P01"],
        top_k_semantic=10,
        max_per_person=10,
    )

    assert [item["event_id"] for item in results] == ["VALID"]


@pytest.mark.asyncio
async def test_mark_events_graph_built_prevents_future_recall(store, now):
    await store.stash_event(make_event("E001", "alpha same person", now), ["P01"])

    await store.mark_events_graph_built(["E001"])
    results = await store.fetch_related_events(
        make_event("E999", "alpha trigger", now),
        ["P01"],
        top_k_semantic=10,
        max_per_person=10,
    )

    assert results == []
