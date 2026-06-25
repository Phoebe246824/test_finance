from __future__ import annotations

from typing import Any

SERVICE_TYPE_LLM = "大语言模型"
SERVICE_TYPE_EMBEDDER = "向量模型"
SERVICE_TYPE_RERANKER = "重排序模型"
SERVICE_TYPE_EXTRACT = "信息抽取模型"
RUNNABLE_MODEL_STATUS = "运行中"


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


def apply_model_services_to_config(config: dict[str, Any]) -> dict[str, Any]:
    from backend.app.services.settings_service import load_app_settings

    settings, _ = load_app_settings()
    if llm := active_model_service(settings, SERVICE_TYPE_LLM):
        config["llm"]["base_url"] = str(llm.get("endpoint") or config["llm"]["base_url"])
    if embedder := active_model_service(settings, SERVICE_TYPE_EMBEDDER):
        config["embedder"]["api_base"] = str(
            embedder.get("endpoint") or config["embedder"]["api_base"]
        )
    if reranker := active_model_service(settings, SERVICE_TYPE_RERANKER):
        config["reranker"] = {
            **config.get("reranker", {}),
            "base_url": str(reranker.get("endpoint") or ""),
        }
    if extractor := active_model_service(settings, SERVICE_TYPE_EXTRACT):
        config["graphiti"] = {
            **config.get("graphiti", {}),
            "extract_base_url": str(extractor.get("endpoint") or ""),
        }
    return config


def configured_service_endpoint(service_type: str) -> str | None:
    from backend.app.services.settings_service import load_app_settings

    settings, _ = load_app_settings()
    service = active_model_service(settings, service_type)
    if service is None:
        return None
    endpoint = service.get("endpoint")
    return str(endpoint) if endpoint else None
