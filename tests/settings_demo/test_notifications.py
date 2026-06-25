from __future__ import annotations

import json

from fastapi.testclient import TestClient
import httpx
import pytest

from backend.app.core.security import CurrentUser
from backend.app.main import create_app
from backend.app.services.runtime_state import runtime_state
from backend.app.services.settings_service import DEFAULT_SETTINGS
from tests.settings_demo.conftest import (
    ADMIN_HEADERS,
    AsyncClientFactory,
    public_dns_result,
    reset_runtime_state,
)


@pytest.mark.asyncio
async def test_analysis_dispatches_enabled_risk_notifications(monkeypatch):
    from backend.app.services.analysis_service import AnalysisService
    from backend.app.services import notification_service

    posted_payloads = []

    def handler(request: httpx.Request) -> httpx.Response:
        posted_payloads.append(json.loads(request.content))
        return httpx.Response(204)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        notification_service,
        "create_outbound_async_client",
        AsyncClientFactory(transport),
    )
    monkeypatch.setattr("backend.app.services.url_safety.socket.getaddrinfo", public_dns_result)

    settings = DEFAULT_SETTINGS.copy()
    settings["notification_events"] = ["高风险事件"]
    settings["notification_channels"] = [
        {"name": "Webhook", "enabled": True, "target": "http://localhost:8000/webhook/alert"},
        {"name": "短信通知", "enabled": False, "target": "未配置"},
    ]
    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.put("/api/settings", headers=ADMIN_HEADERS, json=settings)
    assert response.status_code == 200

    async def fake_process(
        text: str,
        *args: object,
    ) -> dict:
        return {
            "event_id": "E-HIGH",
            "status": "analyzed",
            "risk_level": "high",
            "blacklist": {"decision": "PASS"},
        }

    monkeypatch.setattr("backend.app.services.analysis_service.process_message_detailed", fake_process)

    result = await AnalysisService().analyze("客户 P102 疑似高危交易")

    notification_logs = [
        row for row in runtime_state.audit_logs if row["action"] == "notification.dispatch"
    ]
    assert result["event_id"] == "E-HIGH"
    assert len(notification_logs) == 1
    assert notification_logs[0]["resource_id"] == "E-HIGH"
    assert notification_logs[0]["detail"]["event"] == "高风险事件"
    assert notification_logs[0]["detail"]["channels"] == ["Webhook"]
    assert posted_payloads[0]["event"] == "高风险事件"
    assert posted_payloads[0]["payload"]["event_id"] == "E-HIGH"

def test_webhook_notification_test_sends_probe_request(monkeypatch):
    from backend.app.services import notification_settings

    reset_runtime_state()
    posted_payloads = []
    received_tokens: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        posted_payloads.append(json.loads(request.content))
        received_tokens.append(request.headers.get("X-Sentinel-Webhook-Token"))
        return httpx.Response(204)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        notification_settings,
        "create_outbound_async_client",
        AsyncClientFactory(transport),
    )
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post("/api/notifications/Webhook/test", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert "Webhook 测试发送成功" in response.json()["message"]
    assert posted_payloads == [{"event": "notification_test", "channel": "Webhook"}]
    assert received_tokens == ["sentinel-webhook-token"]


def test_external_webhook_notification_test_does_not_receive_local_receiver_token(monkeypatch):
    from backend.app.services import notification_settings

    reset_runtime_state()
    received_tokens: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received_tokens.append(request.headers.get("X-Sentinel-Webhook-Token"))
        return httpx.Response(204)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        notification_settings,
        "create_outbound_async_client",
        AsyncClientFactory(transport),
    )
    monkeypatch.setattr("backend.app.services.url_safety.socket.getaddrinfo", public_dns_result)
    client = TestClient(create_app(), raise_server_exceptions=False)
    settings = client.get("/api/settings", headers=ADMIN_HEADERS).json()["settings"]
    settings["notification_channels"] = [
        {"name": "Webhook", "enabled": True, "target": "https://hooks.example.test/risk"},
    ]
    save_response = client.put("/api/settings", headers=ADMIN_HEADERS, json=settings)
    assert save_response.status_code == 200

    response = client.post("/api/notifications/Webhook/test", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert received_tokens == [None]


@pytest.mark.asyncio
async def test_external_webhook_dispatch_does_not_receive_local_receiver_token(monkeypatch):
    from backend.app.services import notification_service

    received_tokens: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received_tokens.append(request.headers.get("X-Sentinel-Webhook-Token"))
        return httpx.Response(204)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        notification_service,
        "create_outbound_async_client",
        AsyncClientFactory(transport),
    )
    monkeypatch.setattr("backend.app.services.url_safety.socket.getaddrinfo", public_dns_result)

    sent = await notification_service._send_webhook(
        "https://hooks.example.test/risk",
        "高风险事件",
        {"event_id": "E001"},
    )

    assert sent is True
    assert received_tokens == [None]


