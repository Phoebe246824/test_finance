from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from backend.app.services.runtime_state import runtime_state

DEFAULT_RULES: dict[str, Any] = {
    "thresholds": {
        "high": 0.70,
        "medium": 0.35,
    },
    "dimension_weights": {
        "customer_identity": 0.15,
        "transaction_behavior": 0.20,
        "counterparty": 0.20,
        "amount_velocity": 0.15,
        "device_geo": 0.10,
        "history_context": 0.10,
        "compliance_signal": 0.10,
    },
    "disposal_templates": {
        "high": [
            "建议立即人工复核并临时限制后续出金。",
            "核验客户身份、设备、收款账户和交易备注。",
            "若命中涉诈或反洗钱信号，建议提交冻结/止付工单。",
        ],
        "medium": [
            "建议进入观察名单并补充客户回访。",
            "关注 24 小时内是否出现同账户、同设备或同收款方异常交易。",
        ],
        "low": [
            "暂不拦截，保留为历史上下文。",
            "若后续出现高危事件，可作为相似历史线索回捞。",
        ],
    },
}


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def merge_rules(value: dict[str, Any] | None) -> dict[str, Any]:
    merged = json.loads(json.dumps(DEFAULT_RULES, ensure_ascii=False))
    if not value:
        return merged
    for key, item in value.items():
        if isinstance(item, dict) and isinstance(merged.get(key), dict):
            merged[key].update(item)
        else:
            merged[key] = item
    return merged


def load_risk_rules() -> tuple[dict[str, Any], str]:
    rules, updated_at = runtime_state.load_risk_rules(DEFAULT_RULES)
    return merge_rules(rules), updated_at


def save_risk_rules(value: dict[str, Any]) -> tuple[dict[str, Any], str]:
    rules = merge_rules(value)
    return runtime_state.save_risk_rules(json.loads(json.dumps(rules, ensure_ascii=False)))


def apply_rules_to_config(config: dict, rules: dict[str, Any]) -> dict:
    config.setdefault("risk_scoring", {})
    config["risk_scoring"]["dimensions"] = rules.get("dimension_weights") or {}
    config["risk_scoring"]["thresholds"] = rules.get("thresholds") or {}
    return config
