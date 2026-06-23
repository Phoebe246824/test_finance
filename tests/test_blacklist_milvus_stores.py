from __future__ import annotations

import pytest

from blacklist.stores.event_samples_store import EventSamplesStore
from blacklist.stores.keywords_store import KeywordsStore
from blacklist.stores.persons_store import PersonsStore
from tests.fakes.fake_milvus import FakeMilvusClient


def fake_embed(text: str) -> list[float]:
    if "分拆交易" in text or "洗钱" in text:
        return [1.0, 0.0, 0.0]
    return [0.0, 1.0, 0.0]


@pytest.mark.asyncio
async def test_persons_store_crud_exact_lookup() -> None:
    client = FakeMilvusClient()
    store = PersonsStore(client)

    await store.append_person("p102", summary="客户P102", description="涉诈账户")

    assert await store.query_person("P102") == 1.0
    assert await store.get_person_stats() == {"P102": 1.0}
    assert await store.remove_person("P102") is True
    assert await store.query_person("P102") is None


@pytest.mark.asyncio
async def test_keywords_store_lists_enabled_keywords() -> None:
    client = FakeMilvusClient()
    store = KeywordsStore(client)

    await store.append_keyword("分拆交易", summary="AML")
    await store.append_keyword("工资入账", summary="normal")
    await store.remove_keyword("工资入账")

    assert await store.query_keywords() == ["分拆交易"]
    assert await store.get_keyword_stats() == {"分拆交易": 1.0}


@pytest.mark.asyncio
async def test_event_samples_store_semantic_match() -> None:
    client = FakeMilvusClient()
    store = EventSamplesStore(client, embedding_fn=fake_embed, embedding_dim=3)
    await store.append_event("S001", "AML样本", "疑似分拆交易与洗钱")
    await store.append_event("S002", "正常样本", "普通工资入账")

    match = await store.find_best_match("客户疑似分拆交易洗钱", threshold=0.5)

    assert match is not None
    assert match.hit is True
    assert match.event_id == "S001"
    assert match.summary == "AML样本"
    assert match.score > 0.5


@pytest.mark.asyncio
async def test_event_samples_store_returns_miss_below_threshold() -> None:
    client = FakeMilvusClient()
    store = EventSamplesStore(client, embedding_fn=fake_embed, embedding_dim=3)
    await store.append_event("S001", "正常样本", "普通工资入账")

    match = await store.find_best_match("分拆交易洗钱", threshold=0.95)

    assert match is None

