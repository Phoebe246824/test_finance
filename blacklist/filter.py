"""
黑名单过滤器 — BlacklistFilter
=============================
对 NormalizedEvent 执行三合一 OR 匹配：
    1. 人员 ID 比对  → person_blacklist (Redis SortedSet)
    2. 敏感词比对    → keyword_blacklist (Redis SortedSet)
    3. 事件相似度比对 → event_blacklist (Redis Hash + Jina Rerank API)

OR 逻辑：任一维度命中 → PASS (True)；全未命中 → STASH (False)。
"""

import json
import logging
import os
from typing import Optional

import httpx
from redis.asyncio import Redis

from models import NormalizedEvent
from blacklist.manager import BlacklistManager

logger = logging.getLogger(__name__)


class BlacklistFilter:
    """三合一黑名单匹配器。"""

    def __init__(
        self,
        redis_client: Redis,
        similarity_threshold: Optional[float] = None,
        reranker_api_key: Optional[str] = None,
        reranker_base_url: Optional[str] = None,
        reranker_model: Optional[str] = None,
    ):
        self._manager = BlacklistManager(redis_client)
        self._similarity_threshold = similarity_threshold or float(
            os.getenv("BLACKLIST_EVENT_SIMILARITY_THRESHOLD", "0.5")
        )
        self._reranker_api_key = reranker_api_key or os.getenv("RERANKER_API_KEY", "")
        self._reranker_base_url = reranker_base_url or os.getenv(
            "RERANKER_BASE_URL", ""
        )
        self._reranker_model = reranker_model or os.getenv("RERANKER_MODEL", "")

    async def check(self, event: NormalizedEvent) -> tuple[bool, list[str]]:
        """
        执行三合一 OR 匹配。

        Returns:
            (should_proceed, matched_person_ids):
                should_proceed: True=PASS 进入 pipeline, False=STASH 存 Redis
                matched_person_ids: 命中的人员 ID 列表（用于后续自动积累）
        """
        matched_persons: list[str] = []

        # 1. 人员匹配
        person_hits = await self._check_persons(event)
        if person_hits:
            matched_persons.extend(person_hits)

        # 2. 敏感词匹配
        keyword_hit = await self._check_keywords(event)

        # 3. 事件相似度匹配
        event_hit = await self._check_event_similarity(event)

        should_proceed = bool(matched_persons or keyword_hit or event_hit)

        if should_proceed:
            logger.info(
                "blacklist PASS: event_id=%s, persons=%s, keyword=%s, event_sim=%s",
                event.event_id,
                matched_persons,
                keyword_hit,
                event_hit,
            )
        else:
            logger.info("blacklist STASH: event_id=%s, no matches", event.event_id)

        return should_proceed, matched_persons

    async def _check_persons(self, event: NormalizedEvent) -> list[str]:
        """从事件文本中提取人员 ID 并比对黑名单。"""
        from utils.text import extract_subject_id_numbers

        id_numbers = extract_subject_id_numbers(event.raw_content)
        hits = []
        for pid in id_numbers:
            score = await self._manager.query_person(pid)
            if score is not None:
                hits.append(pid)
                await self._manager.append_person(pid)
        return hits

    async def _check_keywords(self, event: NormalizedEvent) -> bool:
        """检查事件内容是否包含任一敏感词。"""
        keywords = await self._manager.query_keywords()
        if not keywords:
            return False

        content = event.raw_content
        for kw_bytes in keywords:
            kw = kw_bytes.decode() if isinstance(kw_bytes, bytes) else kw_bytes
            if kw in content:
                await self._manager.append_keyword(kw)
                return True
        return False

    async def _check_event_similarity(self, event: NormalizedEvent) -> bool:
        """
        使用 Jina Rerank API 比对事件黑名单中的摘要。
        最高分 > 阈值则判定为命中。
        """
        event_count = await self._manager.get_event_count()
        if event_count == 0:
            return False

        event_summaries = await self._manager._redis.hgetall(BlacklistManager.EVENT_KEY)
        if not event_summaries:
            return False

        summaries: list[str] = []
        event_ids: list[str] = []
        for eid, payload in event_summaries.items():
            eid_str = eid.decode() if isinstance(eid, bytes) else eid
            event_ids.append(eid_str)
            try:
                data = payload.decode() if isinstance(payload, bytes) else payload
                summaries.append(json.loads(data).get("summary", ""))
            except (json.JSONDecodeError, AttributeError):
                summaries.append("")

        if not summaries:
            return False

        try:
            max_score = await self._rerank_similarity(
                query=event.raw_content,
                documents=summaries,
            )
            if max_score > self._similarity_threshold:
                await self._manager.append_event(
                    event.event_id, event.summary or event.raw_content[:200]
                )
                return True
        except Exception as e:
            logger.warning("event similarity check failed: %s", e)

        return False

    async def _rerank_similarity(self, query: str, documents: list[str]) -> float:
        """调用 Jina Rerank API 获取最高相似度分数。"""
        if not self._reranker_api_key:
            logger.warning("RERANKER_API_KEY not set, skipping similarity check")
            return 0.0

        url = f"{self._reranker_base_url.rstrip('/')}/rerank"
        payload = {
            "model": self._reranker_model,
            "query": query,
            "documents": documents,
            "top_n": 1,
        }
        headers = {
            "Authorization": f"Bearer {self._reranker_api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", [])
        if not results:
            return 0.0

        return results[0].get("relevance_score", 0.0)

    async def append_person(self, id_number: str) -> int:
        """手动追加人员到黑名单。"""
        return await self._manager.append_person(id_number)

    async def append_keyword(self, keyword: str) -> int:
        """手动追加敏感词到黑名单。"""
        return await self._manager.append_keyword(keyword)

    async def append_event(self, event_id: str, summary: str) -> bool:
        """手动追加事件到黑名单。"""
        return await self._manager.append_event(event_id, summary)
