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
    ) -> dict[str, Any]:
        return self._stores.events.list_events(
            page=page,
            page_size=page_size,
            risk_level=risk_level,
            keyword=keyword,
        )

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        return self._stores.events.get_event(event_id)

    def delete_event(self, event_id: str) -> bool:
        return self._stores.events.delete_event(event_id)
