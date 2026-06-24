from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from backend.app.services.risk_rule_service import now_text
from backend.app.services.runtime_state import runtime_state

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
    settings, updated_at = runtime_state.load_settings(DEFAULT_SETTINGS)
    return _merge(DEFAULT_SETTINGS, settings), updated_at


def save_app_settings(value: dict[str, Any]) -> tuple[dict[str, Any], str]:
    settings = _merge(DEFAULT_SETTINGS, value)
    saved, updated_at = runtime_state.save_settings(
        json.loads(json.dumps(settings, ensure_ascii=False))
    )
    if not updated_at:
        updated_at = now_text()
    return saved, updated_at


def _get_users_list() -> list[dict[str, Any]]:
    settings, _ = runtime_state.load_settings(DEFAULT_SETTINGS)
    return list(settings.get("users") or DEFAULT_SETTINGS["users"])


def _set_users_list(users: list[dict[str, Any]]) -> None:
    settings, _ = runtime_state.load_settings(DEFAULT_SETTINGS)
    settings["users"] = users
    runtime_state.save_settings(
        json.loads(json.dumps(settings, ensure_ascii=False))
    )


def list_users() -> list[dict[str, Any]]:
    return deepcopy(_get_users_list())


def get_user(username: str) -> dict[str, Any] | None:
    for user in _get_users_list():
        if user.get("username") == username:
            return deepcopy(user)
    return None


def add_user(
    *,
    username: str,
    name: str,
    role: str,
    status: str = "启用",
    password: str = "",
) -> dict[str, Any]:
    users = _get_users_list()
    if any(u.get("username") == username for u in users):
        raise ValueError(f"用户名 '{username}' 已存在")
    user = {
        "username": username,
        "name": name,
        "role": role,
        "status": status,
        "lastLogin": "",
    }
    users.append(user)
    _set_users_list(users)
    return deepcopy(user)


def update_user(
    username: str,
    *,
    name: str,
    role: str,
) -> dict[str, Any] | None:
    users = _get_users_list()
    for user in users:
        if user.get("username") == username:
            user["name"] = name
            user["role"] = role
            _set_users_list(users)
            return deepcopy(user)
    return None


def delete_user(username: str) -> bool:
    users = _get_users_list()
    original_len = len(users)
    users = [u for u in users if u.get("username") != username]
    if len(users) == original_len:
        return False
    _set_users_list(users)
    return True


def reset_user_password(username: str, new_password: str) -> dict[str, Any] | None:
    user = get_user(username)
    if user is None:
        return None
    return user


def toggle_user_status(username: str) -> dict[str, Any] | None:
    users = _get_users_list()
    for user in users:
        if user.get("username") == username:
            user["status"] = "禁用" if user.get("status") == "启用" else "启用"
            _set_users_list(users)
            return deepcopy(user)
    return None


def _get_services_list() -> list[dict[str, Any]]:
    settings, _ = runtime_state.load_settings(DEFAULT_SETTINGS)
    return list(settings.get("model_services") or DEFAULT_SETTINGS["model_services"])


def _set_services_list(services: list[dict[str, Any]]) -> None:
    settings, _ = runtime_state.load_settings(DEFAULT_SETTINGS)
    settings["model_services"] = services
    runtime_state.save_settings(
        json.loads(json.dumps(settings, ensure_ascii=False))
    )


def list_model_services() -> list[dict[str, Any]]:
    return deepcopy(_get_services_list())


def add_model_service(
    *,
    name: str,
    type: str,
    deployment: str,
    endpoint: str,
    status: str,
    default: bool,
) -> dict[str, Any]:
    services = _get_services_list()
    if any(s.get("name") == name for s in services):
        raise ValueError(f"模型服务 '{name}' 已存在")
    svc = {
        "name": name,
        "type": type,
        "deployment": deployment,
        "endpoint": endpoint,
        "status": status,
        "default": default,
        "updatedAt": now_text(),
    }
    services.append(svc)
    _set_services_list(services)
    return deepcopy(svc)


def update_model_service(
    original_name: str,
    *,
    name: str,
    type: str,
    deployment: str,
    endpoint: str,
    default: bool,
) -> dict[str, Any] | None:
    services = _get_services_list()
    if name != original_name and any(s.get("name") == name for s in services):
        raise ValueError(f"模型服务 '{name}' 已存在")
    for svc in services:
        if svc.get("name") == original_name:
            svc["name"] = name
            svc["type"] = type
            svc["deployment"] = deployment
            svc["endpoint"] = endpoint
            svc["default"] = default
            svc["updatedAt"] = now_text()
            _set_services_list(services)
            return deepcopy(svc)
    return None


def delete_model_service(name: str) -> bool:
    services = _get_services_list()
    original_len = len(services)
    services = [s for s in services if s.get("name") != name]
    if len(services) == original_len:
        return False
    _set_services_list(services)
    return True


def _get_notification_list() -> list[dict[str, Any]]:
    settings, _ = runtime_state.load_settings(DEFAULT_SETTINGS)
    return list(settings.get("notification_channels") or DEFAULT_SETTINGS["notification_channels"])


def _set_notification_list(channels: list[dict[str, Any]]) -> None:
    settings, _ = runtime_state.load_settings(DEFAULT_SETTINGS)
    settings["notification_channels"] = channels
    runtime_state.save_settings(
        json.loads(json.dumps(settings, ensure_ascii=False))
    )


def list_notification_channels() -> list[dict[str, Any]]:
    return deepcopy(_get_notification_list())


def update_notification_channel(
    name: str,
    *,
    enabled: bool,
    target: str,
) -> dict[str, Any] | None:
    channels = _get_notification_list()
    for ch in channels:
        if ch.get("name") == name:
            ch["enabled"] = enabled
            ch["target"] = target
            _set_notification_list(channels)
            return deepcopy(ch)
    return None


def test_notification_channel(name: str) -> dict[str, Any] | None:
    channels = _get_notification_list()
    for ch in channels:
        if ch.get("name") == name:
            target = ch.get("target", "")
            if not target or target == "未配置":
                return {
                    "success": False,
                    "message": f"通知渠道 '{name}' 的目标地址未配置",
                    "channel": name,
                }
            return {
                "success": True,
                "message": f"向 '{target}' 发送测试通知成功",
                "channel": name,
            }
    return None
