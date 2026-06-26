from __future__ import annotations

import main

from backend.app.services.settings_service import load_app_settings, save_app_settings
from tests.settings_demo.conftest import reset_runtime_state


def test_web_runtime_config_uses_saved_values_while_cli_load_config_uses_env(
    monkeypatch,
) -> None:
    # Given
    monkeypatch.setenv("LLM_MODEL", "bootstrap-model")
    settings, _ = load_app_settings()
    settings["runtime_config"]["LLM_MODEL"] = "saved-web-model"
    settings["runtime_config"]["LLM_API_KEY"] = "saved-web-key"
    save_app_settings(settings)
    reset_runtime_state()
    monkeypatch.setenv("LLM_MODEL", "env-cli-model")
    monkeypatch.setenv("LLM_API_KEY", "env-cli-key")

    # When
    from backend.app.services.web_runtime_config import load_web_runtime_config

    web_config = load_web_runtime_config()
    cli_config = main.load_config()

    # Then
    assert web_config["llm"]["model"] == "saved-web-model"
    assert web_config["llm"]["api_key"] == "saved-web-key"
    assert web_config["llm_extract"]["model"] == "saved-web-model"
    assert web_config["llm_reason"]["model"] == "saved-web-model"
    assert cli_config["llm"]["model"] == "env-cli-model"
    assert cli_config["llm"]["api_key"] == "env-cli-key"


def test_web_runtime_config_reads_blank_secret_fields_from_saved_settings_only(
    monkeypatch,
) -> None:
    # Given
    monkeypatch.setenv("LLM_MODEL", "bootstrap-model")
    settings, _ = load_app_settings()
    settings["runtime_config"]["LLM_MODEL"] = "saved-web-model"
    settings["runtime_config"]["LLM_API_KEY"] = ""
    settings["runtime_config"]["EMBEDDER_API_KEY"] = ""
    settings["runtime_config"]["RAGFLOW_API_KEY"] = ""
    settings["runtime_config"]["RAGFLOW_DATASET_ID"] = ""
    settings["runtime_config"]["RAGFLOW_DATASET_IDS"] = ["dataset-a", "dataset-b"]
    save_app_settings(settings)
    reset_runtime_state()
    monkeypatch.setenv("LLM_MODEL", "env-model-ignored-for-web")
    monkeypatch.setenv("LLM_API_KEY", "env-llm-secret")
    monkeypatch.setenv("EMBEDDER_API_KEY", "env-embedder-secret")
    monkeypatch.setenv("RAGFLOW_API_KEY", "env-ragflow-secret")

    # When
    from backend.app.services.web_runtime_config import load_web_runtime_config

    web_config = load_web_runtime_config()

    # Then
    assert web_config["llm"]["model"] == "saved-web-model"
    assert web_config["llm"]["api_key"] == ""
    assert web_config["embedder"]["api_key"] == ""
    assert web_config["ragflow"]["client"].api_key == ""
    assert web_config["ragflow"]["client"].dataset_ids == ["dataset-a", "dataset-b"]


def test_web_runtime_config_keeps_saved_runtime_endpoint_over_default_model_service() -> (
    None
):
    # Given
    settings, _ = load_app_settings()
    settings["runtime_config"]["LLM_BASE_URL"] = "https://saved-llm.example/v1"
    settings["runtime_config"]["LLM_REASON_BASE_URL"] = (
        "https://saved-reason.example/v1"
    )
    settings["runtime_config"]["LLM_EXTRACT_BASE_URL"] = (
        "https://saved-extract.example/v1"
    )
    settings["runtime_config"]["RERANKER_BASE_URL"] = (
        "https://saved-reranker.example/v1"
    )
    save_app_settings(settings)
    reset_runtime_state()

    # When
    from backend.app.services.web_runtime_config import load_web_runtime_config

    web_config = load_web_runtime_config()

    # Then
    assert web_config["llm"]["base_url"] == "https://saved-llm.example/v1"
    assert web_config["llm_reason"]["base_url"] == "https://saved-reason.example/v1"
    assert web_config["llm_extract"]["base_url"] == "https://saved-extract.example/v1"
    assert web_config["reranker"]["base_url"] == "https://saved-reranker.example/v1"
