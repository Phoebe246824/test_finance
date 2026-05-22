import json
import logging
import os
from typing import Optional

from redis.asyncio import Redis

from models import NormalizedEvent

logger = logging.getLogger(__name__)


class BlacklistStore:
    """统一管理黑名单与人员事件暂存。"""

    PERSON_KEY = "person_blacklist"
    KEYWORD_KEY = "keyword_blacklist"
    EVENT_KEY = "event_blacklist"

    def __init__(
        self,
        blacklist_redis: Redis,
        stash_redis: Optional[Redis] = None,
        ttl_days: Optional[int] = None,
    ):
        self._blacklist_redis = blacklist_redis
        self._stash_redis = stash_redis
        self._ttl_seconds = (ttl_days or int(os.getenv("KV_TTL_DAYS", "90"))) * 86400

    def _person_stash_key(self, id_number: str) -> str:
        return f"person:{id_number.upper()}"

    def _require_stash_redis(self) -> Redis:
        if self._stash_redis is None:
            raise RuntimeError(
                "stash redis client is required for event stash operations"
            )
        return self._stash_redis

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

    async def stash_event(self, event: NormalizedEvent, id_numbers: list[str]) -> int:
        redis = self._require_stash_redis()
        event_json = event.model_dump_json()
        ops = 0
        for pid in id_numbers:
            key = self._person_stash_key(pid)
            await redis.rpush(key, event_json)
            await redis.expire(key, self._ttl_seconds)
            ops += 1
        logger.info(
            "stash event_id=%s to %d person keys, ttl=%ds",
            event.event_id,
            ops,
            self._ttl_seconds,
        )
        return ops

    async def fetch_stashed_events(
        self,
        id_numbers: list[str],
        max_per_person: Optional[int] = None,
    ) -> list[dict]:
        redis = self._require_stash_redis()
        max_per = max_per_person or int(os.getenv("BATCH_MAX_PER_PERSON", "20"))
        events: list[dict] = []
        seen_event_ids: set[str] = set()

        for pid in id_numbers:
            key = self._person_stash_key(pid)
            raw_list = await redis.lrange(key, -max_per, -1)
            for raw in raw_list:
                try:
                    payload = raw.decode() if isinstance(raw, bytes) else raw
                    event_dict = json.loads(payload)
                except json.JSONDecodeError as e:
                    logger.warning("failed to parse stashed event: %s", e)
                    continue

                event_id = event_dict.get("event_id")
                if event_id:
                    if event_id in seen_event_ids:
                        continue
                    seen_event_ids.add(event_id)
                events.append(event_dict)

        logger.info("fetched %d events for %d persons", len(events), len(id_numbers))
        return events

    async def remove_stashed_events(self, id_numbers: list[str]) -> int:
        redis = self._require_stash_redis()
        keys = [self._person_stash_key(pid) for pid in id_numbers]
        if not keys:
            return 0
        deleted = await redis.delete(*keys)
        logger.info("removed %d person keys", deleted)
        return deleted

    async def get_person_event_count(self, id_number: str) -> int:
        redis = self._require_stash_redis()
        return await redis.llen(self._person_stash_key(id_number))

    async def get_all_person_keys(self) -> list[str]:
        redis = self._require_stash_redis()
        keys: list[str] = []
        async for key in redis.scan_iter(match="person:*"):
            keys.append(key.decode() if isinstance(key, bytes) else key)
        return keys

