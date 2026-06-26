from __future__ import annotations

import json
import re
from pathlib import Path

from backend.app.services.settings_runtime_catalog import load_env_catalog
from backend.app.services.runtime_state import runtime_state
from backend.app.services.settings_service import list_model_services
from backend.app.services.settings_service import load_app_settings, save_app_settings
from tests.settings_demo.conftest import reset_runtime_state


def _env_example_keys() -> set[str]:
    root = Path(__file__).resolve().parents[2]
    keys: set[str] = set()
    pattern = re.compile(r"^\s*#?\s*([A-Z][A-Z0-9_]+)=")
    for line in (root / ".env.example").read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            keys.add(match.group(1))
    return keys


def _required_runtime_keys() -> set[str]:
    return {field.env for field in load_env_catalog()}


def _stored_settings(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    settings = raw["settings"]
    assert isinstance(settings, dict)
    return settings


def test_runtime_config_is_persisted_on_first_bootstrap_with_env_example_coverage(
    monkeypatch,
    tmp_path,
) -> None:
    # Given
    settings_file = tmp_path / "missing-settings.json"
    monkeypatch.setenv("SENTINEL_SETTINGS_FILE", str(settings_file))
    reset_runtime_state()

    # When
    settings, updated_at = load_app_settings()

    # Then
    assert updated_at
    assert settings_file.exists()
    runtime_config = _stored_settings(settings_file)["runtime_config"]
    assert set(runtime_config) == _required_runtime_keys()
    assert _env_example_keys() < set(runtime_config)
    assert "GRAPHITI_EPISODE_SOURCE" in runtime_config
    assert settings["runtime_config"] == runtime_config


def test_runtime_config_env_overlay_coerces_values_and_exposes_effective_scope(
    monkeypatch,
    tmp_path,
) -> None:
    # Given
    settings_file = tmp_path / "bootstrap-settings.json"
    monkeypatch.setenv("SENTINEL_SETTINGS_FILE", str(settings_file))
    monkeypatch.setenv("LLM_MODEL", "env-web-model")
    monkeypatch.setenv("RAGFLOW_ENABLED", "true")
    monkeypatch.setenv("RAGFLOW_DATASET_IDS", "alpha,beta")
    monkeypatch.setenv("RAGFLOW_TOP_K", "9")
    monkeypatch.setenv("SEARCH_MIN_SCORE", "0.45")
    monkeypatch.setenv("GRAPHITI_EPISODE_SOURCE", "env-episode-source")
    reset_runtime_state()

    # When
    settings, _ = load_app_settings()

    # Then
    runtime_config = settings["runtime_config"]
    assert runtime_config["LLM_MODEL"] == "env-web-model"
    assert runtime_config["RAGFLOW_ENABLED"] is True
    assert runtime_config["RAGFLOW_DATASET_IDS"] == ["alpha", "beta"]
    assert runtime_config["RAGFLOW_TOP_K"] == 9
    assert runtime_config["SEARCH_MIN_SCORE"] == 0.45
    assert runtime_config["GRAPHITI_EPISODE_SOURCE"] == "env-episode-source"

    metadata = {field["env"]: field for field in settings["runtime_config_metadata"]}
    assert metadata["LLM_MODEL"]["effective_scope"] == "web_restart"
    assert metadata["RAGFLOW_ENABLED"]["effective_scope"] == "runtime_immediate"
    assert metadata["RAGFLOW_DATASET_IDS"]["scalar_type"] == "list"
    assert metadata["VITE_API_BASE_URL"]["effective_scope"] == "frontend_rebuild"
    assert metadata["NEO4J_URI"]["effective_scope"] == "compose_recreate"
    assert metadata["GRAPHITI_EPISODE_SOURCE"]["effective_scope"] == "web_restart"
    assert metadata["SENTINEL_TARGET_PLATFORM"]["effective_scope"] == "display_only"


def test_runtime_config_dotenv_overrides_existing_environment_on_first_bootstrap(
    monkeypatch,
    tmp_path,
) -> None:
    # Given
    settings_file = tmp_path / "dotenv-override-settings.json"
    dotenv_file = tmp_path / ".env"
    dotenv_file.write_text("LLM_MODEL=dotenv-web-model\nRAGFLOW_TOP_K=11\n", encoding="utf-8")
    monkeypatch.setenv("SENTINEL_SETTINGS_FILE", str(settings_file))
    monkeypatch.setenv("LLM_MODEL", "process-env-model")
    monkeypatch.setenv("RAGFLOW_TOP_K", "3")
    monkeypatch.setattr(
        "backend.app.services.settings_runtime_config.ROOT",
        tmp_path,
    )
    reset_runtime_state()

    # When
    settings, _ = load_app_settings()

    # Then
    runtime_config = settings["runtime_config"]
    assert runtime_config["LLM_MODEL"] == "dotenv-web-model"
    assert runtime_config["RAGFLOW_TOP_K"] == 11
    stored = _stored_settings(settings_file)["runtime_config"]
    assert stored["LLM_MODEL"] == "dotenv-web-model"
    assert stored["RAGFLOW_TOP_K"] == 11


def test_runtime_config_env_overlay_accepts_integer_form_float_strings(
    monkeypatch,
    tmp_path,
) -> None:
    # Given
    settings_file = tmp_path / "integer-float-settings.json"
    monkeypatch.setenv("SENTINEL_SETTINGS_FILE", str(settings_file))
    monkeypatch.setenv("SEARCH_MIN_SCORE", "1")
    monkeypatch.setenv("RISK_THRESHOLD", "0")
    reset_runtime_state()

    # When
    settings, _ = load_app_settings()

    # Then
    assert settings["runtime_config"]["SEARCH_MIN_SCORE"] == 1.0
    assert settings["runtime_config"]["RISK_THRESHOLD"] == 0.0
    stored = _stored_settings(settings_file)["runtime_config"]
    assert stored["SEARCH_MIN_SCORE"] == 1.0
    assert stored["RISK_THRESHOLD"] == 0.0


def test_runtime_config_existing_settings_are_not_overwritten_by_later_env_change(
    monkeypatch,
    tmp_path,
) -> None:
    # Given
    settings_file = tmp_path / "existing-settings.json"
    monkeypatch.setenv("SENTINEL_SETTINGS_FILE", str(settings_file))
    monkeypatch.setenv("LLM_MODEL", "first-env-model")
    reset_runtime_state()
    settings, _ = load_app_settings()
    settings["runtime_config"]["LLM_MODEL"] = "saved-web-model"
    settings["runtime_config"]["GRAPHITI_EPISODE_SOURCE"] = "saved-episode-source"
    save_app_settings(settings)
    runtime_state.settings = None
    runtime_state.settings_updated_at = ""
    monkeypatch.setenv("LLM_MODEL", "second-env-model")
    monkeypatch.setenv("GRAPHITI_EPISODE_SOURCE", "second-episode-source")

    # When
    reloaded, _ = load_app_settings()

    # Then
    assert reloaded["runtime_config"]["LLM_MODEL"] == "saved-web-model"
    assert reloaded["runtime_config"]["GRAPHITI_EPISODE_SOURCE"] == "saved-episode-source"
    assert _stored_settings(settings_file)["runtime_config"]["LLM_MODEL"] == "saved-web-model"
    assert _stored_settings(settings_file)["runtime_config"]["GRAPHITI_EPISODE_SOURCE"] == "saved-episode-source"


def test_runtime_config_corrupt_settings_file_falls_back_to_bootstrap(
    monkeypatch,
    tmp_path,
) -> None:
    # Given
    settings_file = tmp_path / "corrupt-settings.json"
    settings_file.write_text("{not-json", encoding="utf-8")
    monkeypatch.setenv("SENTINEL_SETTINGS_FILE", str(settings_file))
    monkeypatch.setenv("RAGFLOW_ENABLED", "yes")
    reset_runtime_state()

    # When
    settings, _ = load_app_settings()

    # Then
    assert settings["runtime_config"]["RAGFLOW_ENABLED"] is True
    assert _stored_settings(settings_file)["runtime_config"]["RAGFLOW_ENABLED"] is True


def test_runtime_config_saved_string_values_are_coerced_on_reload(
    monkeypatch,
    tmp_path,
) -> None:
    # Given
    settings_file = tmp_path / "saved-string-settings.json"
    settings_file.write_text(
        json.dumps(
            {
                "settings": {
                    "runtime_config": {
                        "RAGFLOW_ENABLED": "true",
                        "RAGFLOW_TOP_K": "9",
                        "SEARCH_MIN_SCORE": "0.45",
                        "RAGFLOW_DATASET_IDS": "alpha,beta",
                    }
                },
                "updated_at": "2026-06-26T16:00:00",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SENTINEL_SETTINGS_FILE", str(settings_file))
    reset_runtime_state()

    # When
    settings, _ = load_app_settings()

    # Then
    runtime_config = settings["runtime_config"]
    assert runtime_config["RAGFLOW_ENABLED"] is True
    assert runtime_config["RAGFLOW_TOP_K"] == 9
    assert runtime_config["SEARCH_MIN_SCORE"] == 0.45
    assert runtime_config["RAGFLOW_DATASET_IDS"] == ["alpha", "beta"]


def test_runtime_config_section_first_bootstrap_preserves_env_overlay(
    monkeypatch,
    tmp_path,
) -> None:
    # Given
    settings_file = tmp_path / "section-first-settings.json"
    monkeypatch.setenv("SENTINEL_SETTINGS_FILE", str(settings_file))
    monkeypatch.setenv("LLM_MODEL", "env-model-before-section-call")
    reset_runtime_state()

    # When
    services = list_model_services()
    settings, _ = load_app_settings()

    # Then
    assert services
    assert settings["runtime_config"]["LLM_MODEL"] == "env-model-before-section-call"
    assert _stored_settings(settings_file)["runtime_config"]["LLM_MODEL"] == "env-model-before-section-call"
