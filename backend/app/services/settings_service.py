from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from backend.app.db.session import get_connection
from backend.app.services.risk_rule_service import now_text

DEFAULT_SETTINGS: dict[str, Any] = {
    "system_config": {
        "name": "Sentinel Edge 金融风控智能体系统",
        "description": "端侧部署的金融风控智能体系统，支持反欺诈、反洗钱、贷前风控等场景。",
        "timezone": "Asia/Shanghai (UTC+08:00)",
        "dateFormat": "YYYY-MM-DD HH:mm:ss",
        "language": "简体中文",
    },
    "model_params": {
        "maxTokens": 2048,
        "temperature": 0.2,
        "topP": 0.9,
        "repetitionPenalty": 1.1,
        "timeout": 60,
        "concurrency": 2,
    },
    "model_services": [
        {
            "name": "本地大模型（Qwen3-8B）",
            "type": "大语言模型",
            "deployment": "本地部署",
            "endpoint": "http://localhost:8001/v1",
            "status": "运行中",
            "default": True,
            "updatedAt": "2026-06-14 14:22:31",
        },
        {
            "name": "向量模型（text-embedding-v3）",
            "type": "向量模型",
            "deployment": "本地部署",
            "endpoint": "http://localhost:8001/embeddings",
            "status": "运行中",
            "default": True,
            "updatedAt": "2026-06-14 14:21:10",
        },
        {
            "name": "重排序模型（bge-reranker）",
            "type": "重排序模型",
            "deployment": "本地部署",
            "endpoint": "http://localhost:8001/reranker",
            "status": "运行中",
            "default": False,
            "updatedAt": "2026-06-14 14:20:05",
        },
        {
            "name": "图谱抽取模型（graph-extract）",
            "type": "信息抽取模型",
            "deployment": "本地部署",
            "endpoint": "http://localhost:8001/graph",
            "status": "运行中",
            "default": False,
            "updatedAt": "2026-06-14 14:19:42",
        },
    ],
    "users": [
        {"username": "admin", "name": "系统管理员", "role": "超级管理员", "status": "启用", "lastLogin": "2026-06-14 15:21:10"},
        {"username": "risk_manager", "name": "风控管理员", "role": "风控管理员", "status": "启用", "lastLogin": "2026-06-14 14:55:32"},
        {"username": "review_001", "name": "张三", "role": "审核人员", "status": "启用", "lastLogin": "2026-06-14 14:11:24"},
        {"username": "review_002", "name": "李四", "role": "审核人员", "status": "启用", "lastLogin": "2026-06-14 13:44:18"},
        {"username": "user_001", "name": "王五", "role": "普通用户", "status": "启用", "lastLogin": "2026-06-13 18:22:09"},
    ],
    "data_management": {
        "summary": [
            {"label": "总记录数", "value": "1,248"},
            {"label": "数据大小", "value": "128.6 MB"},
            {"label": "最早记录", "value": "2026-05-01"},
            {"label": "最新记录", "value": "2026-06-14"},
        ],
        "retentionDays": 180,
        "cleanupTime": "每日 02:00",
        "cleanupEnabled": True,
    },
    "notification_channels": [
        {"name": "邮件通知", "enabled": True, "target": "smtp@sentinel.com"},
        {"name": "短信通知", "enabled": False, "target": "未配置"},
        {"name": "企业微信", "enabled": True, "target": "Sentinel Edge 风控"},
        {"name": "钉钉通知", "enabled": True, "target": "Sentinel Edge 预警"},
        {"name": "Webhook", "enabled": True, "target": "http://localhost:8000/webhook/alert"},
    ],
    "notification_events": ["高风险事件", "黑名单命中", "系统异常", "复核任务提醒", "趋势报告生成", "模型服务异常"],
}


def _merge(default_value: Any, stored_value: Any) -> Any:
    if isinstance(default_value, dict) and isinstance(stored_value, dict):
        merged = deepcopy(default_value)
        for key, value in stored_value.items():
            merged[key] = _merge(merged[key], value) if key in merged else value
        return merged
    if stored_value is None:
        return deepcopy(default_value)
    return stored_value


def load_app_settings() -> tuple[dict[str, Any], str]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT config_json, updated_at FROM app_settings WHERE config_key = ?",
            ("default",),
        ).fetchone()
    if row is None:
        return deepcopy(DEFAULT_SETTINGS), ""
    return _merge(DEFAULT_SETTINGS, json.loads(row["config_json"])), row["updated_at"]


def save_app_settings(value: dict[str, Any]) -> tuple[dict[str, Any], str]:
    settings = _merge(DEFAULT_SETTINGS, value)
    updated_at = now_text()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO app_settings (config_key, config_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(config_key) DO UPDATE SET
                config_json=excluded.config_json,
                updated_at=excluded.updated_at
            """,
            ("default", json.dumps(settings, ensure_ascii=False), updated_at),
        )
    return settings, updated_at
