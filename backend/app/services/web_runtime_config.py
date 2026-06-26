from __future__ import annotations

import os
from typing import Any

from ragflow.client import RagflowConfig

from backend.app.services.model_runtime_config import apply_model_services_to_config
from backend.app.services.settings_runtime_values import RuntimeValue
from backend.app.services.settings_service import load_app_settings


def _text(runtime_config: dict[str, RuntimeValue], env: str, default: str = "") -> str:
    value = runtime_config.get(env)
    return value if isinstance(value, str) and value else default


def _secret(runtime_config: dict[str, RuntimeValue], env: str, default: str = "") -> str:
    value = runtime_config.get(env)
    if isinstance(value, str) and value:
        return value
    return os.getenv(env) or default


def _integer(runtime_config: dict[str, RuntimeValue], env: str, default: int) -> int:
    value = runtime_config.get(env)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _floating(runtime_config: dict[str, RuntimeValue], env: str, default: float) -> float:
    value = runtime_config.get(env)
    if isinstance(value, float):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def _boolean(runtime_config: dict[str, RuntimeValue], env: str, default: bool) -> bool:
    value = runtime_config.get(env)
    return value if isinstance(value, bool) else default


def _string_list(runtime_config: dict[str, RuntimeValue], env: str) -> list[str]:
    value = runtime_config.get(env)
    return list(value) if isinstance(value, list) else []


def _ragflow_dataset_ids(runtime_config: dict[str, RuntimeValue]) -> list[str]:
    dataset_ids = _string_list(runtime_config, "RAGFLOW_DATASET_IDS")
    if dataset_ids:
        return dataset_ids
    dataset_id = _text(runtime_config, "RAGFLOW_DATASET_ID")
    return [dataset_id] if dataset_id else []


