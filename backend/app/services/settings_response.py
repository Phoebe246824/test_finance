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
    runtime_config = next_source.get("runtime_config")
    persisted_runtime = materialize_full_settings(persisted).get("runtime_config")
    if not isinstance(runtime_config, dict) or not isinstance(persisted_runtime, dict):
        return next_source
    for env, value in runtime_config.items():
        if is_secret(env) and value == SECRET_MASK_VALUE:
            persisted_value = persisted_runtime.get(env)
            runtime_config[env] = persisted_value if isinstance(persisted_value, str) else ""
    return next_source


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
