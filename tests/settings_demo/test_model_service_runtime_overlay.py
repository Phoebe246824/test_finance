from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import create_app
from tests.settings_demo.conftest import (
    ADMIN_HEADERS,
    public_dns_result,
    reset_runtime_state,
)


def test_web_runtime_config_uses_default_llm_service_for_blank_runtime_base_url(
    monkeypatch,
) -> None:
    # Given
    reset_runtime_state()
    monkeypatch.setenv("LLM_BASE_URL", "https://env-llm.example/v1")
    monkeypatch.setattr(
        "backend.app.services.url_safety.socket.getaddrinfo", public_dns_result
    )
    client = TestClient(create_app(), raise_server_exceptions=False)
    settings = client.get("/api/settings", headers=ADMIN_HEADERS).json()["settings"]
    settings["runtime_config"]["LLM_BASE_URL"] = ""
    settings["runtime_config"]["LLM_REASON_BASE_URL"] = ""
    settings["model_services"][0]["endpoint"] = "http://saved-service.test/v1"
    settings["model_services"][0]["status"] = "运行中"
    settings["model_services"][0]["default"] = True

    # When
    response = client.put("/api/settings", headers=ADMIN_HEADERS, json=settings)
    reset_runtime_state()
    from backend.app.services.web_runtime_config import load_web_runtime_config

    config = load_web_runtime_config()

    # Then
    assert response.status_code == 200
    assert config["llm"]["base_url"] == "http://saved-service.test/v1"
    assert config["llm_reason"]["base_url"] == "http://saved-service.test/v1"


def test_web_runtime_config_uses_default_llm_service_for_cloud_default_base_url(
    monkeypatch,
) -> None:
    # Given
    reset_runtime_state()
    monkeypatch.setattr(
        "backend.app.services.url_safety.socket.getaddrinfo", public_dns_result
    )
    client = TestClient(create_app(), raise_server_exceptions=False)
    settings = client.get("/api/settings", headers=ADMIN_HEADERS).json()["settings"]
    settings["runtime_config"]["LLM_BASE_URL"] = "https://api.openai.com/v1"
    settings["runtime_config"]["LLM_REASON_BASE_URL"] = "https://api.openai.com/v1"
    settings["model_services"][0]["endpoint"] = "http://saved-service.test/v1"
    settings["model_services"][0]["status"] = "运行中"
    settings["model_services"][0]["default"] = True

    # When
    response = client.put("/api/settings", headers=ADMIN_HEADERS, json=settings)
    reset_runtime_state()
    from backend.app.services.web_runtime_config import load_web_runtime_config

    config = load_web_runtime_config()

    # Then
    assert response.status_code == 200
    assert config["llm"]["base_url"] == "http://saved-service.test/v1"
    assert config["llm_reason"]["base_url"] == "http://saved-service.test/v1"


def test_web_runtime_config_preserves_explicit_llm_endpoint_over_model_service(
    monkeypatch,
) -> None:
    # Given
    reset_runtime_state()
    monkeypatch.setattr(
        "backend.app.services.url_safety.socket.getaddrinfo", public_dns_result
    )
    client = TestClient(create_app(), raise_server_exceptions=False)
    settings = client.get("/api/settings", headers=ADMIN_HEADERS).json()["settings"]
    settings["runtime_config"]["LLM_BASE_URL"] = "https://explicit-llm.example/v1"
    settings["runtime_config"]["LLM_REASON_BASE_URL"] = (
        "https://explicit-reason.example/v1"
    )
    settings["model_services"][0]["endpoint"] = "http://saved-service.test/v1"
    settings["model_services"][0]["status"] = "运行中"
    settings["model_services"][0]["default"] = True

    # When
    response = client.put("/api/settings", headers=ADMIN_HEADERS, json=settings)
    reset_runtime_state()
    from backend.app.services.web_runtime_config import load_web_runtime_config

    config = load_web_runtime_config()

    # Then
    assert response.status_code == 200
    assert config["llm"]["base_url"] == "https://explicit-llm.example/v1"
    assert config["llm_reason"]["base_url"] == "https://explicit-reason.example/v1"
