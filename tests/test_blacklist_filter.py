from __future__ import annotations

import pytest

from blacklist.filter import BlacklistFilter
from blacklist.stores.event_samples_store import EventSampleMatch
from models import EventSource, NormalizedEvent


class FakePersonsStore:
    def __init__(self, hits: set[str] | None = None) -> None:
        self.hits = {item.upper() for item in hits or set()}

    async def query_person(self, id_number: str) -> float | None:
        return 1.0 if id_number.upper() in self.hits else None


class FakeKeywordsStore:
    def __init__(self, keywords: list[str] | None = None) -> None:
        self.keywords = keywords or []

    async def query_keywords(self) -> list[str]:
        return self.keywords


class FakeSamplesStore:
    def __init__(self, match: EventSampleMatch | None = None) -> None:
        self.match = match

    async def find_best_match(
        self,
        query: str,
        *,
        threshold: float,
    ) -> EventSampleMatch | None:
        return self.match


@pytest.fixture
def sample_event() -> NormalizedEvent:
    return NormalizedEvent(
        event_id="E001",
        source=EventSource.NEWS,
        raw_content="【P01# 小明】被发现参与非法活动",
        title="测试事件",
        summary="小明参与非法活动",
    )


@pytest.fixture
def filter_instance() -> BlacklistFilter:
    return BlacklistFilter(
        persons_store=FakePersonsStore(),
        keywords_store=FakeKeywordsStore(),
        samples_store=FakeSamplesStore(),
        similarity_threshold=0.5,
    )


@pytest.mark.asyncio
async def test_person_not_in_blacklist(
    filter_instance: BlacklistFilter,
    sample_event: NormalizedEvent,
) -> None:
    hits = await filter_instance._check_persons(sample_event)
    assert hits == []


@pytest.mark.asyncio
async def test_person_in_blacklist(sample_event: NormalizedEvent) -> None:
    filter_instance = BlacklistFilter(
        persons_store=FakePersonsStore({"P01"}),
        keywords_store=FakeKeywordsStore(),
        samples_store=FakeSamplesStore(),
        similarity_threshold=0.5,
    )

    hits = await filter_instance._check_persons(sample_event)

    assert hits == ["P01"]


@pytest.mark.asyncio
async def test_no_person_in_text(filter_instance: BlacklistFilter) -> None:
    event = NormalizedEvent(
        event_id="E002",
        source=EventSource.NEWS,
        raw_content="今天天气很好，没有特定人员",
        title="无人员事件",
    )

    hits = await filter_instance._check_persons(event)

    assert hits == []


@pytest.mark.asyncio
async def test_no_keywords_in_db(
    filter_instance: BlacklistFilter,
    sample_event: NormalizedEvent,
) -> None:
    result = await filter_instance._check_keywords(sample_event)
    assert result == []


@pytest.mark.asyncio
async def test_keyword_matches(sample_event: NormalizedEvent) -> None:
    filter_instance = BlacklistFilter(
        persons_store=FakePersonsStore(),
        keywords_store=FakeKeywordsStore(["非法"]),
        samples_store=FakeSamplesStore(),
        similarity_threshold=0.5,
    )

    result = await filter_instance._check_keywords(sample_event)

    assert result == ["非法"]


@pytest.mark.asyncio
async def test_keyword_no_match(sample_event: NormalizedEvent) -> None:
    filter_instance = BlacklistFilter(
        persons_store=FakePersonsStore(),
        keywords_store=FakeKeywordsStore(["无关词"]),
        samples_store=FakeSamplesStore(),
        similarity_threshold=0.5,
    )

    result = await filter_instance._check_keywords(sample_event)

    assert result == []


@pytest.mark.asyncio
async def test_no_event_sample_match(
    filter_instance: BlacklistFilter,
    sample_event: NormalizedEvent,
) -> None:
    result = await filter_instance._check_event_similarity(sample_event)
    assert result is False


@pytest.mark.asyncio
async def test_event_similarity_details_come_from_event_sample_store(
    sample_event: NormalizedEvent,
) -> None:
    filter_instance = BlacklistFilter(
        persons_store=FakePersonsStore(),
        keywords_store=FakeKeywordsStore(),
        samples_store=FakeSamplesStore(
            EventSampleMatch(
                hit=True,
                score=0.91,
                event_id="E-FIN-AML-001",
                summary="疑似分拆交易与洗钱",
                threshold=0.5,
            )
        ),
        similarity_threshold=0.5,
    )

    result = await filter_instance._check_event_similarity_details(sample_event)

    assert result.hit is True
    assert result.score == pytest.approx(0.91)
    assert result.event_id == "E-FIN-AML-001"
    assert result.summary == "疑似分拆交易与洗钱"


@pytest.mark.asyncio
async def test_all_miss_stash(
    filter_instance: BlacklistFilter,
    sample_event: NormalizedEvent,
) -> None:
    should_proceed, matched_persons, matched_keywords, event_hit = (
        await filter_instance.check(sample_event)
    )

    assert should_proceed is False
    assert matched_persons == []
    assert matched_keywords == []
    assert event_hit is False


@pytest.mark.asyncio
async def test_person_hit_pass(sample_event: NormalizedEvent) -> None:
    filter_instance = BlacklistFilter(
        persons_store=FakePersonsStore({"P01"}),
        keywords_store=FakeKeywordsStore(),
        samples_store=FakeSamplesStore(),
        similarity_threshold=0.5,
    )

    should_proceed, matched_persons, matched_keywords, event_hit = (
        await filter_instance.check(sample_event)
    )

    assert should_proceed is True
    assert matched_persons == ["P01"]
    assert matched_keywords == []
    assert event_hit is False


@pytest.mark.asyncio
async def test_keyword_hit_pass() -> None:
    event = NormalizedEvent(
        event_id="E003",
        source=EventSource.NEWS,
        raw_content="某公司发布新产品",
        title="无人员事件",
    )
    filter_instance = BlacklistFilter(
        persons_store=FakePersonsStore(),
        keywords_store=FakeKeywordsStore(["新产品"]),
        samples_store=FakeSamplesStore(),
        similarity_threshold=0.5,
    )

    should_proceed, matched_persons, matched_keywords, event_hit = (
        await filter_instance.check(event)
    )

    assert should_proceed is True
    assert matched_persons == []
    assert matched_keywords == ["新产品"]
    assert event_hit is False


@pytest.mark.asyncio
async def test_keyword_hit_pass_without_person_ids() -> None:
    event = NormalizedEvent(
        event_id="E004",
        source=EventSource.NEWS,
        raw_content="某工业园区仓库发生爆炸，周边企业员工已紧急疏散。",
        title="爆炸事件",
    )
    filter_instance = BlacklistFilter(
        persons_store=FakePersonsStore(),
        keywords_store=FakeKeywordsStore(["爆炸", "制裁"]),
        samples_store=FakeSamplesStore(),
        similarity_threshold=0.5,
    )

    should_proceed, matched_persons, matched_keywords, event_hit = (
        await filter_instance.check(event)
    )

    assert should_proceed is True
    assert matched_persons == []
    assert matched_keywords == ["爆炸"]
    assert event_hit is False

