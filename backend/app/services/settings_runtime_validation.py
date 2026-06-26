from __future__ import annotations

from typing import TypeAlias

from backend.app.services.settings_runtime_catalog import is_list_env, load_env_catalog
from backend.app.services.settings_runtime_values import field_scalar_type

RuntimeConfigValue: TypeAlias = bool | int | float | str | list[str]

_POSITIVE_INT_ENVS = frozenset(
    {
        "SEARCH_NUM_RESULTS",
        "RISK_SEARCH_NUM_RESULTS",
        "REASON_MAX_ATTEMPTS",
        "REASON_MAX_STEPS",
        "RAGFLOW_TOP_K",
        "RAGFLOW_MAX_CONTEXT_CHARS",
        "KV_TTL_DAYS",
        "STASH_SEMANTIC_TOP_K",
        "BATCH_MAX_PER_PERSON",
        "EMBEDDING_DIM",
        "BLACKLIST_PERSON_MIN_HITS",
    }
)
_UNIT_FLOAT_ENVS = frozenset(
    {
        "SEARCH_MIN_SCORE",
        "RISK_THRESHOLD",
        "BLACKLIST_EVENT_SIMILARITY_THRESHOLD",
        "STASH_RERANK_MIN_SCORE",
        "RAGFLOW_SIMILARITY_THRESHOLD",
        "RAGFLOW_VECTOR_SIMILARITY_WEIGHT",
    }
)
_POSITIVE_FLOAT_ENVS = frozenset({"RAGFLOW_TIMEOUT_SECONDS"})


def _runtime_catalog() -> dict[str, str]:
    return {field.env: field_scalar_type(field) for field in load_env_catalog()}


def _runtime_type_matches(
    env: str, scalar_type: str, value: RuntimeConfigValue
) -> bool:
    if is_list_env(env):
        return isinstance(value, list) and all(isinstance(item, str) for item in value)
    match scalar_type:
        case "bool":
            return isinstance(value, bool)
        case "int":
            return isinstance(value, int) and not isinstance(value, bool)
        case "float":
            return isinstance(value, (float, int)) and not isinstance(value, bool)
        case "string":
            return isinstance(value, str)
        case _:
            return False


def _runtime_domain_matches(env: str, value: RuntimeConfigValue) -> bool:
    if env.endswith("_PORT"):
        return (
            isinstance(value, int)
            and not isinstance(value, bool)
            and 1 <= value <= 65535
        )
    if env in _POSITIVE_INT_ENVS:
        return isinstance(value, int) and not isinstance(value, bool) and value > 0
    if env.startswith("RISK_WEIGHT_") or env in _UNIT_FLOAT_ENVS:
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and 0.0 <= float(value) <= 1.0
        )
    if env in _POSITIVE_FLOAT_ENVS:
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and float(value) > 0.0
        )
    return True


def validate_runtime_config(
    runtime_config: dict[str, RuntimeConfigValue],
) -> dict[str, RuntimeConfigValue]:
    catalog = _runtime_catalog()
    for env, value in runtime_config.items():
        scalar_type = catalog.get(env)
        if scalar_type is None:
            raise ValueError(f"Unsupported runtime config key: {env}")
        if not _runtime_type_matches(env, scalar_type, value):
            raise ValueError(f"Invalid runtime config value type for {env}")
        if not _runtime_domain_matches(env, value):
            raise ValueError(f"Invalid runtime config value range for {env}")
    return runtime_config
