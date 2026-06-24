from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RagflowConfig:
    enabled: bool
    base_url: str
    api_key: str
    dataset_ids: list[str]
    top_k: int = 5
    similarity_threshold: float = 0.2
    vector_similarity_weight: float = 0.7
    timeout_seconds: float = 15.0
    max_context_chars: int = 4000
    fail_open: bool = True

    @property
    def ready(self) -> bool:
        return bool(self.enabled and self.base_url and self.api_key and self.dataset_ids)


class RagflowClient:
    def __init__(self, config: RagflowConfig) -> None:
        self._config = config

    async def retrieve(self, question: str) -> dict[str, Any]:
        if not self._config.ready:
            return {
                "enabled": self._config.enabled,
                "ready": False,
                "question": question,
                "chunks": [],
                "message": "RAGFlow is disabled or missing required configuration.",
            }

        payload = {
            "question": question,
            "dataset_ids": self._config.dataset_ids,
            "top_k": self._config.top_k,
            "similarity_threshold": self._config.similarity_threshold,
            "vector_similarity_weight": self._config.vector_similarity_weight,
        }
        headers = {"Authorization": f"Bearer {self._config.api_key}"}
        url = f"{self._config.base_url.rstrip('/')}/api/v1/retrieval"

        try:
            async with httpx.AsyncClient(timeout=self._config.timeout_seconds) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            logger.warning("RAGFlow retrieval failed: %s", exc, exc_info=True)
            if self._config.fail_open:
                return {
                    "enabled": True,
                    "ready": True,
                    "question": question,
                    "chunks": [],
                    "error": str(exc),
                }
            raise

        return {
            "enabled": True,
            "ready": True,
            "question": question,
            "chunks": _extract_chunks(data),
            "raw": data,
        }


def _extract_chunks(data: Any) -> list[dict[str, Any]]:
    payload = data.get("data", data) if isinstance(data, dict) else data
    if isinstance(payload, dict):
        candidates = (
            payload.get("chunks")
            or payload.get("records")
            or payload.get("results")
            or payload.get("documents")
            or []
        )
    else:
        candidates = payload if isinstance(payload, list) else []

    chunks: list[dict[str, Any]] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        text = (
            item.get("content")
            or item.get("content_with_weight")
            or item.get("content_ltks")
            or item.get("text")
            or item.get("chunk")
            or item.get("page_content")
            or ""
        )
        if not str(text).strip():
            continue
        chunks.append(
            {
                "content": str(text).strip(),
                "document_name": item.get("document_name")
                or item.get("doc_name")
                or item.get("docnm_kwd")
                or item.get("name")
                or item.get("source")
                or "",
                "score": item.get("similarity") or item.get("score") or item.get("rank"),
                "vector_score": item.get("vector_similarity"),
                "term_score": item.get("term_similarity"),
                "page": item.get("page") or item.get("page_num") or item.get("position"),
                "metadata": item,
            }
        )
    return chunks
