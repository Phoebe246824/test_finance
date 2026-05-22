"""测试 BlacklistManager 黑名单 CRUD 操作。"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from blacklist.manager import BlacklistManager


@pytest.fixture
def mock_redis():
    """创建 Redis 异步 mock。"""
    redis = MagicMock()
    redis.zscore = AsyncMock(return_value=None)
    redis.zrange = AsyncMock(return_value=[])
    redis.zincrby = AsyncMock(return_value=1)
    redis.zrem = AsyncMock(return_value=1)
    redis.hget = AsyncMock(return_value=None)
    redis.hset = AsyncMock(return_value=1)
    redis.hdel = AsyncMock(return_value=1)
    redis.hlen = AsyncMock(return_value=0)
    redis.hgetall = AsyncMock(return_value={})
    return redis


@pytest.fixture
def manager(mock_redis):
    return BlacklistManager(mock_redis)


class TestBlacklistManagerPerson:
    @pytest.mark.asyncio
    async def test_query_person_not_in_list(self, manager, mock_redis):
        """人员不在黑名单中应返回 None。"""
        mock_redis.zscore.return_value = None
        result = await manager.query_person("P001")
        assert result is None

    @pytest.mark.asyncio
    async def test_query_person_in_list(self, manager, mock_redis):
        """人员在黑名单中应返回命中次数。"""
        mock_redis.zscore.return_value = 5.0
        result = await manager.query_person("P001")
        assert result == 5.0

    @pytest.mark.asyncio
    async def test_query_person_uppercase(self, manager, mock_redis):
        """查询时应自动转大写。"""
        await manager.query_person("p001")
        mock_redis.zscore.assert_called_once_with("person_blacklist", "P001")

    @pytest.mark.asyncio
    async def test_append_person(self, manager, mock_redis):
        """追加人员应调用 zincrby。"""
        result = await manager.append_person("P001")
        assert result == 1
        mock_redis.zincrby.assert_called_once_with("person_blacklist", 1, "P001")

    @pytest.mark.asyncio
    async def test_remove_person(self, manager, mock_redis):
        """移除人员应调用 zrem。"""
        result = await manager.remove_person("P001")
        assert result is True
        mock_redis.zrem.assert_called_once_with("person_blacklist", "P001")

    @pytest.mark.asyncio
    async def test_get_person_stats(self, manager, mock_redis):
        """获取人员统计应返回字典。"""
        mock_redis.zrange.return_value = [(b"P001", 5.0), (b"P002", 3.0)]
        result = await manager.get_person_stats()
        assert result == {"P001": 5.0, "P002": 3.0}


class TestBlacklistManagerKeyword:
    @pytest.mark.asyncio
    async def test_query_keywords_empty(self, manager, mock_redis):
        """敏感词库为空应返回空列表。"""
        mock_redis.zrange.return_value = []
        result = await manager.query_keywords()
        assert result == []

    @pytest.mark.asyncio
    async def test_query_keywords_has_items(self, manager, mock_redis):
        """敏感词库有数据应返回列表。"""
        mock_redis.zrange.return_value = ["制裁".encode(), "疫情".encode()]
        result = await manager.query_keywords()
        assert result == ["制裁".encode(), "疫情".encode()]

    @pytest.mark.asyncio
    async def test_append_keyword(self, manager, mock_redis):
        """追加敏感词应调用 zincrby。"""
        result = await manager.append_keyword("制裁")
        assert result == 1
        mock_redis.zincrby.assert_called_once_with("keyword_blacklist", 1, "制裁")

    @pytest.mark.asyncio
    async def test_remove_keyword(self, manager, mock_redis):
        """移除敏感词应调用 zrem。"""
        result = await manager.remove_keyword("制裁")
        assert result is True


class TestBlacklistManagerEvent:
    @pytest.mark.asyncio
    async def test_query_event_not_found(self, manager, mock_redis):
        """事件不在黑名单中应返回 None。"""
        mock_redis.hget.return_value = None
        result = await manager.query_event("E001")
        assert result is None

    @pytest.mark.asyncio
    async def test_query_event_found(self, manager, mock_redis):
        """事件在黑名单中应返回解析后的字典。"""
        payload = json.dumps({"event_id": "E001", "summary": "test"})
        mock_redis.hget.return_value = payload.encode()
        result = await manager.query_event("E001")
        assert result == {"event_id": "E001", "summary": "test"}

    @pytest.mark.asyncio
    async def test_append_event(self, manager, mock_redis):
        """追加事件应调用 hset。"""
        result = await manager.append_event("E001", "test summary")
        assert result == 1
        mock_redis.hset.assert_called_once()
        call_args = mock_redis.hset.call_args
        assert call_args[0][0] == "event_blacklist"
        assert call_args[0][1] == "E001"

    @pytest.mark.asyncio
    async def test_remove_event(self, manager, mock_redis):
        """移除事件应调用 hdel。"""
        result = await manager.remove_event("E001")
        assert result is True

    @pytest.mark.asyncio
    async def test_get_event_count(self, manager, mock_redis):
        """获取事件数量应调用 hlen。"""
        mock_redis.hlen.return_value = 10
        result = await manager.get_event_count()
        assert result == 10
