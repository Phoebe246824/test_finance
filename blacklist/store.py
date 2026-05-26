import json
import logging
from typing import Optional

from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class BlacklistStore:
    """Redis-backed blacklist CRUD store."""

    PERSON_KEY = "person_blacklist"
    KEYWORD_KEY = "keyword_blacklist"
    EVENT_KEY = "event_blacklist"

    def __init__(
        self,
        blacklist_redis: Redis,
    ):
        self._blacklist_redis = blacklist_redis

    async def query_person(self, id_number: str) -> Optional[float]:
        return await self._blacklist_redis.zscore(self.PERSON_KEY, id_number.upper())

    async def query_keywords(self) -> list[bytes | str]:
        return await self._blacklist_redis.zrange(self.KEYWORD_KEY, 0, -1)

    async def query_event(self, event_id: str) -> Optional[dict]:
        raw = await self._blacklist_redis.hget(self.EVENT_KEY, event_id)
        if raw is None:
            return None
        data = raw.decode() if isinstance(raw, bytes) else raw
        return json.loads(data)

    async def append_person(self, id_number: str) -> int:
        return await self._blacklist_redis.zincrby(
            self.PERSON_KEY, 1, id_number.upper()
        )

    async def append_keyword(self, keyword: str) -> int:
        return await self._blacklist_redis.zincrby(self.KEYWORD_KEY, 1, keyword)

    async def append_event(self, event_id: str, summary: str) -> int:
        payload = json.dumps(
            {"event_id": event_id, "summary": summary}, ensure_ascii=False
        )
        return await self._blacklist_redis.hset(self.EVENT_KEY, event_id, payload)

    async def remove_person(self, id_number: str) -> bool:
        return bool(
            await self._blacklist_redis.zrem(self.PERSON_KEY, id_number.upper())
        )

    async def remove_keyword(self, keyword: str) -> bool:
        return bool(await self._blacklist_redis.zrem(self.KEYWORD_KEY, keyword))

    async def remove_event(self, event_id: str) -> bool:
        return bool(await self._blacklist_redis.hdel(self.EVENT_KEY, event_id))

    async def get_person_stats(self) -> dict[str, float]:
        items = await self._blacklist_redis.zrange(
            self.PERSON_KEY, 0, -1, withscores=True
        )
        return {
            pid.decode() if isinstance(pid, bytes) else pid: score
            for pid, score in items
        }

    async def get_keyword_stats(self) -> dict[str, float]:
        items = await self._blacklist_redis.zrange(
            self.KEYWORD_KEY, 0, -1, withscores=True
        )
        return {
            kw.decode() if isinstance(kw, bytes) else kw: score for kw, score in items
        }

    async def get_event_count(self) -> int:
        return await self._blacklist_redis.hlen(self.EVENT_KEY)

    async def get_event_summaries(self) -> dict[str, str]:
        raw_map = await self._blacklist_redis.hgetall(self.EVENT_KEY)
        result: dict[str, str] = {}
        for eid, payload in raw_map.items():
            eid_str = eid.decode() if isinstance(eid, bytes) else eid
            payload_str = payload.decode() if isinstance(payload, bytes) else payload
            result[eid_str] = payload_str
        return result
