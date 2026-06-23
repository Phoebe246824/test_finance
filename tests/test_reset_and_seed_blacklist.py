from __future__ import annotations

import pytest

from scripts.reset_and_seed_blacklist import (
    EVENT_SEEDS,
    KEYWORD_SEEDS,
    PERSON_SEEDS,
    reset_milvus_collections,
    seed_blacklist_stores,
)
from tests.fakes.fake_milvus import FakeMilvusClient


def test_reset_milvus_collections_drops_existing_collections() -> None:
    client = FakeMilvusClient()
    for collection in (
        "events",
        "blacklist_persons",
        "blacklist_keywords",
        "blacklist_event_samples",
        "review_actions",
    ):
        client.collections.add(collection)

    dropped = reset_milvus_collections(client)

    assert dropped == [
        "blacklist_event_samples",
        "blacklist_keywords",
        "blacklist_persons",
        "events",
        "review_actions",
    ]
    assert client.collections == set()


@pytest.mark.asyncio
async def test_seed_blacklist_stores_writes_persons_keywords_and_samples() -> None:
    client = FakeMilvusClient()
    await seed_blacklist_stores(
        client=client,
        embedding_fn=lambda text: [1.0, 0.0, 0.0],
        embedding_dim=3,
    )

    assert set(client.rows["blacklist_persons"]) == set(PERSON_SEEDS)
    assert len(client.rows["blacklist_keywords"]) == len(KEYWORD_SEEDS)
    assert set(client.rows["blacklist_event_samples"]) == {
        event_id for event_id, _summary in EVENT_SEEDS
    }
    assert client.flushed == [
        "blacklist_persons",
        "blacklist_keywords",
        "blacklist_event_samples",
    ]
