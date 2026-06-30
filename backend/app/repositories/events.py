from __future__ import annotations

from typing import Any

from backend.app.services import store_provider


class EventRepository:
    def __init__(self, stores: Any | None = None) -> None:
        self._stores = stores or store_provider.get_store_bundle()

    async def upsert_from_analysis(self, result: dict[str, Any]) -> int:
        return await self._stores.events.upsert_analysis_result(result)

    async def upsert_stashed_event(self, event: Any, *, person_ids: list[str], status: str, blacklist_decision: str, matched_persons: list[str] | None = None, matched_keywords: list[str] | None = None, event_similarity: dict[str, Any] | None = None, dedupe_content: bool = True) -> int:
        return await self._stores.stashed_events.upsert_event(
            event,
            person_ids=person_ids,
            status=status,
            blacklist_decision=blacklist_decision,
            matched_persons=matched_persons,
            matched_keywords=matched_keywords,
            event_similarity=event_similarity,
            dedupe_content=dedupe_content,
        )

    def list_events(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        risk_level: str | None = None,
        keyword: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict[str, Any]:
        rows = self._merged_events(risk_level=risk_level, keyword=keyword)
        if date_from is not None or date_to is not None:
            rows = [
                row
                for row in rows
                if self._matches_date_range(row, date_from=date_from, date_to=date_to)
            ]
        offset = (page - 1) * page_size
        return {
            "total": len(rows),
            "page": page,
            "page_size": page_size,
            "items": rows[offset : offset + page_size],
        }

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        event = self._stores.events.get_event(event_id)
        stash = self._stores.stashed_events.get_event(event_id)
        if event is None:
            return stash
        if stash is None:
            return event
        return event if self._prefer_row(event, stash) else stash

    def list_recent_events(
        self,
        *,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        return self._merged_events(risk_level=None, keyword=None)[:limit]

    def get_event_for_detail(self, event_id: str) -> dict[str, Any] | None:
        return self.get_event(event_id)

    def delete_event(self, event_id: str) -> bool:
        deleted = self._stores.events.delete_event(event_id)
        return self._stores.stashed_events.delete_event(event_id) or deleted

    def has_content_hash(self, content_hash: str) -> bool:
        return bool(
            self._stores.events.query_by_content_hash(content_hash)
            or self._stores.stashed_events.query_by_content_hash(content_hash)
        )

    def _merged_events(
        self,
        *,
        risk_level: str | None,
        keyword: str | None,
    ) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for row in [
            *self._stores.stashed_events.list_events(
                page=1,
                page_size=10000,
                risk_level=risk_level,
                keyword=keyword,
            )["items"],
            *self._stores.events.list_events(
                page=1,
                page_size=10000,
                risk_level=risk_level,
                keyword=keyword,
            )["items"],
        ]:
            event_id = str(row.get("event_id") or "")
            if not event_id:
                continue
            current = merged.get(event_id)
            if current is None or self._prefer_row(row, current):
                merged[event_id] = row
        rows = list(merged.values())
        rows.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        return rows

    @staticmethod
    def _prefer_row(candidate: dict[str, Any], current: dict[str, Any]) -> bool:
        candidate_status = str(candidate.get("status") or "")
        current_status = str(current.get("status") or "")
        if candidate_status == "analyzed" and current_status != "analyzed":
            return True
        if candidate_status != "analyzed" and current_status == "analyzed":
            return False
        candidate_updated = str(candidate.get("updated_at") or "")
        current_updated = str(current.get("updated_at") or "")
        return candidate_updated > current_updated

    @staticmethod
    def _matches_date_range(
        row: dict[str, Any],
        *,
        date_from: str | None,
        date_to: str | None,
    ) -> bool:
        created_at = str(row.get("created_at") or "")[:10]
        if date_from and created_at < date_from:
            return False
        return not (date_to and created_at > date_to)
