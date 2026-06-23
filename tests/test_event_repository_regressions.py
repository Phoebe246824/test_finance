from __future__ import annotations

from typing import Any

import pytest

from backend.app.repositories.events import EventRepository


class FakeEvents:
    def __init__(self) -> None:
        self.analysis_results: list[dict[str, Any]] = []

    async def upsert_analysis_result(self, result: dict[str, Any]) -> int:
        self.analysis_results.append(dict(result))
        return 1


class FakeStores:
    def __init__(self) -> None:
        self.events = FakeEvents()


@pytest.mark.asyncio
async def test_upsert_from_analysis_delegates_to_events_store() -> None:
    stores = FakeStores()
    result = {
        "event_id": "E001",
        "raw_content": "客户 P102 疑似分拆交易",
        "risk_level": "high",
    }

    written = await EventRepository(stores=stores).upsert_from_analysis(result)

    assert written == 1
    assert stores.events.analysis_results == [result]
