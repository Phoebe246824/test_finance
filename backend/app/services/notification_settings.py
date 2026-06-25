from __future__ import annotations

from copy import deepcopy
from typing import Any

import httpx

from backend.app.services.outbound_http import create_outbound_async_client
from backend.app.services.settings_defaults import IMPLEMENTED_NOTIFICATION_CHANNELS
from backend.app.services.url_safety import validate_outbound_http_url
from backend.app.services.webhook_auth import webhook_headers_for_target


def list_notification_channels(get_section) -> list[dict[str, Any]]:
    return [
        deepcopy(channel)
        for channel in get_section("notification_channels")
        if channel.get("name") in IMPLEMENTED_NOTIFICATION_CHANNELS
    ]


def update_notification_channel(
    get_section,
    set_section,
    name: str,
    *,
    enabled: bool,
    target: str,
) -> dict[str, Any] | None:
    if name not in IMPLEMENTED_NOTIFICATION_CHANNELS:
        return None
    _ensure_safe_target(target)
    channels = get_section("notification_channels")
    for channel in channels:
        if channel.get("name") == name:
            channel["enabled"] = enabled
            channel["target"] = target
            set_section("notification_channels", channels)
            return deepcopy(channel)
    return None


def validate_notification_channels(channels: list[dict[str, Any]]) -> None:
    for channel in channels:
        if channel.get("name") not in IMPLEMENTED_NOTIFICATION_CHANNELS:
            continue
        target = str(channel.get("target") or "")
        if target and target != "未配置":
            _ensure_safe_target(target)


async def test_notification_channel(get_section, name: str) -> dict[str, Any] | None:
    if name not in IMPLEMENTED_NOTIFICATION_CHANNELS:
        return None
    channels = get_section("notification_channels")
    for channel in channels:
        if channel.get("name") != name:
            continue
        target = channel.get("target", "")
        if not target or target == "未配置":
            return {
                "success": False,
                "message": f"通知渠道 '{name}' 的目标地址未配置",
                "channel": name,
            }
        return await _test_webhook_channel(name, str(target))
    return None


async def _test_webhook_channel(name: str, target: str) -> dict[str, Any]:
    safety = validate_outbound_http_url(target)
    if not safety.allowed:
        return {
            "success": False,
            "message": safety.message,
            "channel": name,
        }
    try:
        async with create_outbound_async_client(timeout=3.0, follow_redirects=False) as client:
            response = await client.post(
                target,
                json={"event": "notification_test", "channel": name},
                headers=webhook_headers_for_target(target),
            )
            response.raise_for_status()
    except httpx.RequestError:
        return {
            "success": False,
            "message": "Webhook 不可达",
            "channel": name,
        }
    except httpx.HTTPStatusError as exc:
        return {
            "success": False,
            "message": f"Webhook 返回异常状态：{exc.response.status_code}",
            "channel": name,
        }
    return {
        "success": True,
        "message": f"Webhook 测试发送成功：{target}",
        "channel": name,
    }


def _ensure_safe_target(target: str) -> None:
    if not target or target == "未配置":
        return
    safety = validate_outbound_http_url(target)
    if not safety.allowed:
        raise ValueError(safety.message)
