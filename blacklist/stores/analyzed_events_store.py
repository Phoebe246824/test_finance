from __future__ import annotations

from datetime import datetime
from typing import Any

from blacklist.stores.events_store import EventsStore
from blacklist.stores.events_maintenance import duplicate_event_ids, expired_event_ids
from blacklist.stores.events_recall import merge_recall_matches, person_matches, semantic_hits
from models import NormalizedEvent


class AnalyzedEventsStore(EventsStore):
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
            ["event_id", "content_hash", "raw_content", "created_at", "status"],
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
        event_embedding = await self.resolve_embedding(self._embedding_fn, event.raw_content)
        result = self.collection_operation(
            lambda: self._client.search(
                collection_name=self.collection_name,
                data=[event_embedding],
                anns_field=self.vector_field,
                filter=self.id_filter("event_id", eligible_ids),
                limit=top_k,
                output_fields=self.output_fields,
            )
        )
        hits = result[0] if result else []
        return semantic_hits(hits, set(eligible_ids), self._semantic_score_threshold)
