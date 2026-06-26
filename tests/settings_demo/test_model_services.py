from __future__ import annotations

import importlib

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.services.settings_service import DEFAULT_SETTINGS
from tests.settings_demo.conftest import (
    ADMIN_HEADERS,
    public_dns_result,
    reset_runtime_state,
)


def test_model_services_remain_empty_after_all_services_are_deleted():
    reset_runtime_state()
    client = TestClient(create_app(), raise_server_exceptions=False)

    for service in DEFAULT_SETTINGS["model_services"]:
        response = client.delete(
            f"/api/model-services/{service['name']}",
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200

    response = client.get("/api/model-services", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    assert response.json()["services"] == []
    assert response.json()["total"] == 0

def test_duplicate_model_service_create_returns_conflict():
    reset_runtime_state()
    client = TestClient(create_app(), raise_server_exceptions=False)
    service = DEFAULT_SETTINGS["model_services"][0]

    response = client.post(
        "/api/model-services",
        headers=ADMIN_HEADERS,
        json={
            "name": service["name"],
            "type": service["type"],
            "deployment": service["deployment"],
            "endpoint": service["endpoint"],
            "default": True,
        },
    )

    assert response.status_code == 409
    assert "已存在" in response.json()["detail"]

def test_created_default_model_service_is_unverified_and_not_selected_by_provider(
    monkeypatch,
):
    reset_runtime_state()
    monkeypatch.setenv("LLM_MODEL", "base-model")
    monkeypatch.setenv("LLM_API_KEY", "base-key")
    monkeypatch.setenv("LLM_BASE_URL", "http://base-llm.test/v1")
    monkeypatch.setattr("backend.app.services.url_safety.socket.getaddrinfo", public_dns_result)
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post(
        "/api/model-services",
        headers=ADMIN_HEADERS,
        json={
            "name": "Demo Reason LLM",
            "type": "大语言模型",
            "deployment": "本地部署",
            "endpoint": "http://demo-reason.test/v1",
            "default": True,
        },
    )
    assert response.status_code == 200

    import providers.llm_provider as llm_provider

    reloaded = importlib.reload(llm_provider)
    llm = reloaded.get_llm_for("risk_first")

    assert response.json()["service"]["status"] == "未验证"
    assert llm.base_url == DEFAULT_SETTINGS["model_services"][0]["endpoint"]


def test_abnormal_default_model_service_is_not_applied_to_runtime_config(monkeypatch):
    import main

    reset_runtime_state()
    monkeypatch.setenv("LLM_BASE_URL", "http://base-llm.test/v1")
    monkeypatch.setattr("backend.app.services.url_safety.socket.getaddrinfo", public_dns_result)
    client = TestClient(create_app(), raise_server_exceptions=False)
    settings = client.get("/api/settings", headers=ADMIN_HEADERS).json()["settings"]
    settings["model_services"][0]["endpoint"] = "http://demo-reason.test/v1"
    settings["model_services"][0]["default"] = True
    settings["model_services"][0]["status"] = "异常"

    response = client.put("/api/settings", headers=ADMIN_HEADERS, json=settings)
    assert response.status_code == 200

    config = main.load_config()

    assert config["llm"]["base_url"] != "http://demo-reason.test/v1"


def test_model_service_create_rejects_metadata_address_endpoint():
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post(
        "/api/model-services",
        headers=ADMIN_HEADERS,
        json={
            "name": "Unsafe Metadata LLM",
            "type": "大语言模型",
            "deployment": "本地部署",
            "endpoint": "http://169.254.169.254/latest/meta-data",
            "default": True,
        },
    )

    assert response.status_code == 400
    assert "不允许访问该地址" in response.json()["detail"]


def test_settings_save_rejects_unsafe_default_model_service_endpoint():
    client = TestClient(create_app(), raise_server_exceptions=False)
    settings = client.get("/api/settings", headers=ADMIN_HEADERS).json()["settings"]
    settings["model_services"][0]["endpoint"] = "http://169.254.169.254/latest/meta-data"
    settings["model_services"][0]["default"] = True

    response = client.put("/api/settings", headers=ADMIN_HEADERS, json=settings)

    assert response.status_code == 400
    assert "不允许访问该地址" in response.json()["detail"]
