from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi.testclient import TestClient
import httpx

from backend.app.main import create_app
from backend.app.services.settings_service import DEFAULT_SETTINGS
from tests.settings_demo.conftest import (
    ADMIN_HEADERS,
    AsyncClientFactory,
    public_dns_result,
    reset_runtime_state,
)


def _stored_settings(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    settings = raw["settings"]
    assert isinstance(settings, dict)
    return settings


def test_model_service_create_persists_api_key_and_masks_list_response() -> None:
    reset_runtime_state()
    client = TestClient(create_app(), raise_server_exceptions=False)

    create_response = client.post(
        "/api/model-services",
        headers=ADMIN_HEADERS,
        json={
            "name": "SiliconFlow LLM",
            "type": "大语言模型",
            "deployment": "云端部署",
            "endpoint": "https://api.siliconflow.cn/v1",
            "apiKey": "sk-test-12345678",
            "default": False,
        },
    )
    list_response = client.get("/api/model-services", headers=ADMIN_HEADERS)
    settings = client.get("/api/settings", headers=ADMIN_HEADERS).json()["settings"]
    persisted_settings = _stored_settings(Path(os.environ["SENTINEL_SETTINGS_FILE"]))
    saved_service = next(
        service
        for service in persisted_settings["model_services"]
        if service["name"] == "SiliconFlow LLM"
    )
    listed_service = next(
        service
        for service in list_response.json()["services"]
        if service["name"] == "SiliconFlow LLM"
    )
    public_service = next(
        service
        for service in settings["model_services"]
        if service["name"] == "SiliconFlow LLM"
    )

    assert create_response.status_code == 200
    assert create_response.json()["service"]["apiKey"] == "sk-****5678"
    assert listed_service["apiKey"] == "sk-****5678"
    assert saved_service["apiKey"] == "sk-test-12345678"
    assert public_service["apiKey"] == "sk-****5678"


def test_model_service_update_changes_api_key_without_logging_plaintext() -> None:
    reset_runtime_state()
    client = TestClient(create_app(), raise_server_exceptions=False)
    service = DEFAULT_SETTINGS["model_services"][0]

    response = client.put(
        f"/api/model-services/{service['name']}",
        headers=ADMIN_HEADERS,
        json={
            "name": service["name"],
            "type": service["type"],
            "deployment": "云端部署",
            "endpoint": "https://api.siliconflow.cn/v1",
            "apiKey": "sk-updated-87654321",
            "default": service["default"],
        },
    )
    settings = client.get("/api/settings", headers=ADMIN_HEADERS).json()["settings"]
    persisted_settings = _stored_settings(Path(os.environ["SENTINEL_SETTINGS_FILE"]))
    updated_service = next(
        item
        for item in persisted_settings["model_services"]
        if item["name"] == service["name"]
    )
    audit_logs = client.get("/api/audit/logs", headers=ADMIN_HEADERS)
    public_service = next(
        item
        for item in settings["model_services"]
        if item["name"] == service["name"]
    )

    assert response.status_code == 200
    assert response.json()["service"]["apiKey"] == "sk-****4321"
    assert updated_service["apiKey"] == "sk-updated-87654321"
    assert public_service["apiKey"] == "sk-****4321"
    assert "sk-updated-87654321" not in audit_logs.text


def test_saved_model_service_test_sends_bearer_authorization_header(monkeypatch) -> None:
    from backend.app.services import model_service_settings

    captured_headers: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_headers.append(request.headers.get("Authorization"))
        return httpx.Response(200, json={"data": [{"id": "qwen3"}]})

    transport = httpx.MockTransport(handler)
    client_factory = AsyncClientFactory(transport)
    monkeypatch.setattr(
        model_service_settings,
        "create_outbound_async_client",
        client_factory,
    )
    monkeypatch.setattr(
        "backend.app.services.url_safety.socket.getaddrinfo",
        public_dns_result,
    )
    client = TestClient(create_app(), raise_server_exceptions=False)

    create_response = client.post(
        "/api/model-services",
        headers=ADMIN_HEADERS,
        json={
            "name": "SiliconFlow LLM",
            "type": "大语言模型",
            "deployment": "云端部署",
            "endpoint": "https://api.siliconflow.cn/v1",
            "apiKey": "sk-test-12345678",
            "default": False,
        },
    )
    assert create_response.status_code == 200

    test_response = client.post(
        "/api/model-services/SiliconFlow%20LLM/test",
        headers=ADMIN_HEADERS,
    )

    assert test_response.status_code == 200
    assert captured_headers == ["Bearer sk-test-12345678"]
    assert client_factory.calls == [
        {
            "timeout": 10.0,
            "follow_redirects": False,
            "headers": {"Authorization": "Bearer sk-test-12345678"},
        }
    ]


def test_model_service_test_without_api_key_keeps_authorization_header_absent(
    monkeypatch,
) -> None:
    from backend.app.services import model_service_settings

    captured_headers: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_headers.append(request.headers.get("Authorization"))
        return httpx.Response(
            200,
            json={"results": [{"index": 0, "relevance_score": 1.0}]},
        )

    transport = httpx.MockTransport(handler)
    client_factory = AsyncClientFactory(transport)
    monkeypatch.setattr(
        model_service_settings,
        "create_outbound_async_client",
        client_factory,
    )
    monkeypatch.setattr(
        "backend.app.services.url_safety.socket.getaddrinfo",
        public_dns_result,
    )
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post(
        "/api/model-services/test",
        headers=ADMIN_HEADERS,
        json={"endpoint": "https://demo-rerank.test/v1", "type": "重排序模型"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert captured_headers == [None]
    assert client_factory.calls == [
        {"timeout": 10.0, "follow_redirects": False, "headers": None}
    ]
