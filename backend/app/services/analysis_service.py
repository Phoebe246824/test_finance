from __future__ import annotations

from main import load_config, process_message_detailed

from backend.app.repositories.events import EventRepository
from backend.app.services.risk_rule_service import apply_rules_to_config, load_risk_rules


class AnalysisService:
    def __init__(self) -> None:
        self._events = EventRepository()

    async def analyze(self, text: str) -> dict:
        config = load_config()
        rules, _ = load_risk_rules()
        apply_rules_to_config(config, rules)
        result = await process_message_detailed(text, config)
        self._events.upsert_from_analysis(result)
        return result
