"""测试 BlacklistFilter 三合一 OR 匹配逻辑。"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from blacklist.filter import BlacklistFilter
from models import EventSource, NormalizedEvent


@pytest.fixture
def mock_redis():
    redis = MagicMock()
    redis.zscore = AsyncMock(return_value=None)
    redis.zrange = AsyncMock(return_value=[])
    redis.zincrby = AsyncMock(return_value=1)
    redis.hget = AsyncMock(return_value=None)
    redis.hset = AsyncMock(return_value=1)
    redis.hlen = AsyncMock(return_value=0)
    redis.hgetall = AsyncMock(return_value={})
    return redis


@pytest.fixture
def sample_event():
    return NormalizedEvent(
        event_id="E001",
        source=EventSource.NEWS,
        raw_content="【P01# 小明】被发现参与非法活动",
        title="测试事件",
        summary="小明参与非法活动",
    )


@pytest.fixture
def filter_instance(mock_redis):
    return BlacklistFilter(
        redis_client=mock_redis,
        similarity_threshold=0.5,
        reranker_api_key="",
    )


class TestBlacklistFilterPersonCheck:
    @pytest.mark.asyncio
    async def test_person_not_in_blacklist(
        self, filter_instance, mock_redis, sample_event
    ):
        """人员不在黑名单中不应命中。"""
        mock_redis.zscore.return_value = None
        hits = await filter_instance._check_persons(sample_event)
        assert hits == []

    @pytest.mark.asyncio
    async def test_person_in_blacklist(self, filter_instance, mock_redis, sample_event):
        """人员在黑名单中应命中并自动积累。"""
        mock_redis.zscore.return_value = 3.0
        hits = await filter_instance._check_persons(sample_event)
        assert hits == ["P01"]
        mock_redis.zincrby.assert_called_with("person_blacklist", 1, "P01")

    @pytest.mark.asyncio
    async def test_no_person_in_text(self, filter_instance, mock_redis):
        """文本中无可识别人员 ID 应返回空。"""
        event = NormalizedEvent(
            event_id="E002",
            source=EventSource.NEWS,
            raw_content="今天天气很好，没有特定人员",
            title="无人员事件",
        )
        hits = await filter_instance._check_persons(event)
        assert hits == []


class TestBlacklistFilterKeywordCheck:
    @pytest.mark.asyncio
    async def test_no_keywords_in_db(self, filter_instance, mock_redis, sample_event):
        """敏感词库为空不应命中。"""
        mock_redis.zrange.return_value = []
        result = await filter_instance._check_keywords(sample_event)
        assert result is False

    @pytest.mark.asyncio
    async def test_keyword_matches(self, filter_instance, mock_redis, sample_event):
        """内容包含敏感词应命中。"""
        mock_redis.zrange.return_value = ["非法".encode()]
        result = await filter_instance._check_keywords(sample_event)
        assert result is True
        mock_redis.zincrby.assert_called_with("keyword_blacklist", 1, "非法")

    @pytest.mark.asyncio
    async def test_keyword_no_match(self, filter_instance, mock_redis, sample_event):
        """内容不包含敏感词不应命中。"""
        mock_redis.zrange.return_value = ["无关词".encode()]
        result = await filter_instance._check_keywords(sample_event)
        assert result is False


class TestBlacklistFilterEventSimilarity:
    @pytest.mark.asyncio
    async def test_no_events_in_db(self, filter_instance, mock_redis, sample_event):
        """事件黑名单为空不应命中。"""
        mock_redis.hlen.return_value = 0
        result = await filter_instance._check_event_similarity(sample_event)
        assert result is False

    @pytest.mark.asyncio
    async def test_no_reranker_key(self, filter_instance, mock_redis, sample_event):
        """未配置 Reranker API Key 应跳过相似度检查。"""
        mock_redis.hlen.return_value = 1
        mock_redis.hgetall.return_value = {
            b"E999": json.dumps({"summary": "test"}).encode()
        }
        result = await filter_instance._check_event_similarity(sample_event)
        assert result is False


class TestBlacklistFilterCheck:
    @pytest.mark.asyncio
    async def test_all_miss_stash(self, filter_instance, mock_redis, sample_event):
        """三维度均未命中应返回 STASH (False)。"""
        mock_redis.zscore.return_value = None
        mock_redis.zrange.return_value = []
        mock_redis.hlen.return_value = 0
        should_proceed, matched = await filter_instance.check(sample_event)
        assert should_proceed is False
        assert matched == []

    @pytest.mark.asyncio
    async def test_person_hit_pass(self, filter_instance, mock_redis, sample_event):
        """人员命中应返回 PASS (True)。"""
        mock_redis.zscore.return_value = 2.0
        mock_redis.zrange.return_value = []
        mock_redis.hlen.return_value = 0
        should_proceed, matched = await filter_instance.check(sample_event)
        assert should_proceed is True
        assert matched == ["P01"]

    @pytest.mark.asyncio
    async def test_keyword_hit_pass(self, filter_instance, mock_redis):
        """敏感词命中应返回 PASS。"""
        event = NormalizedEvent(
            event_id="E003",
            source=EventSource.NEWS,
            raw_content="某公司发布新产品",
            title="无人员事件",
        )
        mock_redis.zscore.return_value = None
        mock_redis.zrange.return_value = ["新产品".encode()]
        mock_redis.hlen.return_value = 0
        filter_instance = BlacklistFilter(mock_redis, reranker_api_key="")
        should_proceed, matched = await filter_instance.check(event)
        assert should_proceed is True
        assert matched == []

    @pytest.mark.asyncio
    async def test_keyword_hit_pass_without_person_ids(
        self, filter_instance, mock_redis
    ):
        """无人员但命中敏感词时仍应 PASS。"""
        event = NormalizedEvent(
            event_id="E004",
            source=EventSource.NEWS,
            raw_content="某工业园区仓库发生爆炸，周边企业员工已紧急疏散。",
            title="爆炸事件",
        )
        mock_redis.zscore.return_value = None
        mock_redis.zrange.return_value = ["爆炸".encode(), "制裁".encode()]
        mock_redis.hlen.return_value = 0

        should_proceed, matched = await filter_instance.check(event)

        assert should_proceed is True
        assert matched == []
        mock_redis.zincrby.assert_called_with("keyword_blacklist", 1, "爆炸")
