from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any, Final

from backend.app.services.settings_defaults import DEFAULT_SETTINGS
from backend.app.services.settings_runtime_catalog import is_secret
from backend.app.services.settings_runtime_config import ensure_runtime_settings

HIDDEN_SETTINGS_RESPONSE_KEYS: Final[frozenset[str]] = frozenset(
    {"runtime_config", "runtime_config_metadata"}
)
VISIBLE_SETTINGS_RESPONSE_KEYS: Final[frozenset[str]] = frozenset(
    set(DEFAULT_SETTINGS) | HIDDEN_SETTINGS_RESPONSE_KEYS
)
SECRET_MASK_VALUE: Final = "********"


def mask_model_service_api_key(api_key: str) -> str:
    normalized = api_key.strip()
    if not normalized:
        return ""
    if len(normalized) <= 4:
        return "****"
    return f"sk-****{normalized[-4:]}"


class SettingsResponseView(dict[str, Any]):
    def __init__(self, data: dict[str, Any]) -> None:
        visible = {
            key: value
            for key, value in data.items()
            if key in VISIBLE_SETTINGS_RESPONSE_KEYS
            and key not in HIDDEN_SETTINGS_RESPONSE_KEYS
        }
        super().__init__(visible)
        self._hidden = {
            key: deepcopy(data[key])
            for key in HIDDEN_SETTINGS_RESPONSE_KEYS
            if key in data
        }

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._hidden:
            return self._hidden.get(key, default)
        return super().get(key, default)

    def __getitem__(self, key: str) -> Any:
        if key in self._hidden:
            return self._hidden[key]
        return super().__getitem__(key)

    def __contains__(self, key: object) -> bool:
        if isinstance(key, str) and key in self._hidden:
            return True
        return super().__contains__(key)

    def __setitem__(self, key: str, value: Any) -> None:
        if key in HIDDEN_SETTINGS_RESPONSE_KEYS:
            self._hidden[key] = value
            return
        super().__setitem__(key, value)

    def __delitem__(self, key: str) -> None:
        if key in self._hidden:
            del self._hidden[key]
            return
        super().__delitem__(key)

    def full_dict(self) -> dict[str, Any]:
        return {
            **dict(self),
            **deepcopy(self._hidden),
        }


def materialize_full_settings(
    settings: dict[str, Any] | SettingsResponseView,
) -> dict[str, Any]:
    if isinstance(settings, SettingsResponseView):
        return deepcopy(settings.full_dict())
    return deepcopy(settings)


def public_settings_response(settings: dict[str, Any] | SettingsResponseView) -> dict[str, Any]:
    response = {
        key: value
        for key, value in materialize_full_settings(settings).items()
        if key in VISIBLE_SETTINGS_RESPONSE_KEYS
    }
    model_services = response.get("model_services")
    if isinstance(model_services, list):
        for service in model_services:
            if isinstance(service, dict):
                api_key = service.get("apiKey")
                if isinstance(api_key, str):
                    service["apiKey"] = mask_model_service_api_key(api_key)
    runtime_config = response.get("runtime_config")
    if isinstance(runtime_config, dict):
        for env, value in runtime_config.items():
            if is_secret(env) and isinstance(value, str) and value:
                runtime_config[env] = SECRET_MASK_VALUE
    metadata = response.get("runtime_config_metadata")
    if isinstance(metadata, list):
        for field in metadata:
            if isinstance(field, dict) and field.get("secret") is True:
                field["default"] = ""
    return response


def preserve_masked_runtime_secrets(
    source: dict[str, Any],
    persisted: dict[str, Any] | SettingsResponseView,
) -> dict[str, Any]:
    next_source = deepcopy(source)
    persisted_settings = materialize_full_settings(persisted)
    _preserve_masked_model_service_secrets(
        next_source.get("model_services"),
        persisted_settings.get("model_services"),
    )
    runtime_config = next_source.get("runtime_config")
    persisted_runtime = persisted_settings.get("runtime_config")
    if not isinstance(runtime_config, dict) or not isinstance(persisted_runtime, dict):
        return next_source
    for env, value in runtime_config.items():
        if is_secret(env) and value == SECRET_MASK_VALUE:
            persisted_value = persisted_runtime.get(env)
            runtime_config[env] = persisted_value if isinstance(persisted_value, str) else ""
    return next_source


def _preserve_masked_model_service_secrets(
    source_services: Any,
    persisted_services: Any,
) -> None:
    if not isinstance(source_services, list) or not isinstance(persisted_services, list):
        return
    persisted_by_name = {
        str(service.get("name") or ""): service
        for service in persisted_services
        if isinstance(service, dict)
    }
    for source_service in source_services:
        if not isinstance(source_service, dict):
            continue
        source_api_key = source_service.get("apiKey")
        if not isinstance(source_api_key, str):
            continue
        persisted_service = persisted_by_name.get(str(source_service.get("name") or ""))
        persisted_api_key = (
            persisted_service.get("apiKey")
            if isinstance(persisted_service, dict)
            else None
        )
        if (
            isinstance(persisted_api_key, str)
            and source_api_key == mask_model_service_api_key(persisted_api_key)
        ):
            source_service["apiKey"] = persisted_api_key


def response_view(settings: dict[str, Any]) -> SettingsResponseView:
    return SettingsResponseView(settings)


def with_runtime_settings_for_storage(
    settings: dict[str, Any],
    source: dict[str, Any],
    *,
    load_persisted_settings: Callable[[dict[str, Any]], tuple[dict[str, Any], str]],
    merge_settings: Callable[[Any, Any], Any],
    filter_settings: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    next_settings = dict(settings)
    runtime_keys = {
        key: deepcopy(source[key])
        for key in HIDDEN_SETTINGS_RESPONSE_KEYS
        if key in source
    }
    if runtime_keys:
        next_settings.update(runtime_keys)
        return next_settings
    persisted, updated_at = load_persisted_settings(DEFAULT_SETTINGS)
    persisted = filter_settings(merge_settings(DEFAULT_SETTINGS, persisted))
    persisted, _ = ensure_runtime_settings(
        persisted,
        use_environment=not updated_at,
    )
    next_settings["runtime_config"] = deepcopy(persisted["runtime_config"])
    next_settings["runtime_config_metadata"] = deepcopy(
        persisted["runtime_config_metadata"]
    )
    return next_settings
