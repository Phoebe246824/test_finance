from __future__ import annotations

import json

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


def test_named_model_service_test_updates_persisted_status(monkeypatch) -> None:
    from backend.app.services import model_service_settings

    reset_runtime_state()
    requested_urls = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(200, json={"data": [{"id": "qwen3"}]})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        model_service_settings,
        "create_outbound_async_client",
        AsyncClientFactory(transport),
    )
    monkeypatch.setattr(
        "backend.app.services.url_safety.socket.getaddrinfo",
        public_dns_result,
    )
    client = TestClient(create_app(), raise_server_exceptions=False)
    service = DEFAULT_SETTINGS["model_services"][0]

    response = client.post(
        f"/api/model-services/{service['name']}/test",
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["result"]["success"] is True
    assert response.json()["service"]["status"] == "运行中"
    assert requested_urls == [f"{service['endpoint']}/models"]


def test_model_service_test_calls_openai_compatible_models_endpoint(
    monkeypatch,
) -> None:
    from backend.app.services import model_service_settings

    reset_runtime_state()
    requested_urls = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(200, json={"data": [{"id": "qwen3"}]})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        model_service_settings,
        "create_outbound_async_client",
        AsyncClientFactory(transport),
    )
    monkeypatch.setattr(
        "backend.app.services.url_safety.socket.getaddrinfo",
        public_dns_result,
    )
    client = TestClient(create_app(), raise_server_exceptions=False)

    valid_response = client.post(
        "/api/model-services/test",
        headers=ADMIN_HEADERS,
        json={"endpoint": "https://demo-model.test/v1", "type": "大语言模型"},
    )
    invalid_response = client.post(
        "/api/model-services/test",
        headers=ADMIN_HEADERS,
        json={"endpoint": "demo-model.test/v1"},
    )

    assert valid_response.status_code == 200
    assert valid_response.json()["success"] is True
    assert "模型服务连接成功" in valid_response.json()["message"]
    assert requested_urls == ["https://demo-model.test/v1/models"]
    assert invalid_response.status_code == 200
    assert invalid_response.json()["success"] is False
    assert "http://" in invalid_response.json()["message"]


def test_model_service_test_rejects_metadata_address_without_request(
    monkeypatch,
) -> None:
    from backend.app.services import model_service_settings

    requested_urls = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        model_service_settings,
        "create_outbound_async_client",
        AsyncClientFactory(transport),
    )
    monkeypatch.setattr(
        "backend.app.services.url_safety.socket.getaddrinfo",
        public_dns_result,
    )
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post(
        "/api/model-services/test",
        headers=ADMIN_HEADERS,
        json={
            "endpoint": "http://169.254.169.254/latest/meta-data",
            "type": "大语言模型",
        },
    )

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert "不允许访问该地址" in response.json()["message"]
    assert requested_urls == []


def test_model_service_test_rejects_hostname_that_resolves_to_private_address_without_request(
    monkeypatch,
) -> None:
    from backend.app.services import model_service_settings

    requested_urls = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(200, json={"ok": True})

    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [
            (
                2,
                1,
                6,
                "",
                ("10.0.0.5", port or 80),
            )
        ]

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        model_service_settings,
        "create_outbound_async_client",
        AsyncClientFactory(transport),
    )
    monkeypatch.setattr(
        "backend.app.services.url_safety.socket.getaddrinfo",
        fake_getaddrinfo,
    )
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post(
        "/api/model-services/test",
        headers=ADMIN_HEADERS,
        json={"endpoint": "https://rebind.example.test/v1", "type": "大语言模型"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert "不允许访问该地址" in response.json()["message"]
    assert requested_urls == []


def test_model_service_test_rejects_malformed_port_without_server_error() -> None:
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post(
        "/api/model-services/test",
        headers=ADMIN_HEADERS,
        json={"endpoint": "http://demo.test:not-a-port/v1", "type": "大语言模型"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert "端口" in response.json()["message"]


def test_embedding_model_service_test_posts_to_embeddings_endpoint(
    monkeypatch,
) -> None:
    from backend.app.services import model_service_settings

    requested = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append((request.method, str(request.url), json.loads(request.content)))
        return httpx.Response(200, json={"data": [{"embedding": [0.1]}]})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        model_service_settings,
        "create_outbound_async_client",
        AsyncClientFactory(transport),
    )
    monkeypatch.setattr(
        "backend.app.services.url_safety.socket.getaddrinfo",
        public_dns_result,
    )
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post(
        "/api/model-services/test",
        headers=ADMIN_HEADERS,
        json={"endpoint": "https://demo-model.test/v1", "type": "向量模型"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert requested == [
        (
            "POST",
            "https://demo-model.test/v1/embeddings",
            {"input": "ping", "model": "probe"},
        )
    ]


def test_reranker_model_service_test_posts_to_runtime_rerank_endpoint(
    monkeypatch,
) -> None:
    from backend.app.services import model_service_settings

    requested = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append((request.method, str(request.url), json.loads(request.content)))
        return httpx.Response(
            200,
            json={"results": [{"index": 0, "relevance_score": 1.0}]},
        )

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        model_service_settings,
        "create_outbound_async_client",
        AsyncClientFactory(transport),
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
    assert requested == [
        (
            "POST",
            "https://demo-rerank.test/v1/rerank",
            {"query": "ping", "documents": ["ping"]},
        )
    ]
