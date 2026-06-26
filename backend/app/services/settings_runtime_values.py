from __future__ import annotations

import re
from typing import Final

from backend.app.services.settings_runtime_catalog import (
    EnvField,
    clean_default,
    is_list_env,
)

JsonScalar = str | int | float | bool | None
RuntimeValue = JsonScalar | list[str]

_BOOL_TRUE: Final = frozenset({"1", "true", "yes", "y", "on"})
_BOOL_FALSE: Final = frozenset({"0", "false", "no", "n", "off"})
_INT_PATTERN: Final = re.compile(r"[+-]?\d+")
_FLOAT_PATTERN: Final = re.compile(r"[+-]?(?:\d+\.\d*|\d*\.\d+)")
_FLOAT_ENVS: Final = frozenset(
    {
        "RAGFLOW_TIMEOUT_SECONDS",
    }
)
_INT_ENVS: Final = frozenset(
    {
        "BLACKLIST_PERSON_MIN_HITS",
    }
)


def default_scalar_type(raw_default: str) -> str:
    value = clean_default(raw_default)
    normalized = value.lower()
    if normalized in _BOOL_TRUE or normalized in _BOOL_FALSE:
        return "bool"
    if _INT_PATTERN.fullmatch(value):
        return "int"
    if _FLOAT_PATTERN.fullmatch(value):
        return "float"
    return "string"


def field_scalar_type(field: EnvField) -> str:
    if field.env in _INT_ENVS:
        return "int"
    if field.env in _FLOAT_ENVS:
        return "float"
    return default_scalar_type(field.raw_default)


def scalar_type(value: RuntimeValue) -> str:
    match value:
        case bool():
            return "bool"
        case int():
            return "int"
        case float():
            return "float"
        case list():
            return "list"
        case None:
            return "string"
        case str():
            return "string"


def default_runtime_value(field: EnvField) -> RuntimeValue:
    value = clean_default(field.raw_default)
    if is_list_env(field.env):
        if not value:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]
    match field_scalar_type(field):
        case "bool":
            return value.lower() in _BOOL_TRUE
        case "int":
            return int(value)
        case "float":
            return float(value)
        case "string":
            return value


def coerce_runtime_value(field: EnvField, raw_value: str) -> RuntimeValue:
    default_value = default_runtime_value(field)
    value = clean_default(raw_value)
    if is_list_env(field.env):
        if not value:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]
    match field_scalar_type(field):
        case "bool":
            normalized = value.lower()
            if normalized in _BOOL_TRUE:
                return True
            if normalized in _BOOL_FALSE:
                return False
            return default_value
        case "int":
            if _INT_PATTERN.fullmatch(value):
                return int(value)
            return default_value
        case "float":
            if _FLOAT_PATTERN.fullmatch(value) or _INT_PATTERN.fullmatch(value):
                return float(value)
            return default_value
        case "string":
            return value


def coerce_saved_value(field: EnvField, value: object) -> RuntimeValue:
    default_value = default_runtime_value(field)
    if is_list_env(field.env):
        match value:
            case list():
                if not all(isinstance(item, str) for item in value):
                    return default_value
                return [item.strip() for item in value if item.strip()]
            case str():
                return coerce_runtime_value(field, value)
            case _:
                return default_value
    match field_scalar_type(field):
        case "bool":
            return value if isinstance(value, bool) else (
                coerce_runtime_value(field, value) if isinstance(value, str) else default_value
            )
        case "int":
            return value if isinstance(value, int) and not isinstance(value, bool) else (
                coerce_runtime_value(field, value) if isinstance(value, str) else default_value
            )
        case "float":
            return value if isinstance(value, float) else (
                float(value) if isinstance(value, int) and not isinstance(value, bool) else (
                    coerce_runtime_value(field, value) if isinstance(value, str) else default_value
                )
            )
        case "string":
            return value if isinstance(value, str) else default_value
