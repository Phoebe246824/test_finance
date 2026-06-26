from __future__ import annotations

from dotenv import dotenv_values, load_dotenv

from backend.app.services.settings_runtime_catalog import (
    ROOT,
    EnvField,
    effective_scope,
    is_secret,
    label_for,
    load_env_catalog,
)
from backend.app.services.settings_runtime_values import (
    RuntimeValue,
    coerce_runtime_value,
    coerce_saved_value,
    default_runtime_value,
    scalar_type,
)

JsonScalar = str | int | float | bool | None
RuntimeConfig = dict[str, RuntimeValue]
RuntimeMetadata = dict[str, RuntimeValue]


def _dotenv_configured_values() -> dict[str, str]:
    values = dotenv_values(ROOT / ".env")
    return {
        key: value
        for key, value in values.items()
        if key is not None and value is not None
    }


def build_runtime_config(*, use_environment: bool) -> RuntimeConfig:
    configured_env_values: dict[str, str] = {}
    if use_environment:
        load_dotenv(ROOT / ".env", override=True)
        configured_env_values = _dotenv_configured_values()
    config: RuntimeConfig = {}
    for field in load_env_catalog():
        raw_value = configured_env_values.get(field.env)
        config[field.env] = coerce_runtime_value(
            field,
            field.raw_default if raw_value is None else raw_value,
        )
    return config


def build_runtime_metadata() -> list[RuntimeMetadata]:
    metadata: list[RuntimeMetadata] = []
    for field in load_env_catalog():
        default = default_runtime_value(field)
        scope = effective_scope(field.env)
        metadata.append(
            {
                "env": field.env,
                "group": field.group,
                "key_path": f"runtime_config.{field.env}",
                "label": label_for(field.env),
                "help": field.help_text,
                "scalar_type": scalar_type(default),
                "default": default,
                "secret": is_secret(field.env),
                "editable": scope != "display_only",
                "effective_scope": scope,
            }
        )
    return metadata


def ensure_runtime_settings(
    settings: dict[str, object],
    *,
    use_environment: bool,
) -> tuple[dict[str, object], bool]:
    next_settings = dict(settings)
    catalog = {field.env: field for field in load_env_catalog()}
    defaults = build_runtime_config(use_environment=use_environment)
    current = next_settings.get("runtime_config")
    changed = not isinstance(current, dict)
    runtime_config: RuntimeConfig = dict(defaults)
    if isinstance(current, dict):
        for key, value in current.items():
            field = catalog.get(key)
            if key in runtime_config and field is not None:
                coerced = coerce_saved_value(field, value)
                runtime_config[key] = coerced
                changed = changed or coerced != value
        changed = changed or set(current) != set(runtime_config)
    next_settings["runtime_config"] = runtime_config
    metadata = build_runtime_metadata()
    changed = changed or next_settings.get("runtime_config_metadata") != metadata
    next_settings["runtime_config_metadata"] = metadata
    return next_settings, changed


__all__ = [
    "EnvField",
    "JsonScalar",
    "ROOT",
    "RuntimeConfig",
    "RuntimeMetadata",
    "RuntimeValue",
    "build_runtime_config",
    "build_runtime_metadata",
    "ensure_runtime_settings",
    "load_env_catalog",
]
