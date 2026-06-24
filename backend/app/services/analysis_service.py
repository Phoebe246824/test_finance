from __future__ import annotations

from main import load_config, process_message_detailed
from pipeline_progress import ProgressCallback

from backend.app.services.risk_rule_service import apply_rules_to_config, load_risk_rules


class AnalysisService:
    async def analyze(
        self,
        text: str,
        progress_callback: ProgressCallback | None = None,
    ) -> dict:
        config = load_config()
        rules, _ = load_risk_rules()
        apply_rules_to_config(config, rules)
        if progress_callback is None:
            return await process_message_detailed(text, config)
        return await process_message_detailed(text, config, progress_callback)
