from __future__ import annotations

from typing import Any

from backend.app.services import store_provider


class EventRepository:
    def __init__(self, stores: Any | None = None) -> None:
        self._stores = stores or store_provider.get_store_bundle()

    async def upsert_from_analysis(self, result: dict[str, Any]) -> int:
        return await self._stores.events.upsert_analysis_result(result)

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
        if date_from is None and date_to is None:
            return self._stores.events.list_events(
                page=page,
                page_size=page_size,
                risk_level=risk_level,
                keyword=keyword,
            )
        result = self._stores.events.list_events(
            page=1,
            page_size=10000,
            risk_level=risk_level,
            keyword=keyword,
        )
        filtered = [
            row
            for row in result["items"]
            if self._matches_date_range(row, date_from=date_from, date_to=date_to)
        ]
        offset = (page - 1) * page_size
        return {
            **result,
            "total": len(filtered),
            "page": page,
            "page_size": page_size,
            "items": filtered[offset : offset + page_size],
        }

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        return self._stores.events.get_event(event_id)

    def delete_event(self, event_id: str) -> bool:
        return self._stores.events.delete_event(event_id)

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
