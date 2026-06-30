from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from pymilvus import DataType

from blacklist.stores.base import EmbeddingFn, FieldSpec, MilvusBaseStore


@dataclass(frozen=True, slots=True)
class EventSampleMatch:
    hit: bool
    score: float
    event_id: str
    summary: str
    threshold: float


class EventSamplesStore(MilvusBaseStore):
    collection_name = "blacklist_event_samples"
    primary_field = "sample_id"
    vector_field = "embedding"

    def __init__(
        self,
        client: Any,
        *,
        embedding_fn: EmbeddingFn,
        embedding_dim: int = 1024,
    ) -> None:
        super().__init__(client, embedding_dim=embedding_dim)
        self._embedding_fn = embedding_fn

    def fields(self) -> list[FieldSpec]:
        return [
            FieldSpec("sample_id", DataType.VARCHAR, is_primary=True, max_length=128),
            FieldSpec("summary", DataType.VARCHAR, max_length=2048),
            FieldSpec("description", DataType.VARCHAR, max_length=8192),
            FieldSpec("embedding", DataType.FLOAT_VECTOR, dim=self._embedding_dim),
            FieldSpec("enabled", DataType.BOOL),
            FieldSpec("created_at", DataType.VARCHAR, max_length=64),
            FieldSpec("updated_at", DataType.VARCHAR, max_length=64),
        ]

    async def append_event(
        self,
        event_id: str,
        summary: str,
        description: str = "",
    ) -> int:
        text = description or summary
        now = self.now_iso()
        existing = self._find_sample_row(event_id)
        if not existing and self._content_hash_exists(text):
            return 0
        row = {
            "sample_id": event_id,
            "summary": summary,
            "description": text,
            "embedding": await self.resolve_embedding(self._embedding_fn, text),
            "enabled": True,
            "created_at": str(existing.get("created_at") or now) if existing else now,
            "updated_at": now,
        }
        return self.upsert_rows([row])

    async def remove_event(self, event_id: str) -> bool:
        row = self._find_sample_row(event_id)
        if not row:
            return False
        row.update({"enabled": False, "updated_at": self.now_iso()})
        return self.upsert_rows([row]) > 0

    async def get_event_count(self) -> int:
        rows = self.query_rows(
            'sample_id != "" and enabled == true',
            ["sample_id"],
            limit=10000,
        )
        return len(rows)

    async def get_event_summaries(self) -> dict[str, str]:
        rows = self.query_rows(
            'sample_id != "" and enabled == true',
            ["sample_id", "summary"],
            limit=10000,
        )
        return {str(row["sample_id"]): str(row.get("summary") or "") for row in rows}

    async def find_best_match(
        self,
        query: str,
        *,
        threshold: float,
    ) -> EventSampleMatch | None:
        if await self.get_event_count() == 0:
            return None
        self.ensure_collection()
        result = self._client.search(
            collection_name=self.collection_name,
            data=[await self.resolve_embedding(self._embedding_fn, query)],
            anns_field=self.vector_field,
            filter="enabled == true",
            limit=1,
            output_fields=["sample_id", "summary", "description"],
        )
        hits = result[0] if result else []
        if not hits:
            return None
        return self._match_from_hit(hits[0], threshold)

    def list_items(self) -> list[dict[str, Any]]:
        rows = self.query_rows(
            'sample_id != "" and enabled == true',
            ["sample_id", "summary", "description", "enabled", "created_at", "updated_at"],
            limit=10000,
        )
        return [
            {**row, "value": row["sample_id"]}
            for row in sorted(
                rows,
                key=lambda item: str(item.get("updated_at") or ""),
                reverse=True,
            )
        ]

    def _find_sample_row(self, sample_id: str) -> dict[str, Any]:
        rows = self.query_rows(
            f"sample_id == {self.quote(sample_id)}",
            ["sample_id", "summary", "description", "embedding", "enabled", "created_at"],
            limit=1,
        )
        return dict(rows[0]) if rows else {}

    def _content_hash_exists(self, text: str) -> bool:
        normalized = self._normalize_text(text)
        if not normalized:
            return False
        target_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        rows = self.query_rows(
            'sample_id != "" and enabled == true',
            ["sample_id", "summary", "description"],
            limit=10000,
        )
        for row in rows:
            candidate_text = str(row.get("description") or row.get("summary") or "")
            if hashlib.sha256(self._normalize_text(candidate_text).encode("utf-8")).hexdigest() == target_hash:
                return True
        return False

    @staticmethod
    def _normalize_text(text: str) -> str:
        return " ".join(str(text or "").split()).strip()

    @staticmethod
    def _match_from_hit(
        hit: dict[str, Any],
        threshold: float,
    ) -> EventSampleMatch | None:
        score = float(hit.get("distance") or 0.0)
        if score <= threshold:
            return None
        entity = hit.get("entity") or {}
        sample_id = str(entity.get("sample_id") or hit.get("id") or "")
        summary = str(entity.get("summary") or entity.get("description") or "")
        return EventSampleMatch(
            hit=True,
            score=score,
            event_id=sample_id,
            summary=summary,
            threshold=threshold,
        )
