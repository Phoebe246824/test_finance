from __future__ import annotations

from backend.app.services.settings_service import load_app_settings, save_app_settings
from tests.settings_demo.conftest import reset_runtime_state


def test_web_graphiti_extract_inherits_saved_base_llm_when_extract_fields_are_blank(
    monkeypatch,
) -> None:
    # Given
    settings, _ = load_app_settings()
    settings["runtime_config"]["LLM_MODEL"] = "saved-base-model"
    settings["runtime_config"]["LLM_API_KEY"] = "saved-base-key"
    settings["runtime_config"]["LLM_BASE_URL"] = "https://saved-base.example/v1"
    settings["runtime_config"]["LLM_EXTRACT_MODEL"] = ""
    settings["runtime_config"]["LLM_EXTRACT_API_KEY"] = ""
    settings["runtime_config"]["LLM_EXTRACT_BASE_URL"] = ""
    save_app_settings(settings)
    reset_runtime_state()
    monkeypatch.setenv("LLM_EXTRACT_MODEL", "env-extract-model")
    monkeypatch.setenv("LLM_EXTRACT_API_KEY", "env-extract-key")
    monkeypatch.setenv("LLM_EXTRACT_BASE_URL", "https://env-extract.example/v1")

    # When
    from backend.app.services.web_runtime_config import load_web_runtime_config
    from graphiti import graphiti_workflow

    config = load_web_runtime_config()
    resolved = graphiti_workflow._resolve_graphiti_llm_config(
        config["llm"],
        config["graphiti"],
    )

    # Then
    assert config["llm_extract"] == {
        "api_key": "saved-base-key",
        "base_url": "https://saved-base.example/v1",
        "model": "saved-base-model",
    }
    assert config["graphiti"]["extract_api_key"] == "saved-base-key"
    assert config["graphiti"]["extract_base_url"] == "https://saved-base.example/v1"
    assert config["graphiti"]["extract_model"] == "saved-base-model"
    assert resolved == {
        "api_key": "saved-base-key",
        "base_url": "https://saved-base.example/v1",
        "model": "saved-base-model",
    }
