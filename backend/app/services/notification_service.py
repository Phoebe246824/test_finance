from __future__ import annotations

from typing import Any

import httpx

from backend.app.core.security import CurrentUser
from backend.app.services.audit_service import write_audit_log
from backend.app.services.outbound_http import create_outbound_async_client
from backend.app.services.settings_service import load_app_settings
from backend.app.services.url_safety import validate_outbound_http_url
from backend.app.services.webhook_auth import webhook_headers_for_target


async def dispatch_analysis_notifications(
    *,
    result: dict[str, Any],
    actor: CurrentUser,
) -> list[str]:
    event_names = _notification_events_for_result(result)
    if not event_names:
        return []

    settings, _ = load_app_settings()
    enabled_events = set(settings.get("notification_events") or [])
    selected_events = [event for event in event_names if event in enabled_events]
    if not selected_events:
        return []

    channels = [
        channel
        for channel in settings.get("notification_channels") or []
        if channel.get("enabled") and channel.get("target") and channel.get("target") != "未配置"
    ]
    if not channels:
        return []
    delivered_channels: list[str] = []
    event_id = str(result.get("event_id") or "")
    for event_name in selected_events:
        delivered_for_event = await _deliver_channels(channels, event_name, result)
        if not delivered_for_event:
            continue
        delivered_channels.extend(delivered_for_event)
        write_audit_log(
            actor=actor,
            action="notification.dispatch",
            resource_type="event",
            resource_id=event_id or None,
            detail={
                "event": event_name,
                "channels": delivered_for_event,
                "delivery": "sent",
            },
        )
    return delivered_channels


async def dispatch_system_notification(
    *,
    event_name: str,
    actor: CurrentUser,
    resource_id: str | None,
    detail: dict[str, Any] | None = None,
) -> list[str]:
    settings, _ = load_app_settings()
    enabled_events = set(settings.get("notification_events") or [])
    if event_name not in enabled_events:
        return []
    channels = [
        channel
        for channel in settings.get("notification_channels") or []
        if channel.get("enabled") and channel.get("target") and channel.get("target") != "未配置"
    ]
    if not channels:
        return []
    delivered_channels = await _deliver_channels(
        channels,
        event_name,
        {"resource_id": resource_id, **(detail or {})},
    )
    if not delivered_channels:
        return []
    write_audit_log(
        actor=actor,
        action="notification.dispatch",
        resource_type="system",
        resource_id=resource_id,
        detail={
            "event": event_name,
            "channels": delivered_channels,
            "delivery": "sent",
            **(detail or {}),
        },
    )
    return delivered_channels


def _notification_events_for_result(result: dict[str, Any]) -> list[str]:
    events: list[str] = []
    if str(result.get("risk_level") or "").lower() == "high":
        events.append("高风险事件")
    blacklist = result.get("blacklist") or {}
    if isinstance(blacklist, dict) and _is_blacklist_hit(blacklist):
        events.append("黑名单命中")
    return events


def _is_blacklist_hit(blacklist: dict[str, Any]) -> bool:
    decision = str(blacklist.get("decision") or "").upper()
    if decision in {"HIT", "PASS"}:
        return bool(
            blacklist.get("matched_persons")
            or blacklist.get("matched_keywords")
            or (blacklist.get("event_similarity") or {}).get("hit")
        )
    return False


async def _deliver_channels(
    channels: list[dict[str, Any]],
    event_name: str,
    payload: dict[str, Any],
) -> list[str]:
    delivered: list[str] = []
    for channel in channels:
        name = str(channel.get("name") or "")
        if name != "Webhook":
            continue
        target = str(channel.get("target") or "")
        if await _send_webhook(target, event_name, payload):
            delivered.append(name)
    return delivered


async def _send_webhook(target: str, event_name: str, payload: dict[str, Any]) -> bool:
    safety = validate_outbound_http_url(target)
    if not safety.allowed:
        return False
    try:
        async with create_outbound_async_client(timeout=3.0, follow_redirects=False) as client:
            response = await client.post(
                target,
                json={"event": event_name, "payload": payload},
                headers=webhook_headers_for_target(target),
            )
            response.raise_for_status()
    except httpx.RequestError:
        return False
    except httpx.HTTPStatusError:
        return False
    return True