@pytest.mark.asyncio
async def test_local_demo_webhook_dispatch_includes_receiver_token(monkeypatch):
    from backend.app.services import notification_service

    received_tokens: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received_tokens.append(request.headers.get("X-Sentinel-Webhook-Token"))
        return httpx.Response(204)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        notification_service,
        "create_outbound_async_client",
        AsyncClientFactory(transport),
    )

    sent = await notification_service._send_webhook(
        "http://localhost:8000/webhook/alert",
        "高风险事件",
        {"event_id": "E001"},
    )

    assert sent is True
    assert received_tokens == ["sentinel-webhook-token"]


def test_local_webhook_alert_endpoint_records_delivery():
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post(
        "/webhook/alert",
        headers={"X-Sentinel-Webhook-Token": "sentinel-webhook-token"},
        json={"event": "notification_test", "payload": {"event_id": "E001"}},
    )

    assert response.status_code == 200
    assert response.json() == {"accepted": True}
    assert runtime_state.audit_logs[-1]["action"] == "webhook.received"
    assert runtime_state.audit_logs[-1]["resource_id"] == "notification_test"


def test_local_webhook_alert_endpoint_rejects_missing_token():
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post(
        "/webhook/alert",
        json={"event": "forged", "payload": {"event_id": "E-FORGED"}},
    )

    assert response.status_code == 401
    assert [
        row for row in runtime_state.audit_logs if row["action"] == "webhook.received"
    ] == []


@pytest.mark.asyncio
async def test_blacklist_notification_dispatches_when_high_risk_toggle_is_disabled(monkeypatch):
    from backend.app.services import notification_service

    posted_payloads = []

    def handler(request: httpx.Request) -> httpx.Response:
        posted_payloads.append(json.loads(request.content))
        return httpx.Response(204)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        notification_service,
        "create_outbound_async_client",
        AsyncClientFactory(transport),
    )

    settings = DEFAULT_SETTINGS.copy()
    settings["notification_events"] = ["黑名单命中"]
    settings["notification_channels"] = [
        {"name": "Webhook", "enabled": True, "target": "http://localhost:8000/webhook/alert"},
    ]
    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.put("/api/settings", headers=ADMIN_HEADERS, json=settings)
    assert response.status_code == 200

    await notification_service.dispatch_analysis_notifications(
        result={
            "event_id": "E-HIGH-BLACKLIST",
            "risk_level": "high",
            "blacklist": {
                "decision": "PASS",
                "matched_keywords": ["虚拟币"],
            },
        },
        actor=CurrentUser(username="admin", role="admin"),
    )

    notification_logs = [
        row for row in runtime_state.audit_logs if row["action"] == "notification.dispatch"
    ]
    assert len(notification_logs) == 1
    assert notification_logs[0]["detail"]["event"] == "黑名单命中"
    assert posted_payloads[0]["event"] == "黑名单命中"


def test_default_notifications_only_expose_implemented_channels():
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.get("/api/notifications", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    assert [channel["name"] for channel in response.json()["channels"]] == ["Webhook"]

def test_webhook_test_rejects_private_network_target_without_request(monkeypatch):
    from backend.app.services import notification_settings

    requested_urls = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        notification_settings,
        "create_outbound_async_client",
        AsyncClientFactory(transport),
    )
    client = TestClient(create_app(), raise_server_exceptions=False)
    settings = client.get("/api/settings", headers=ADMIN_HEADERS).json()["settings"]
    settings["notification_channels"] = [
        {"name": "Webhook", "enabled": True, "target": "http://10.0.0.5/hook"},
    ]
    save_response = client.put("/api/settings", headers=ADMIN_HEADERS, json=settings)
    assert save_response.status_code == 400
    assert "不允许访问该地址" in save_response.json()["detail"]
    assert requested_urls == []


def test_notification_channel_save_rejects_private_network_target():
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.put(
        "/api/notifications/Webhook",
        headers=ADMIN_HEADERS,
        json={"enabled": True, "target": "http://10.0.0.5/hook"},
    )

    assert response.status_code == 400
    assert "不允许访问该地址" in response.json()["detail"]


def test_notification_settings_save_rejects_malformed_port_without_server_error():
    client = TestClient(create_app(), raise_server_exceptions=False)
    settings = client.get("/api/settings", headers=ADMIN_HEADERS).json()["settings"]
    settings["notification_channels"] = [
        {"name": "Webhook", "enabled": True, "target": "http://demo.test:not-a-port/hook"},
    ]

    response = client.put("/api/settings", headers=ADMIN_HEADERS, json=settings)

    assert response.status_code == 400
    assert "端口" in response.json()["detail"]
