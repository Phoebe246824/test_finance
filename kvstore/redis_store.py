"""
Redis KV 暂存存储 — EventKVStore
===============================
人员 → 事件列表的 CRUD + TTL 管理。

方案 A: 一人一链表
    KEY:   person:<id_number>
    VALUE: JSON 数组 [{event1}, {event2}, ...]
    TTL:   可配置，默认 90 天
"""

import json
import logging
import os
from typing import Optional

from redis.asyncio import Redis

from models import NormalizedEvent

logger = logging.getLogger(__name__)


class EventKVStore:
    """人员事件 KV 暂存。"""

    def __init__(
        self,
        redis_client: Redis,
        ttl_days: Optional[int] = None,
    ):
        self._redis = redis_client
        self._ttl_seconds = (ttl_days or int(os.getenv("KV_TTL_DAYS", "90"))) * 86400

    def _key(self, id_number: str) -> str:
        return f"person:{id_number.upper()}"

    async def stash(self, event: NormalizedEvent, id_numbers: list[str]) -> int:
        """
        将事件存入指定人员 ID 的 KV 链表。
        一个事件涉及 N 个人 → 写入 N 条 key。
        """
        event_json = event.model_dump_json()
        ops = 0
        for pid in id_numbers:
            key = self._key(pid)
            await self._redis.rpush(key, event_json)
            await self._redis.expire(key, self._ttl_seconds)
            ops += 1
        logger.info(
            "stash event_id=%s to %d person keys, ttl=%ds",
            event.event_id,
            ops,
            self._ttl_seconds,
        )
        return ops

    async def fetch(
        self,
        id_numbers: list[str],
        max_per_person: Optional[int] = None,
        max_age_days: Optional[int] = None,
    ) -> list[dict]:
        """
        从指定人员 ID 的 KV 链表中取回历史事件。
        
        Args:
            id_numbers: 人员 ID 列表
            max_per_person: 每人最多取 N 条（默认 BATCH_MAX_PER_PERSON=20）
            max_age_days: 暂未实现（依赖 TTL 自然过期）
            
        Returns:
            list[dict]: 历史事件列表（已解析为 dict）
        """
        max_per = max_per_person or int(os.getenv("BATCH_MAX_PER_PERSON", "20"))
        events: list[dict] = []
        
        for pid in id_numbers:
            key = self._key(pid)
            raw_list = await self._redis.lrange(key, -max_per, -1)
            for raw in raw_list:
                try:
                    event_dict = json.loads(raw)
                    events.append(event_dict)
                except json.JSONDecodeError as e:
                    logger.warning("failed to parse stashed event: %s", e)
        
        logger.info("fetched %d events for %d persons", len(events), len(id_numbers))
        return events

    async def remove(self, id_numbers: list[str]) -> int:
        """
        删除指定人员 ID 的 KV 链表。
        用于批量构图成功后清理已处理的 KV。
        """
        keys = [self._key(pid) for pid in id_numbers]
        deleted = await self._redis.delete(*keys)
        logger.info("removed %d person keys", deleted)
        return deleted

    async def get_person_event_count(self, id_number: str) -> int:
        """获取指定人员的暂存事件数量。"""
        key = self._key(id_number)
        return await self._redis.llen(key)

    async def get_all_person_keys(self) -> list[str]:
        """获取所有人员 KV key（用于调试/监控）。"""
        keys: list[str] = []
        async for key in self._redis.scan_iter(match="person:*"):
            keys.append(key.decode() if isinstance(key, bytes) else key)
        return keys
