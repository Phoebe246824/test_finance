from __future__ import annotations

from main import process_message_detailed
from pipeline_progress import ProgressCallback

from backend.app.core.security import CurrentUser
from backend.app.services.notification_service import (
    dispatch_analysis_notifications,
    dispatch_system_notification,
)
from backend.app.services.risk_rule_service import apply_rules_to_config, load_risk_rules
from backend.app.services.web_runtime_config import load_web_runtime_config

SYSTEM_ACTOR = CurrentUser(username="system", role="admin")


class AnalysisService:
    async def analyze(
        self,
        text: str,
        progress_callback: ProgressCallback | None = None,
        actor: CurrentUser | None = None,
    ) -> dict:
        notification_actor = actor or SYSTEM_ACTOR
        try:
            config = load_web_runtime_config()
            rules, _ = load_risk_rules()
            apply_rules_to_config(config, rules)
            if progress_callback is None:
                result = await process_message_detailed(text, config)
            else:
                result = await process_message_detailed(text, config, progress_callback)
        except Exception as exc:
            await dispatch_system_notification(
                event_name=_failure_notification_event(str(exc)),
                actor=notification_actor,
                resource_id=None,
                detail={"error": str(exc)[:200]},
            )
            raise
        await dispatch_analysis_notifications(result=result, actor=notification_actor)
        return result


def _failure_notification_event(error_message: str) -> str:
    lowered = error_message.lower()
    if "model" in lowered or "llm" in lowered or "模型" in error_message:
        return "模型服务异常"
    return "系统异常"
