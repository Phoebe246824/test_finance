"""
黑名单管理器 — BlacklistManager
===============================
负责加载、查询、追加黑名单数据（人员库、敏感词库、高危事件库）。

Redis 数据结构:
    person_blacklist:   SortedSet { id_number -> hit_count }
    keyword_blacklist:  SortedSet { keyword -> hit_count }
    event_blacklist:    Hash { event_id -> summary_json }
"""

import json
import logging
from typing import Optional

from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class BlacklistManager:
    """黑名单 CRUD 操作封装。"""

    PERSON_KEY = "person_blacklist"
    KEYWORD_KEY = "keyword_blacklist"
    EVENT_KEY = "event_blacklist"

    def __init__(self, redis_client: Redis):
        self._redis = redis_client

    async def query_person(self, id_number: str) -> Optional[float]:
        """查询人员是否在黑名单中，返回命中次数（None 表示未命中）。"""
        score = await self._redis.zscore(self.PERSON_KEY, id_number.upper())
        return score

    async def query_keywords(self) -> list[str]:
        """获取所有敏感词。"""
        return await self._redis.zrange(self.KEYWORD_KEY, 0, -1)

    async def query_event(self, event_id: str) -> Optional[dict]:
        """查询高危事件摘要。"""
        raw = await self._redis.hget(self.EVENT_KEY, event_id)
        if raw is None:
            return None
        return json.loads(raw)

    async def append_person(self, id_number: str) -> int:
        """追加人员到黑名单，返回新的命中次数。"""
        return await self._redis.zincrby(self.PERSON_KEY, 1, id_number.upper())

    async def append_keyword(self, keyword: str) -> int:
        """追加敏感词到黑名单，返回新的命中次数。"""
        return await self._redis.zincrby(self.KEYWORD_KEY, 1, keyword)

    async def append_event(self, event_id: str, summary: str) -> bool:
        """追加高危事件摘要到黑名单。"""
        payload = json.dumps({"event_id": event_id, "summary": summary}, ensure_ascii=False)
        return await self._redis.hset(self.EVENT_KEY, event_id, payload)

    async def remove_person(self, id_number: str) -> bool:
        """从人员黑名单中移除。"""
        return bool(await self._redis.zrem(self.PERSON_KEY, id_number.upper()))

    async def remove_keyword(self, keyword: str) -> bool:
        """从敏感词库中移除。"""
        return bool(await self._redis.zrem(self.KEYWORD_KEY, keyword))

    async def remove_event(self, event_id: str) -> bool:
        """从高危事件库中移除。"""
        return bool(await self._redis.hdel(self.EVENT_KEY, event_id))

    async def get_person_stats(self) -> dict[str, float]:
        """获取所有人员及其命中次数。"""
        items = await self._redis.zrange(self.PERSON_KEY, 0, -1, withscores=True)
        return {pid.decode() if isinstance(pid, bytes) else pid: score for pid, score in items}

    async def get_keyword_stats(self) -> dict[str, float]:
        """获取所有敏感词及其命中次数。"""
        items = await self._redis.zrange(self.KEYWORD_KEY, 0, -1, withscores=True)
        return {kw.decode() if isinstance(kw, bytes) else kw: score for kw, score in items}

    async def get_event_count(self) -> int:
        """获取高危事件库中的事件数量。"""
        return await self._redis.hlen(self.EVENT_KEY)
