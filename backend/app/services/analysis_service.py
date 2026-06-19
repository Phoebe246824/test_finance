from __future__ import annotations

from main import load_config, process_message_detailed

from backend.app.repositories.events import EventRepository


class AnalysisService:
    def __init__(self) -> None:
        self._events = EventRepository()

    async def analyze(self, text: str) -> dict:
        result = await process_message_detailed(text, load_config())
        self._events.upsert_from_analysis(result)
        return result
