from __future__ import annotations

import importlib

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.services.runtime_state import runtime_state
from backend.app.services.settings_service import DEFAULT_SETTINGS
from tests.settings_demo.conftest import ADMIN_HEADERS, public_dns_result, reset_runtime_state


def test_saved_model_params_are_applied_to_next_llm(monkeypatch):
    reset_runtime_state()
    monkeypatch.setenv("LLM_MODEL", "base-model")
    monkeypatch.setenv("LLM_API_KEY", "base-key")
    monkeypatch.setenv("LLM_BASE_URL", "http://base-llm.test/v1")
    client = TestClient(create_app(), raise_server_exceptions=False)

    settings = client.get("/api/settings", headers=ADMIN_HEADERS).json()["settings"]
    settings["model_params"] = {
        "maxTokens": 1234,
        "temperature": 0.42,
        "topP": 0.77,
        "repetitionPenalty": 1.0,
        "timeout": 9,
        "concurrency": 3,
    }
    response = client.put("/api/settings", headers=ADMIN_HEADERS, json=settings)
    assert response.status_code == 200

    import providers.llm_provider as llm_provider

    reloaded = importlib.reload(llm_provider)
    llm = reloaded.get_llm_for("dashboard")

    assert llm.max_completion_tokens == 1234
    assert llm.temperature == 0.42
    assert llm.top_p == 0.77
    assert llm.frequency_penalty == 1.0
    assert getattr(llm, "timeout", None) == 9

def test_settings_are_persisted_across_runtime_state_instances(tmp_path):
    reset_runtime_state()
    client = TestClient(create_app(), raise_server_exceptions=False)
    settings = client.get("/api/settings", headers=ADMIN_HEADERS).json()["settings"]
    settings["model_params"]["temperature"] = 0.33

    response = client.put("/api/settings", headers=ADMIN_HEADERS, json=settings)
    assert response.status_code == 200
    runtime_state.settings = None
    runtime_state.settings_updated_at = ""

    reloaded = client.get("/api/settings", headers=ADMIN_HEADERS)

    assert reloaded.status_code == 200
    assert reloaded.json()["settings"]["model_params"]["temperature"] == 0.33

def test_corrupt_settings_file_falls_back_to_defaults(tmp_path):
    settings_file = tmp_path / "app_settings.json"
    settings_file.write_text("{not-json", encoding="utf-8")
    reset_runtime_state()
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.get("/api/settings", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    assert response.json()["settings"]["system_config"]["name"] == DEFAULT_SETTINGS["system_config"]["name"]

def test_get_settings_requires_admin_token():
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.get("/api/settings")

    assert response.status_code == 401

def test_model_params_reject_invalid_values():
    client = TestClient(create_app(), raise_server_exceptions=False)
    settings = client.get("/api/settings", headers=ADMIN_HEADERS).json()["settings"]
    settings["model_params"]["temperature"] = "hot"

    response = client.put("/api/settings", headers=ADMIN_HEADERS, json=settings)

    assert response.status_code == 422


def test_settings_save_rejects_extra_top_level_and_model_service_fields():
    client = TestClient(create_app(), raise_server_exceptions=False)
    settings = client.get("/api/settings", headers=ADMIN_HEADERS).json()["settings"]
    settings["model_services"][0]["unexpected"] = "demo"
    settings["surprise"] = {"enabled": True}

    response = client.put("/api/settings", headers=ADMIN_HEADERS, json=settings)

    assert response.status_code == 422


def test_saved_concurrency_is_available_to_analysis_runtime(monkeypatch):
    from backend.app.services.task_service import model_concurrency_limit

    client = TestClient(create_app(), raise_server_exceptions=False)
    settings = client.get("/api/settings", headers=ADMIN_HEADERS).json()["settings"]
    settings["model_params"]["concurrency"] = 7

    response = client.put("/api/settings", headers=ADMIN_HEADERS, json=settings)

    assert response.status_code == 200
    assert model_concurrency_limit() == 7


def test_settings_rejects_unimplemented_notification_and_cleanup_fields():
    client = TestClient(create_app(), raise_server_exceptions=False)
    settings = client.get("/api/settings", headers=ADMIN_HEADERS).json()["settings"]
    settings["notification_events"] = ["高风险事件", "复核任务提醒", "趋势报告生成"]
    settings["data_management"]["cleanupTime"] = "每日 02:00"
    settings["data_management"]["cleanupEnabled"] = True

    response = client.put("/api/settings", headers=ADMIN_HEADERS, json=settings)

    assert response.status_code == 422

def test_default_extract_stage_uses_openai_compatible_llm_endpoint(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "base-model")
    monkeypatch.setenv("LLM_API_KEY", "base-key")
    monkeypatch.setenv("LLM_BASE_URL", "http://base-llm.test/v1")

    import providers.llm_provider as llm_provider

    reloaded = importlib.reload(llm_provider)
    llm = reloaded.get_llm_for("normalize")

    assert llm.base_url == "http://localhost:8001/v1"
    assert "/graph" not in llm.base_url

def test_model_services_are_applied_to_runtime_config(monkeypatch):
    import main
    from graphiti import graphiti_workflow

    monkeypatch.setattr("backend.app.services.url_safety.socket.getaddrinfo", public_dns_result)
    client = TestClient(create_app(), raise_server_exceptions=False)
    settings = client.get("/api/settings", headers=ADMIN_HEADERS).json()["settings"]
    for service in settings["model_services"]:
        if service["type"] == "向量模型":
            service["endpoint"] = "http://vector-runtime.test/v1"
        if service["type"] == "重排序模型":
            service["endpoint"] = "http://rerank-runtime.test"
            service["default"] = True
        if service["type"] == "信息抽取模型":
            service["endpoint"] = "http://extract-runtime.test/v1"
            service["default"] = True
    response = client.put("/api/settings", headers=ADMIN_HEADERS, json=settings)
    assert response.status_code == 200

    config = main.load_config()
    resolved_graphiti_llm = graphiti_workflow._resolve_graphiti_llm_config(
        config["llm"],
        config["graphiti"],
    )

    assert config["embedder"]["api_base"] == "http://vector-runtime.test/v1"
    assert config["reranker"]["base_url"] == "http://rerank-runtime.test"
    assert resolved_graphiti_llm["base_url"] == "http://extract-runtime.test/v1"
