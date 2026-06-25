from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.app.services import model_service_settings, notification_settings
from backend.app.services.risk_rule_service import now_text
from backend.app.services.runtime_state import runtime_state
from backend.app.services.settings_defaults import (
    DEFAULT_SETTINGS,
    IMPLEMENTED_NOTIFICATION_CHANNELS,
    IMPLEMENTED_NOTIFICATION_EVENTS,
)


def _merge(default_value: Any, stored_value: Any) -> Any:
    if isinstance(default_value, dict) and isinstance(stored_value, dict):
        merged = deepcopy(default_value)
        for key, value in stored_value.items():
            merged[key] = _merge(merged[key], value) if key in merged else value
        return merged
    if stored_value is None:
        return deepcopy(default_value)
    return stored_value


def _filter_supported_channels(settings: dict[str, Any]) -> dict[str, Any]:
    filtered = deepcopy(settings)
    data_management = filtered.get("data_management") or {}
    filtered["data_management"] = {
        "summary": data_management.get("summary") or [],
        "retentionDays": data_management.get("retentionDays") or 180,
    }
    filtered["notification_channels"] = [
        channel
        for channel in filtered.get("notification_channels", [])
        if channel.get("name") in IMPLEMENTED_NOTIFICATION_CHANNELS
    ]
    filtered["notification_events"] = [
        event
        for event in filtered.get("notification_events", [])
        if event in IMPLEMENTED_NOTIFICATION_EVENTS
    ]
    return filtered


def load_app_settings() -> tuple[dict[str, Any], str]:
    settings, updated_at = runtime_state.load_settings(DEFAULT_SETTINGS)
    return _filter_supported_channels(_merge(DEFAULT_SETTINGS, settings)), updated_at


def save_app_settings(value: dict[str, Any]) -> tuple[dict[str, Any], str]:
    settings = _filter_supported_channels(_merge(DEFAULT_SETTINGS, value))
    model_service_settings.validate_model_services(settings.get("model_services") or [])
    notification_settings.validate_notification_channels(settings.get("notification_channels") or [])
    saved, updated_at = runtime_state.save_settings(settings)
    if not updated_at:
        updated_at = now_text()
    return saved, updated_at


def _get_section(key: str) -> list[dict[str, Any]]:
    settings, _ = runtime_state.load_settings(DEFAULT_SETTINGS)
    merged = _filter_supported_channels(_merge(DEFAULT_SETTINGS, settings))
    return list(merged.get(key) or [])


def _set_section(key: str, items: list[dict[str, Any]]) -> None:
    settings, _ = runtime_state.load_settings(DEFAULT_SETTINGS)
    settings = _filter_supported_channels(_merge(DEFAULT_SETTINGS, settings))
    settings[key] = items
    runtime_state.save_settings(settings)


def list_users() -> list[dict[str, Any]]:
    return deepcopy(_get_section("users"))


def get_user(username: str) -> dict[str, Any] | None:
    for user in _get_section("users"):
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
    users = _get_section("users")
    if any(user.get("username") == username for user in users):
        raise ValueError(f"用户名 '{username}' 已存在")
    user = {
        "username": username,
        "name": name,
        "role": role,
        "status": status,
        "lastLogin": "",
    }
    users.append(user)
    _set_section("users", users)
    return deepcopy(user)


def update_user(
    username: str,
    *,
    name: str,
    role: str,
) -> dict[str, Any] | None:
    users = _get_section("users")
    for user in users:
        if user.get("username") == username:
            user["name"] = name
            user["role"] = role
            _set_section("users", users)
            return deepcopy(user)
    return None


def delete_user(username: str) -> bool:
    users = _get_section("users")
    kept = [user for user in users if user.get("username") != username]
    if len(kept) == len(users):
        return False
    _set_section("users", kept)
    return True


def reset_user_password(username: str, new_password: str) -> dict[str, Any] | None:
    return get_user(username)


def toggle_user_status(username: str) -> dict[str, Any] | None:
    users = _get_section("users")
    for user in users:
        if user.get("username") == username:
            user["status"] = "禁用" if user.get("status") == "启用" else "启用"
            _set_section("users", users)
            return deepcopy(user)
    return None


def list_model_services() -> list[dict[str, Any]]:
    return model_service_settings.list_model_services(_get_section)


def get_model_service(name: str) -> dict[str, Any] | None:
    return model_service_settings.get_model_service(_get_section, name)


def add_model_service(
    *,
    name: str,
    type: str,
    deployment: str,
    endpoint: str,
    status: str,
    default: bool,
) -> dict[str, Any]:
    return model_service_settings.add_model_service(
        _get_section,
        _set_section,
        name=name,
        type=type,
        deployment=deployment,
        endpoint=endpoint,
        status=status,
        default=default,
    )


def update_model_service(
    original_name: str,
    *,
    name: str,
    type: str,
    deployment: str,
    endpoint: str,
    default: bool,
) -> dict[str, Any] | None:
    return model_service_settings.update_model_service(
        _get_section,
        _set_section,
        original_name,
        name=name,
        type=type,
        deployment=deployment,
        endpoint=endpoint,
        default=default,
    )


def update_model_service_status(
    name: str,
    *,
    status: str,
) -> dict[str, Any] | None:
    return model_service_settings.update_model_service_status(
        _get_section,
        _set_section,
        name,
        status=status,
    )


def delete_model_service(name: str) -> bool:
    return model_service_settings.delete_model_service(_get_section, _set_section, name)


async def test_model_endpoint(
    endpoint: str,
    service_type: str = "大语言模型",
) -> dict[str, Any]:
    return await model_service_settings.test_model_endpoint(endpoint, service_type)


def list_notification_channels() -> list[dict[str, Any]]:
    return notification_settings.list_notification_channels(_get_section)


def update_notification_channel(
    name: str,
    *,
    enabled: bool,
    target: str,
) -> dict[str, Any] | None:
    return notification_settings.update_notification_channel(
        _get_section,
        _set_section,
        name,
        enabled=enabled,
        target=target,
    )


async def test_notification_channel(name: str) -> dict[str, Any] | None:
    return await notification_settings.test_notification_channel(_get_section, name)
