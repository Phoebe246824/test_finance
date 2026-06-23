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
from blacklist.stores.events_recall import merge_recall_matches, person_matches
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
    ) -> None:
        super().__init__(client, embedding_dim=embedding_dim)
        self._embedding_fn = embedding_fn
        self._ttl_days = ttl_days

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
        return [semantic_row(hit, set(eligible_ids)) for hit in result[0] if result]

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


def semantic_row(hit: dict[str, Any], eligible_ids: set[str]) -> dict[str, Any]:
    entity = dict(hit.get("entity") or {})
    event_id = str(entity.get("event_id") or hit.get("id"))
    if event_id not in eligible_ids:
        return {}
    return {
        **entity,
        "event_id": event_id,
        "semantic_score": float(hit.get("distance") or 0.0),
    }


def duplicate_event_ids(rows: list[dict[str, Any]]) -> list[str]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        raw_content = str(row.get("raw_content") or "")
        row_hash = str(row.get("content_hash") or content_hash(raw_content))
        grouped.setdefault(row_hash, []).append(row)
    delete_ids: list[str] = []
    for duplicate_rows in grouped.values():
        duplicate_rows.sort(
            key=lambda item: (str(item.get("created_at") or ""), str(item.get("event_id") or ""))
        )
        delete_ids.extend(str(row["event_id"]) for row in duplicate_rows[1:] if row.get("event_id"))
    return delete_ids
