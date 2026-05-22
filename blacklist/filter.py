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

from blacklist.store import BlacklistStore
from models import NormalizedEvent

logger = logging.getLogger(__name__)


class BlacklistFilter:
    """三合一黑名单匹配器。"""

    def __init__(
        self,
        store: BlacklistStore,
        similarity_threshold: Optional[float] = None,
        reranker_api_key: Optional[str] = None,
        reranker_base_url: Optional[str] = None,
        reranker_model: Optional[str] = None,
    ):
        self._store = store
        self._similarity_threshold = similarity_threshold or float(
            os.getenv("BLACKLIST_EVENT_SIMILARITY_THRESHOLD", "0.5")
        )
        self._reranker_api_key = reranker_api_key or os.getenv("RERANKER_API_KEY", "")
        self._reranker_base_url = reranker_base_url or os.getenv(
            "RERANKER_BASE_URL", ""
        )
        self._reranker_model = reranker_model or os.getenv("RERANKER_MODEL", "")

    async def check(self, event: NormalizedEvent) -> tuple[bool, list[str], list[str], bool]:
        """
        执行三合一 OR 匹配。

        Returns:
            (should_proceed, matched_person_ids, matched_keywords, event_similarity_hit):
                should_proceed: True=PASS 进入 pipeline, False=STASH 存 Redis
                matched_person_ids: 命中的人员 ID 列表
                matched_keywords: 命中的敏感词列表
                event_similarity_hit: 是否命中事件相似度黑名单
        """
        matched_persons = await self._check_persons(event)
        matched_keywords = await self._check_keywords(event)
        event_hit = await self._check_event_similarity(event)

        should_proceed = bool(matched_persons or matched_keywords or event_hit)

        if should_proceed:
            logger.info(
                "blacklist PASS: event_id=%s, persons=%s, keywords=%s, event_sim=%s",
                event.event_id,
                matched_persons,
                matched_keywords,
                event_hit,
            )
        else:
            logger.info("blacklist STASH: event_id=%s, no matches", event.event_id)

        return should_proceed, matched_persons, matched_keywords, event_hit

    async def _check_persons(self, event: NormalizedEvent) -> list[str]:
        """从事件文本中提取人员 ID 并比对黑名单。"""
        from utils.text import extract_person_id_numbers

        id_numbers = extract_person_id_numbers(event.raw_content)
        hits = []
        for pid in id_numbers:
            score = await self._store.query_person(pid)
            if score is not None:
                hits.append(pid)
        return hits

    async def _check_keywords(self, event: NormalizedEvent) -> list[str]:
        """检查事件内容是否包含的敏感词。"""
        keywords = await self._store.query_keywords()
        if not keywords:
            return []

        matched_keywords: list[str] = []
        content = event.raw_content
        for kw_bytes in keywords:
            kw = kw_bytes.decode() if isinstance(kw_bytes, bytes) else kw_bytes
            if kw in content:
                matched_keywords.append(kw)
        return matched_keywords

    async def _check_event_similarity(self, event: NormalizedEvent) -> bool:
        """
        使用 Jina Rerank API 比对事件黑名单中的摘要。
        最高分 > 阈值则判定为命中。
        """
        event_count = await self._store.get_event_count()
        if event_count == 0:
            return False

        event_summaries = await self._store.get_event_summaries()
        if not event_summaries:
            return False

        summaries: list[str] = []
        for payload in event_summaries.values():
            try:
                summaries.append(json.loads(payload).get("summary", ""))
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

