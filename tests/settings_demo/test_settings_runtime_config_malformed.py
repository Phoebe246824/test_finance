from __future__ import annotations

import json

from backend.app.services.settings_service import load_app_settings
from tests.settings_demo.conftest import reset_runtime_state


def _stored_runtime_config(settings_file) -> dict:
    raw = json.loads(settings_file.read_text(encoding="utf-8"))
    settings = raw["settings"]
    assert isinstance(settings, dict)
    runtime_config = settings["runtime_config"]
    assert isinstance(runtime_config, dict)
    return runtime_config


def test_runtime_config_malformed_env_values_fall_back_to_defaults(
    monkeypatch,
    tmp_path,
) -> None:
    # Given
    settings_file = tmp_path / "malformed-env-settings.json"
    monkeypatch.setenv("SENTINEL_SETTINGS_FILE", str(settings_file))
    monkeypatch.setenv("RAGFLOW_ENABLED", "not-a-bool")
    monkeypatch.setenv("RAGFLOW_TOP_K", "oops")
    monkeypatch.setenv("SEARCH_MIN_SCORE", "bad-float")
    monkeypatch.setenv("RAGFLOW_DATASET_IDS", "alpha,,beta")
    reset_runtime_state()

    # When
    settings, _ = load_app_settings()

    # Then
    runtime_config = settings["runtime_config"]
    assert runtime_config["RAGFLOW_ENABLED"] is False
    assert runtime_config["RAGFLOW_TOP_K"] == 5
    assert runtime_config["SEARCH_MIN_SCORE"] == 0.0
    assert runtime_config["RAGFLOW_DATASET_IDS"] == ["alpha", "beta"]
    stored = _stored_runtime_config(settings_file)
    assert stored["RAGFLOW_ENABLED"] is False
    assert stored["RAGFLOW_TOP_K"] == 5
    assert stored["SEARCH_MIN_SCORE"] == 0.0
    assert stored["RAGFLOW_DATASET_IDS"] == ["alpha", "beta"]


def test_runtime_config_malformed_saved_values_fall_back_to_defaults(
    monkeypatch,
    tmp_path,
) -> None:
    # Given
    settings_file = tmp_path / "malformed-saved-settings.json"
    settings_file.write_text(
        json.dumps(
            {
                "settings": {
                    "runtime_config": {
                        "RAGFLOW_ENABLED": "not-a-bool",
                        "RAGFLOW_TOP_K": "oops",
                        "SEARCH_MIN_SCORE": "bad-float",
                        "RAGFLOW_DATASET_IDS": {"bad": "shape"},
                    }
                },
                "updated_at": "2026-06-26T16:10:00",
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
    assert runtime_config["RAGFLOW_ENABLED"] is False
    assert runtime_config["RAGFLOW_TOP_K"] == 5
    assert runtime_config["SEARCH_MIN_SCORE"] == 0.0
    assert runtime_config["RAGFLOW_DATASET_IDS"] == []
    stored = _stored_runtime_config(settings_file)
    assert stored["RAGFLOW_ENABLED"] is False
    assert stored["RAGFLOW_TOP_K"] == 5
    assert stored["SEARCH_MIN_SCORE"] == 0.0
    assert stored["RAGFLOW_DATASET_IDS"] == []


def test_runtime_config_wrong_saved_scalar_types_fall_back_to_declared_defaults(
    monkeypatch,
    tmp_path,
) -> None:
    # Given
    settings_file = tmp_path / "wrong-type-saved-settings.json"
    settings_file.write_text(
        json.dumps(
            {
                "settings": {
                    "runtime_config": {
                        "RAGFLOW_TOP_K": False,
                        "SEARCH_MIN_SCORE": True,
                        "LLM_MODEL": 9,
                    }
                },
                "updated_at": "2026-06-26T16:20:00",
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
    assert runtime_config["RAGFLOW_TOP_K"] == 5
    assert runtime_config["SEARCH_MIN_SCORE"] == 0.0
    assert runtime_config["LLM_MODEL"] == "qwen3.5"
    stored = _stored_runtime_config(settings_file)
    assert stored["RAGFLOW_TOP_K"] == 5
    assert stored["SEARCH_MIN_SCORE"] == 0.0
    assert stored["LLM_MODEL"] == "qwen3.5"


def test_runtime_config_saved_list_with_non_string_elements_falls_back_to_default(
    monkeypatch,
    tmp_path,
) -> None:
    # Given
    settings_file = tmp_path / "wrong-type-saved-list-settings.json"
    settings_file.write_text(
        json.dumps(
            {
                "settings": {
                    "runtime_config": {
                        "RAGFLOW_DATASET_IDS": [9, True, " alpha "],
                    }
                },
                "updated_at": "2026-06-26T16:30:00",
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
    assert runtime_config["RAGFLOW_DATASET_IDS"] == []
    stored = _stored_runtime_config(settings_file)
    assert stored["RAGFLOW_DATASET_IDS"] == []
