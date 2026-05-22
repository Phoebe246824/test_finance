"""测试 BlacklistStore Redis KV 暂存操作。"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from blacklist.store import BlacklistStore
from models import EventSource, NormalizedEvent


@pytest.fixture
def mock_redis():
    redis = MagicMock()
    redis.rpush = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=True)
    redis.lrange = AsyncMock(return_value=[])
    redis.delete = AsyncMock(return_value=0)
    redis.llen = AsyncMock(return_value=0)
    redis.scan_iter = AsyncMock()
    redis.scan_iter.return_value = iter([])
    return redis


@pytest.fixture
def store(mock_redis):
    return BlacklistStore(mock_redis, mock_redis, ttl_days=90)


@pytest.fixture
def sample_event():
    return NormalizedEvent(
        event_id="E001",
        source=EventSource.NEWS,
        raw_content="【P01# 小明】被发现",
        title="测试",
        timestamp=datetime.now(),
    )


class TestBlacklistStoreStash:
    @pytest.mark.asyncio
    async def test_stash_single_person(self, store, mock_redis, sample_event):
        """单人员事件应写入一条 key。"""
        ops = await store.stash_event(sample_event, ["P01"])
        assert ops == 1
        mock_redis.rpush.assert_called_once()
        mock_redis.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_stash_multiple_persons(self, store, mock_redis, sample_event):
        """多人员事件应写入 N 条 key。"""
        ops = await store.stash_event(sample_event, ["P01", "P02", "P03"])
        assert ops == 3
        assert mock_redis.rpush.call_count == 3
        assert mock_redis.expire.call_count == 3

    @pytest.mark.asyncio
    async def test_stash_empty_persons(self, store, mock_redis, sample_event):
        """空人员列表应返回 0 操作。"""
        ops = await store.stash_event(sample_event, [])
        assert ops == 0
        mock_redis.rpush.assert_not_called()

    @pytest.mark.asyncio
    async def test_stash_uppercase_key(self, store, mock_redis, sample_event):
        """key 中的 ID 应转为大写。"""
        await store.stash_event(sample_event, ["p01"])
        call_args = mock_redis.rpush.call_args
        assert call_args[0][0] == "person:P01"


class TestBlacklistStoreFetch:
    @pytest.mark.asyncio
    async def test_fetch_empty(self, store, mock_redis):
        """无数据应返回空列表。"""
        mock_redis.lrange.return_value = []
        result = await store.fetch_stashed_events(["P01"])
        assert result == []

    @pytest.mark.asyncio
    async def test_fetch_with_data(self, store, mock_redis):
        """有数据应正确解析。"""
        event_dict = {"event_id": "E001", "raw_content": "test"}
        mock_redis.lrange.return_value = [json.dumps(event_dict).encode()]
        result = await store.fetch_stashed_events(["P01"])
        assert len(result) == 1
        assert result[0]["event_id"] == "E001"

    @pytest.mark.asyncio
    async def test_fetch_multiple_persons(self, store, mock_redis):
        """多人员回捞时应按 event_id 去重。"""
        mock_redis.lrange.return_value = [
            json.dumps({"event_id": "E001"}).encode(),
        ]
        result = await store.fetch_stashed_events(["P01", "P02"])
        assert len(result) == 1
        assert result[0]["event_id"] == "E001"

    @pytest.mark.asyncio
    async def test_fetch_respects_max_per_person(self, store, mock_redis):
        """应传递 max_per_person 到 lrange。"""
        mock_redis.lrange.return_value = []
        await store.fetch_stashed_events(["P01"], max_per_person=5)
        mock_redis.lrange.assert_called_once_with("person:P01", -5, -1)

    @pytest.mark.asyncio
    async def test_fetch_invalid_json(self, store, mock_redis):
        """无效 JSON 应跳过不抛异常。"""
        mock_redis.lrange.return_value = [b"not valid json"]
        result = await store.fetch_stashed_events(["P01"])
        assert result == []


class TestBlacklistStoreRemove:
    @pytest.mark.asyncio
    async def test_remove_single(self, store, mock_redis):
        """删除单人员 key。"""
        mock_redis.delete.return_value = 1
        result = await store.remove_stashed_events(["P01"])
        assert result == 1
        mock_redis.delete.assert_called_once_with("person:P01")

    @pytest.mark.asyncio
    async def test_remove_multiple(self, store, mock_redis):
        """删除多人员 key。"""
        mock_redis.delete.return_value = 2
        result = await store.remove_stashed_events(["P01", "P02"])
        assert result == 2
        mock_redis.delete.assert_called_once_with("person:P01", "person:P02")


class TestBlacklistStoreHelpers:
    @pytest.mark.asyncio
    async def test_get_person_event_count(self, store, mock_redis):
        """获取人员事件数量。"""
        mock_redis.llen.return_value = 5
        result = await store.get_person_event_count("P01")
        assert result == 5

    @pytest.mark.asyncio
    async def test_get_all_person_keys(self, store, mock_redis):
        """获取所有人员 key。"""

        async def mock_scan_iter(match=None):
            for key in [b"person:P01", b"person:P02"]:
                yield key

        mock_redis.scan_iter = mock_scan_iter
        result = await store.get_all_person_keys()
        assert result == ["person:P01", "person:P02"]
