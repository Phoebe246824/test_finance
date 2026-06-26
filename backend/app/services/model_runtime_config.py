from __future__ import annotations

from typing import Any

SERVICE_TYPE_LLM = "大语言模型"
SERVICE_TYPE_EMBEDDER = "向量模型"
SERVICE_TYPE_RERANKER = "重排序模型"
SERVICE_TYPE_EXTRACT = "信息抽取模型"
RUNNABLE_MODEL_STATUS = "运行中"
DEFAULT_LLM_BASE_URL = "https://api.openai.com/v1"


def active_model_service(
    settings: dict[str, Any],
    service_type: str,
) -> dict[str, Any] | None:
    services = settings.get("model_services") or []
    candidates = [
        service
        for service in services
        if service.get("type") == service_type
        and service.get("status") == RUNNABLE_MODEL_STATUS
    ]
    if not candidates:
        return None
    return next((service for service in candidates if service.get("default")), candidates[0])


def _apply_endpoint(
    target: dict[str, Any],
    key: str,
    endpoint: str,
    *,
    override_existing: bool,
) -> None:
    if override_existing or not target.get(key):
        target[key] = endpoint


def _apply_llm_service_endpoint(
    target: dict[str, Any],
    key: str,
    endpoint: str,
    *,
    override_existing: bool,
) -> None:
    if target.get(key) == DEFAULT_LLM_BASE_URL:
        target[key] = endpoint
        return
    _apply_endpoint(target, key, endpoint, override_existing=override_existing)


def apply_model_services_to_config(
    config: dict[str, Any],
    *,
    override_existing: bool = True,
) -> dict[str, Any]:
    from backend.app.services.settings_service import load_app_settings

    settings, _ = load_app_settings()
    if llm := active_model_service(settings, SERVICE_TYPE_LLM):
        endpoint = str(llm.get("endpoint") or config["llm"]["base_url"])
        _apply_llm_service_endpoint(
            config["llm"],
            "base_url",
            endpoint,
            override_existing=override_existing,
        )
        if "llm_reason" in config:
            _apply_llm_service_endpoint(
                config["llm_reason"],
                "base_url",
                endpoint,
                override_existing=override_existing,
            )
    if embedder := active_model_service(settings, SERVICE_TYPE_EMBEDDER):
        config["embedder"]["api_base"] = str(
            embedder.get("endpoint") or config["embedder"]["api_base"]
        )
    if reranker := active_model_service(settings, SERVICE_TYPE_RERANKER):
        config["reranker"] = {**config.get("reranker", {})}
        _apply_endpoint(
            config["reranker"],
            "base_url",
            str(reranker.get("endpoint") or ""),
            override_existing=override_existing,
        )
    if extractor := active_model_service(settings, SERVICE_TYPE_EXTRACT):
        endpoint = str(extractor.get("endpoint") or "")
        config["graphiti"] = {**config.get("graphiti", {})}
        _apply_endpoint(
            config["graphiti"],
            "extract_base_url",
            endpoint,
            override_existing=override_existing,
        )
        if "llm_extract" in config:
            _apply_endpoint(
                config["llm_extract"],
                "base_url",
                endpoint,
                override_existing=override_existing,
            )
    return config


def configured_service_endpoint(service_type: str) -> str | None:
    from backend.app.services.settings_service import load_app_settings

    settings, _ = load_app_settings()
    service = active_model_service(settings, service_type)
    if service is None:
        return None
    endpoint = service.get("endpoint")
    return str(endpoint) if endpoint else None
