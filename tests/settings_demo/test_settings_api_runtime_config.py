from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.services.settings_response import SECRET_MASK_VALUE
from backend.app.services.settings_runtime_catalog import is_secret, load_env_catalog
from backend.app.services.settings_service import load_app_settings
from tests.settings_demo.conftest import ADMIN_HEADERS, reset_runtime_state


def _env_example_keys() -> set[str]:
    root = Path(__file__).resolve().parents[2]
    pattern = re.compile(r"^\s*#?\s*([A-Z][A-Z0-9_]+)=")
    return {
        match.group(1)
        for line in (root / ".env.example").read_text(encoding="utf-8").splitlines()
        if (match := pattern.match(line))
    }


def _required_runtime_keys() -> set[str]:
    return {field.env for field in load_env_catalog()}


def _stored_settings(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    settings = raw["settings"]
    assert isinstance(settings, dict)
    return settings


def _write_dotenv(monkeypatch, root: Path, values: dict[str, str]) -> None:
    root.joinpath(".env").write_text(
        "".join(f"{key}={value}\n" for key, value in values.items()),
        encoding="utf-8",
    )
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(
        "backend.app.services.settings_runtime_config.ROOT",
        root,
    )


def test_settings_api_get_filters_legacy_runtime_derived_top_level_keys(
    monkeypatch,
    tmp_path,
) -> None:
    # Given
    settings_file = tmp_path / "legacy-derived-settings.json"
    settings_file.write_text(
        json.dumps(
            {
                "settings": {
                    "runtime_config": {"LLM_MODEL": "legacy-model"},
                    "llm": {"model": "derived-model"},
                    "neo4j": {"uri": "bolt://derived"},
                    "search": {"num_results": 10},
                    "ragflow": {"enabled": False},
                },
                "updated_at": "2026-06-26T19:00:00",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SENTINEL_SETTINGS_FILE", str(settings_file))
    reset_runtime_state()
    client = TestClient(create_app(), raise_server_exceptions=False)

    # When
    response = client.get("/api/settings", headers=ADMIN_HEADERS)
    settings = response.json()["settings"]
    put_response = client.put("/api/settings", headers=ADMIN_HEADERS, json=settings)

    # Then
    assert response.status_code == 200
    assert "llm" not in settings
    assert "neo4j" not in settings
    assert "search" not in settings
    assert "ragflow" not in settings
    assert put_response.status_code == 200


def test_settings_api_get_exposes_runtime_config_and_metadata() -> None:
    # Given
    reset_runtime_state()
    client = TestClient(create_app(), raise_server_exceptions=False)

    # When
    response = client.get("/api/settings", headers=ADMIN_HEADERS)
    settings = response.json()["settings"]

    # Then
    assert response.status_code == 200
    assert set(settings["runtime_config"]) == _required_runtime_keys()
    metadata = {field["env"]: field for field in settings["runtime_config_metadata"]}
    assert set(metadata) == _required_runtime_keys()
    assert _env_example_keys() < set(metadata)


def test_settings_api_put_persists_runtime_config() -> None:
    # Given
    reset_runtime_state()
    client = TestClient(create_app(), raise_server_exceptions=False)
    settings = client.get("/api/settings", headers=ADMIN_HEADERS).json()["settings"]
    settings["runtime_config"]["LLM_MODEL"] = "api-saved-model"
    settings["runtime_config"]["RAGFLOW_ENABLED"] = True
    settings["runtime_config"]["RAGFLOW_DATASET_IDS"] = ["alpha", "beta"]

    # When
    response = client.put("/api/settings", headers=ADMIN_HEADERS, json=settings)
    reloaded = client.get("/api/settings", headers=ADMIN_HEADERS)

    # Then
    assert response.status_code == 200
    assert reloaded.json()["settings"]["runtime_config"]["LLM_MODEL"] == "api-saved-model"
    assert reloaded.json()["settings"]["runtime_config"]["RAGFLOW_ENABLED"] is True
    assert reloaded.json()["settings"]["runtime_config"]["RAGFLOW_DATASET_IDS"] == [
        "alpha",
        "beta",
    ]


def test_settings_api_accepts_blacklist_person_min_hits_as_integer() -> None:
    # Given
    reset_runtime_state()
    client = TestClient(create_app(), raise_server_exceptions=False)
    settings = client.get("/api/settings", headers=ADMIN_HEADERS).json()["settings"]
    metadata = {field["env"]: field for field in settings["runtime_config_metadata"]}
    settings["runtime_config"]["BLACKLIST_PERSON_MIN_HITS"] = 3

    # When
    response = client.put("/api/settings", headers=ADMIN_HEADERS, json=settings)
    reloaded = client.get("/api/settings", headers=ADMIN_HEADERS)

    # Then
    assert metadata["BLACKLIST_PERSON_MIN_HITS"]["scalar_type"] == "int"
    assert response.status_code == 200
    assert reloaded.json()["settings"]["runtime_config"]["BLACKLIST_PERSON_MIN_HITS"] == 3


def test_settings_api_section_update_preserves_newer_runtime_config() -> None:
    # Given
    reset_runtime_state()
    client = TestClient(create_app(), raise_server_exceptions=False)
    original = client.get("/api/settings", headers=ADMIN_HEADERS).json()["settings"]
    original["runtime_config"]["LLM_MODEL"] = "runtime-before-section-update"
    runtime_response = client.put("/api/settings", headers=ADMIN_HEADERS, json=original)
    assert runtime_response.status_code == 200

    # When
    section_response = client.put(
        "/api/settings/system-config",
        headers=ADMIN_HEADERS,
        json={
            **original["system_config"],
            "name": "Runtime Preservation Demo",
        },
    )
    reloaded = client.get("/api/settings", headers=ADMIN_HEADERS)

    # Then
    assert section_response.status_code == 200
    assert reloaded.json()["settings"]["system_config"]["name"] == "Runtime Preservation Demo"
    assert (
        reloaded.json()["settings"]["runtime_config"]["LLM_MODEL"]
        == "runtime-before-section-update"
    )


def test_settings_api_rejects_unknown_runtime_config_field() -> None:
    # Given
    reset_runtime_state()
    client = TestClient(create_app(), raise_server_exceptions=False)
    settings = client.get("/api/settings", headers=ADMIN_HEADERS).json()["settings"]
    settings["runtime_config"]["UNKNOWN_RUNTIME_FIELD"] = "surprise"

    # When
    response = client.put("/api/settings", headers=ADMIN_HEADERS, json=settings)

    # Then
    assert response.status_code == 422


def test_settings_api_rejects_invalid_runtime_config_types() -> None:
    # Given
    reset_runtime_state()
    client = TestClient(create_app(), raise_server_exceptions=False)
    settings = client.get("/api/settings", headers=ADMIN_HEADERS).json()["settings"]
    settings["runtime_config"]["RAGFLOW_ENABLED"] = "true"
    settings["runtime_config"]["RAGFLOW_TOP_K"] = "5"
    settings["runtime_config"]["RAGFLOW_DATASET_IDS"] = "alpha,beta"

    # When
    response = client.put("/api/settings", headers=ADMIN_HEADERS, json=settings)

    # Then
    assert response.status_code == 422


def test_settings_api_rejects_invalid_numeric_runtime_config_domains() -> None:
    # Given
    reset_runtime_state()
    client = TestClient(create_app(), raise_server_exceptions=False)
    settings = client.get("/api/settings", headers=ADMIN_HEADERS).json()["settings"]
    settings["runtime_config"]["RAGFLOW_TOP_K"] = -5
    settings["runtime_config"]["RISK_THRESHOLD"] = 99.0

    # When
    response = client.put("/api/settings", headers=ADMIN_HEADERS, json=settings)

    # Then
    assert response.status_code == 422


def test_settings_api_get_masks_nonblank_secret_values(
    monkeypatch,
) -> None:
    # Given
    monkeypatch.setenv("LLM_API_KEY", "raw-env-llm-secret")
    monkeypatch.setenv("NEO4J_PASSWORD", "raw-env-neo4j-secret")
    monkeypatch.setenv("SENTINEL_ADMIN_TOKEN", "raw-env-admin-secret")
    reset_runtime_state()
    client = TestClient(create_app(), raise_server_exceptions=False)

    # When
    response = client.get(
        "/api/settings",
        headers={"Authorization": "Bearer raw-env-admin-secret"},
    )
    settings = response.json()["settings"]

    # Then
    assert response.status_code == 200
    runtime_config = settings["runtime_config"]
    assert runtime_config["LLM_API_KEY"] == SECRET_MASK_VALUE
    assert runtime_config["NEO4J_PASSWORD"] == SECRET_MASK_VALUE
    assert runtime_config["SENTINEL_ADMIN_TOKEN"] == SECRET_MASK_VALUE
    dumped = json.dumps(settings, ensure_ascii=False)
    assert "raw-env-llm-secret" not in dumped
    assert "raw-env-neo4j-secret" not in dumped
    assert "raw-env-admin-secret" not in dumped
    metadata = {field["env"]: field for field in settings["runtime_config_metadata"]}
    secret_metadata = [field for field in metadata.values() if field["secret"]]
    assert secret_metadata
    assert all(field["default"] == "" for field in secret_metadata)


def test_settings_api_put_masked_secret_preserves_stored_value(
    monkeypatch,
    tmp_path,
) -> None:
    # Given
    settings_file = tmp_path / "masked-secret-preserve.json"
    _write_dotenv(
        monkeypatch,
        tmp_path,
        {"LLM_API_KEY": "stored-secret-before-mask"},
    )
    monkeypatch.setenv("SENTINEL_SETTINGS_FILE", str(settings_file))
    reset_runtime_state()
    client = TestClient(create_app(), raise_server_exceptions=False)
    settings = client.get("/api/settings", headers=ADMIN_HEADERS).json()["settings"]
    assert settings["runtime_config"]["LLM_API_KEY"] == SECRET_MASK_VALUE
    settings["runtime_config"]["LLM_MODEL"] = "model-updated-with-mask"

    # When
    response = client.put("/api/settings", headers=ADMIN_HEADERS, json=settings)
    stored = _stored_settings(settings_file)["runtime_config"]

    # Then
    assert response.status_code == 200
    assert stored["LLM_API_KEY"] == "stored-secret-before-mask"
    assert stored["LLM_MODEL"] == "model-updated-with-mask"


def test_settings_api_put_new_secret_updates_storage_and_runtime_loader(
    monkeypatch,
    tmp_path,
) -> None:
    # Given
    settings_file = tmp_path / "new-secret-update.json"
    _write_dotenv(
        monkeypatch,
        tmp_path,
        {"LLM_API_KEY": "bootstrap-secret-before-update"},
    )
    monkeypatch.setenv("SENTINEL_SETTINGS_FILE", str(settings_file))
    reset_runtime_state()
    client = TestClient(create_app(), raise_server_exceptions=False)
    settings = client.get("/api/settings", headers=ADMIN_HEADERS).json()["settings"]
    settings["runtime_config"]["LLM_API_KEY"] = "new-api-secret"
    settings["runtime_config"]["LLM_MODEL"] = "secret-update-model"

    # When
    response = client.put("/api/settings", headers=ADMIN_HEADERS, json=settings)
    stored = _stored_settings(settings_file)["runtime_config"]
    reset_runtime_state()
    from backend.app.services.web_runtime_config import load_web_runtime_config

    web_config = load_web_runtime_config()
    get_after_update = client.get("/api/settings", headers=ADMIN_HEADERS)

    # Then
    assert response.status_code == 200
    assert stored["LLM_API_KEY"] == "new-api-secret"
    assert web_config["llm"]["api_key"] == "new-api-secret"
    assert (
        get_after_update.json()["settings"]["runtime_config"]["LLM_API_KEY"]
        == SECRET_MASK_VALUE
    )


def test_settings_service_keeps_raw_dotenv_secret_values_for_runtime_use(
    monkeypatch,
    tmp_path,
) -> None:
    # Given
    _write_dotenv(monkeypatch, tmp_path, {"LLM_API_KEY": "service-raw-secret"})
    reset_runtime_state()

    # When
    settings, _ = load_app_settings()

    # Then
    assert settings["runtime_config"]["LLM_API_KEY"] == "service-raw-secret"
    metadata = {field["env"]: field for field in settings["runtime_config_metadata"]}
    assert all(field["secret"] == is_secret(env) for env, field in metadata.items())
