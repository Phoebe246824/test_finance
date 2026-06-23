from __future__ import annotations

from main import load_config, process_message_detailed


class AnalysisService:
    async def analyze(self, text: str) -> dict:
        return await process_message_detailed(text, load_config())
