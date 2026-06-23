from __future__ import annotations

from datetime import datetime
from typing import Any

from blacklist.stores.base import EmbeddingFn, FieldSpec, MilvusBaseStore
from blacklist.stores.events_codec import (
    analysis_row,
    api_event,
    content_hash,
    event_row,
)
from blacklist.stores.events_maintenance import (
    duplicate_event_ids,
    expired_event_ids,
)
from blacklist.stores.events_recall import (
    merge_recall_matches,
    person_matches,
    semantic_hits,
)
from blacklist.stores.events_schema import (
    EVENT_OUTPUT_FIELDS,
    EVENT_PRIMARY_FIELD,
    EVENT_VECTOR_FIELD,
    EVENTS_COLLECTION,
    event_fields,
)
from models import NormalizedEvent


class EventsStore(MilvusBaseStore):
    collection_name = EVENTS_COLLECTION
    primary_field = EVENT_PRIMARY_FIELD
    vector_field = EVENT_VECTOR_FIELD
    output_fields = EVENT_OUTPUT_FIELDS

    def __init__(
        self,
        client: Any,
        *,
        embedding_fn: EmbeddingFn,
        embedding_dim: int = 1024,
        ttl_days: int = 90,
        collection_name: str = EVENTS_COLLECTION,
        semantic_score_threshold: float = 0.0,
    ) -> None:
        super().__init__(client, embedding_dim=embedding_dim)
        self.collection_name = collection_name
        self._embedding_fn = embedding_fn
        self._ttl_days = ttl_days
        self._semantic_score_threshold = semantic_score_threshold

    def fields(self) -> list[FieldSpec]:
        return event_fields(self._embedding_dim)

    async def stash_event(self, event: NormalizedEvent, id_numbers: list[str]) -> int:
        return await self.upsert_event(
            event,
            person_ids=id_numbers,
            status="stashed",
            blacklist_decision="miss",
        )

    async def upsert_event(
        self,
        event: NormalizedEvent,
        *,
        person_ids: list[str],
        status: str,
        blacklist_decision: str = "",
        matched_persons: list[str] | None = None,
        matched_keywords: list[str] | None = None,
        event_similarity: dict[str, Any] | None = None,
    ) -> int:
        duplicate_rows = self.query_by_content_hash(content_hash(event.raw_content))
        if duplicate_rows and duplicate_rows[0].get("event_id") != event.event_id:
            return 0
        row = event_row(
            event,
            embedding=await self.resolve_embedding(self._embedding_fn, event.raw_content),
            person_ids=person_ids,
            status=status,
            blacklist_decision=blacklist_decision,
            matched_persons=matched_persons,
            matched_keywords=matched_keywords,
            event_similarity=event_similarity,
            ttl_days=self._ttl_days,
        )
        return self.upsert_rows([row])

    async def upsert_analysis_result(self, result: dict[str, Any]) -> int:
        event_id = str(result["event_id"])
        existing = self.get_raw_event(event_id) or {}
        raw_content = str(result.get("raw_content") or existing.get("raw_content") or "")
        row = analysis_row(
            result,
            existing=existing,
            embedding=await self.resolve_embedding(self._embedding_fn, raw_content),
            embedding_dim=self._embedding_dim,
            ttl_days=self._ttl_days,
        )
        return self.upsert_rows([row])

    def get_raw_event(self, event_id: str) -> dict[str, Any] | None:
        rows = self.query_rows(
            self.id_filter("event_id", [event_id]),
            [*self.output_fields, "embedding"],
            limit=1,
        )
        return dict(rows[0]) if rows else None

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        row = self.get_raw_event(event_id)
        return api_event(row) if row else None

    def list_events(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        risk_level: str | None = None,
        keyword: str | None = None,
    ) -> dict[str, Any]:
        rows = self.query_rows('event_id != ""', self.output_fields, limit=10000)
        filtered = [
            row
            for row in rows
            if self._matches_filters(row, risk_level=risk_level, keyword=keyword)
        ]
        filtered.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        offset = (page - 1) * page_size
        return {
            "total": len(filtered),
            "page": page,
            "page_size": page_size,
            "items": [api_event(row) for row in filtered[offset : offset + page_size]],
        }

    def delete_event(self, event_id: str) -> bool:
        return self.delete_rows(self.id_filter("event_id", [event_id])) > 0

    def query_by_content_hash(self, row_hash: str) -> list[dict[str, Any]]:
        return self.query_rows(
            f"content_hash == {self.quote(row_hash)}",
            ["event_id", "content_hash", "raw_content"],
            limit=1,
        )

    def ensure_collection_ready(self) -> None:
        self.ensure_collection()

    def query_event_rows(
        self,
        event_id: str,
        output_fields: list[str],
        *,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        return self.query_rows(
            self.id_filter("event_id", [event_id]),
            output_fields,
            limit=limit,
        )

    def count_rows_for_diagnostics(self, *, limit: int = 10000) -> int | None:
        rows = self.query_rows('event_id != ""', ["event_id"], limit=limit)
        return len(rows) if rows else 0

    async def fetch_related_events(
        self,
        event: NormalizedEvent,
        id_numbers: list[str],
        top_k_semantic: int = 10,
        max_per_person: int = 20,
    ) -> list[dict[str, Any]]:
        eligible = self._eligible_rows(event.event_id)
        person_ids = {pid.upper() for pid in id_numbers if pid}
        semantic_rows = await self._semantic_matches(event, eligible, top_k_semantic)
        return merge_recall_matches(
            person_matches(eligible, person_ids, max_per_person),
            semantic_rows,
        )

    async def mark_events_graph_built(self, event_ids: list[str]) -> int:
        unique_ids = sorted({event_id for event_id in event_ids if event_id})
        if not unique_ids:
            return 0
        rows = self.query_rows(
            self.id_filter("event_id", unique_ids),
            [*self.output_fields, "embedding"],
        )
        updated_at = datetime.now().isoformat(timespec="seconds")
        return self.upsert_rows(
            [{**row, "is_graph_built": True, "updated_at": updated_at} for row in rows]
        )

    def cleanup_duplicate_content(self, *, limit: int = 10000) -> int:
        rows = self.query_rows(
            'event_id != ""',
            ["event_id", "content_hash", "raw_content", "created_at"],
            limit=limit,
        )
        delete_ids = duplicate_event_ids(rows)
        return self.delete_rows(self.id_filter("event_id", delete_ids)) if delete_ids else 0

    def cleanup_expired(
        self,
        *,
        now: datetime | None = None,
        graph_built_retention_days: int | None = None,
    ) -> int:
        delete_ids = expired_event_ids(
            self.query_rows,
            self.quote,
            now=now or datetime.now(),
            graph_built_retention_days=graph_built_retention_days,
        )
        return self.delete_rows(self.id_filter("event_id", delete_ids)) if delete_ids else 0

    def _eligible_rows(self, current_event_id: str) -> list[dict[str, Any]]:
        return self.query_rows(
            " and ".join(
                [
                    "is_graph_built == false",
                    f"expire_at > {self.quote(datetime.now().isoformat())}",
                    f"event_id != {self.quote(current_event_id)}",
                ]
            ),
            [*self.output_fields, "embedding"],
        )

    async def _semantic_matches(
        self,
        event: NormalizedEvent,
        eligible_rows: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        if top_k <= 0 or not eligible_rows:
            return []
        eligible_ids = sorted(str(row["event_id"]) for row in eligible_rows)
        self.ensure_collection()
        result = self._client.search(
            collection_name=self.collection_name,
            data=[await self.resolve_embedding(self._embedding_fn, event.raw_content)],
            anns_field=self.vector_field,
            filter=self.id_filter("event_id", eligible_ids),
            limit=top_k,
            output_fields=self.output_fields,
        )
        hits = result[0] if result else []
        return semantic_hits(hits, set(eligible_ids), self._semantic_score_threshold)

    @staticmethod
    def _matches_filters(
        row: dict[str, Any],
        *,
        risk_level: str | None,
        keyword: str | None,
    ) -> bool:
        if risk_level and str(row.get("risk_level") or "") != risk_level:
            return False
        haystack = " ".join(str(row.get(field) or "") for field in ("raw_content", "title", "summary"))
        return keyword is None or keyword in haystack