def load_web_runtime_config() -> dict[str, Any]:
    settings, _ = load_app_settings()
    runtime_config = settings.get("runtime_config")
    if not isinstance(runtime_config, dict):
        runtime_config = {}

    config: dict[str, Any] = {
        "neo4j": {
            "uri": _text(runtime_config, "NEO4J_URI", "bolt://localhost:7687"),
            "user": _text(runtime_config, "NEO4J_USER", "neo4j"),
            "password": _secret(runtime_config, "NEO4J_PASSWORD", "pa55w0rd"),
        },
        "llm": {
            "api_key": _secret(runtime_config, "LLM_API_KEY"),
            "base_url": _text(runtime_config, "LLM_BASE_URL", "https://api.openai.com/v1"),
            "model": _text(runtime_config, "LLM_MODEL", "gpt-4o"),
        },
        "llm_extract": {
            "api_key": _secret(
                runtime_config,
                "LLM_EXTRACT_API_KEY",
                _secret(runtime_config, "LLM_API_KEY"),
            ),
            "base_url": _text(
                runtime_config,
                "LLM_EXTRACT_BASE_URL",
                _text(runtime_config, "LLM_BASE_URL", "https://api.openai.com/v1"),
            ),
            "model": _text(
                runtime_config,
                "LLM_EXTRACT_MODEL",
                _text(runtime_config, "LLM_MODEL", "gpt-4o"),
            ),
        },
        "llm_reason": {
            "api_key": _secret(
                runtime_config,
                "LLM_REASON_API_KEY",
                _secret(runtime_config, "LLM_API_KEY"),
            ),
            "base_url": _text(
                runtime_config,
                "LLM_REASON_BASE_URL",
                _text(runtime_config, "LLM_BASE_URL", "https://api.openai.com/v1"),
            ),
            "model": _text(
                runtime_config,
                "LLM_REASON_MODEL",
                _text(runtime_config, "LLM_MODEL", "gpt-4o"),
            ),
        },
        "reasoning": {
            "max_attempts": _integer(runtime_config, "REASON_MAX_ATTEMPTS", 2),
            "max_steps": _integer(runtime_config, "REASON_MAX_STEPS", 4),
        },
        "embedder": {
            "model": _text(runtime_config, "EMBEDDER_MODEL", "BAAI/bge-m3"),
            "api_key": _secret(
                runtime_config,
                "EMBEDDER_API_KEY",
                _secret(runtime_config, "LLM_API_KEY"),
            ),
            "api_base": _text(
                runtime_config,
                "EMBEDDER_API_BASE",
                "https://api.openai.com/v1",
            ),
        },
        "reranker": {
            "model": _text(runtime_config, "RERANKER_MODEL", "BAAI/bge-reranker-v2-m3"),
            "api_key": _secret(
                runtime_config,
                "RERANKER_API_KEY",
                _secret(runtime_config, "LLM_API_KEY"),
            ),
            "base_url": _text(runtime_config, "RERANKER_BASE_URL"),
        },
        "graphiti": {
            "episode_source_name": _text(runtime_config, "GRAPHITI_EPISODE_SOURCE", "sentinel"),
            "dry_run": _boolean(runtime_config, "GRAPHITI_DRY_RUN", False),
            "extract_base_url": _text(runtime_config, "LLM_EXTRACT_BASE_URL"),
            "extract_model": _text(runtime_config, "LLM_EXTRACT_MODEL"),
            "extract_api_key": _secret(runtime_config, "LLM_EXTRACT_API_KEY"),
        },
        "search": {
            "num_results": _integer(runtime_config, "SEARCH_NUM_RESULTS", 10),
            "risk_num_results": _integer(
                runtime_config,
                "RISK_SEARCH_NUM_RESULTS",
                _integer(runtime_config, "SEARCH_NUM_RESULTS", 20),
            ),
            "min_score": _floating(runtime_config, "SEARCH_MIN_SCORE", 0.0),
        },
        "classification": {
            "risk_threshold": _floating(runtime_config, "RISK_THRESHOLD", 0.2),
        },
        "risk_scoring": {
            "dimensions": {
                "customer_identity": _floating(
                    runtime_config,
                    "RISK_WEIGHT_CUSTOMER_IDENTITY",
                    0.15,
                ),
                "transaction_behavior": _floating(
                    runtime_config,
                    "RISK_WEIGHT_TRANSACTION_BEHAVIOR",
                    0.25,
                ),
                "counterparty": _floating(runtime_config, "RISK_WEIGHT_COUNTERPARTY", 0.20),
                "amount_velocity": _floating(
                    runtime_config,
                    "RISK_WEIGHT_AMOUNT_VELOCITY",
                    0.15,
                ),
                "device_geo": _floating(runtime_config, "RISK_WEIGHT_DEVICE_GEO", 0.10),
                "history_context": _floating(
                    runtime_config,
                    "RISK_WEIGHT_HISTORY_CONTEXT",
                    0.10,
                ),
                "compliance_signal": _floating(
                    runtime_config,
                    "RISK_WEIGHT_COMPLIANCE_SIGNAL",
                    0.05,
                ),
            }
        },
        "blacklist": {
            "event_similarity_threshold": _floating(
                runtime_config,
                "BLACKLIST_EVENT_SIMILARITY_THRESHOLD",
                0.5,
            ),
            "person_min_hits": _integer(runtime_config, "BLACKLIST_PERSON_MIN_HITS", 1),
        },
        "storage": {"backend": "milvus"},
        "milvus": {
            "uri": _text(runtime_config, "MILVUS_URI", "http://localhost:19530"),
            "token": _secret(runtime_config, "MILVUS_TOKEN"),
            "stash_collection": _text(runtime_config, "MILVUS_STASH_COLLECTION", "events"),
            "stash_ttl_days": _integer(runtime_config, "KV_TTL_DAYS", 90),
            "semantic_top_k": _integer(runtime_config, "STASH_SEMANTIC_TOP_K", 10),
            "rerank_min_score": _floating(runtime_config, "STASH_RERANK_MIN_SCORE", 0.7),
            "rerank_enabled": _boolean(runtime_config, "STASH_RERANK_ENABLED", True),
            "max_per_person": _integer(runtime_config, "BATCH_MAX_PER_PERSON", 20),
            "embedding_dim": _integer(runtime_config, "EMBEDDING_DIM", 1024),
        },
        "ragflow": {
            "client": RagflowConfig(
                enabled=_boolean(runtime_config, "RAGFLOW_ENABLED", False),
                base_url=_text(runtime_config, "RAGFLOW_BASE_URL"),
                api_key=_secret(runtime_config, "RAGFLOW_API_KEY"),
                dataset_ids=_ragflow_dataset_ids(runtime_config),
                top_k=_integer(runtime_config, "RAGFLOW_TOP_K", 5),
                similarity_threshold=_floating(
                    runtime_config,
                    "RAGFLOW_SIMILARITY_THRESHOLD",
                    0.2,
                ),
                vector_similarity_weight=_floating(
                    runtime_config,
                    "RAGFLOW_VECTOR_SIMILARITY_WEIGHT",
                    0.7,
                ),
                timeout_seconds=_floating(runtime_config, "RAGFLOW_TIMEOUT_SECONDS", 15.0),
                max_context_chars=_integer(runtime_config, "RAGFLOW_MAX_CONTEXT_CHARS", 4000),
                fail_open=_boolean(runtime_config, "RAGFLOW_FAIL_OPEN", True),
            )
        },
    }
    return apply_model_services_to_config(config, override_existing=False)


__all__ = ["load_web_runtime_config"]
