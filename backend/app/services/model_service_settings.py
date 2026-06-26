from __future__ import annotations

from copy import deepcopy
from typing import Any
from urllib.parse import urljoin

import httpx

from backend.app.services.outbound_http import create_outbound_async_client
from backend.app.services.risk_rule_service import now_text
from backend.app.services.url_safety import validate_outbound_http_url

RUNTIME_MODEL_SERVICE_TYPES = frozenset({"大语言模型", "向量模型", "重排序模型", "信息抽取模型"})
RUNNABLE_MODEL_STATUS = "运行中"


def list_model_services(get_section) -> list[dict[str, Any]]:
    return deepcopy(get_section("model_services"))


def get_model_service(get_section, name: str) -> dict[str, Any] | None:
    for service in get_section("model_services"):
        if service.get("name") == name:
            return deepcopy(service)
    return None


def add_model_service(
    get_section,
    set_section,
    *,
    name: str,
    type: str,
    deployment: str,
    endpoint: str,
    api_key: str,
    status: str,
    default: bool,
) -> dict[str, Any]:
    services = get_section("model_services")
    if any(service.get("name") == name for service in services):
        raise ValueError(f"模型服务 '{name}' 已存在")
    _ensure_safe_endpoint(endpoint, type)
    service = {
        "name": name,
        "type": type,
        "deployment": deployment,
        "endpoint": endpoint,
        "apiKey": api_key,
        "status": status,
        "default": default,
        "updatedAt": now_text(),
    }
    service_default = default and status == RUNNABLE_MODEL_STATUS
    if service_default:
        _clear_default_for_type(services, type)
    elif default:
        service["pendingDefault"] = True
    service["default"] = service_default
    services.append(service)
    set_section("model_services", services)
    return deepcopy(service)


def update_model_service_status(
    get_section,
    set_section,
    name: str,
    *,
    status: str,
) -> dict[str, Any] | None:
    services = get_section("model_services")
    for service in services:
        if service.get("name") != name:
            continue
        service["status"] = status
        service["updatedAt"] = now_text()
        if status == RUNNABLE_MODEL_STATUS and service.get("pendingDefault"):
            _clear_default_for_type(services, str(service.get("type") or ""))
            service["default"] = True
            service.pop("pendingDefault", None)
        set_section("model_services", services)
        return deepcopy(service)
    return None


def update_model_service(
    get_section,
    set_section,
    original_name: str,
    *,
    name: str,
    type: str,
    deployment: str,
    endpoint: str,
    api_key: str,
    default: bool,
) -> dict[str, Any] | None:
    services = get_section("model_services")
    if name != original_name and any(service.get("name") == name for service in services):
        raise ValueError(f"模型服务 '{name}' 已存在")
    _ensure_safe_endpoint(endpoint, type)
    for service in services:
        if service.get("name") != original_name:
            continue
        service_default = default and service.get("status") == RUNNABLE_MODEL_STATUS
        if service_default:
            for existing in services:
                if existing is not service and existing.get("type") == type:
                    existing["default"] = False
        service["name"] = name
        service["type"] = type
        service["deployment"] = deployment
        service["endpoint"] = endpoint
        service["apiKey"] = api_key
        service["default"] = service_default
        if default and not service_default:
            service["pendingDefault"] = True
        else:
            service.pop("pendingDefault", None)
        service["status"] = service.get("status") or "运行中"
        service["updatedAt"] = now_text()
        set_section("model_services", services)
        return deepcopy(service)
    return None


def validate_model_services(services: list[dict[str, Any]]) -> None:
    for service in services:
        _ensure_safe_endpoint(
            str(service.get("endpoint") or ""),
            str(service.get("type") or ""),
        )


def normalize_model_services(services: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = deepcopy(services)
    seen_default_types: set[str] = set()
    for service in normalized:
        service_type = str(service.get("type") or "")
        wants_default = bool(service.get("default"))
        is_runnable = service.get("status") == RUNNABLE_MODEL_STATUS
        if wants_default and is_runnable and service_type not in seen_default_types:
            seen_default_types.add(service_type)
            continue
        if wants_default and not is_runnable:
            service["pendingDefault"] = True
        service["default"] = False
    return normalized


def delete_model_service(get_section, set_section, name: str) -> bool:
    services = get_section("model_services")
    kept = [service for service in services if service.get("name") != name]
    if len(kept) == len(services):
        return False
    set_section("model_services", kept)
    return True


async def test_model_endpoint(
    endpoint: str,
    service_type: str = "大语言模型",
    api_key: str = "",
) -> dict[str, Any]:
    normalized = endpoint.strip()
    safety = validate_outbound_http_url(normalized)
    if not safety.allowed:
        return {
            "success": False,
            "message": safety.message,
            "endpoint": normalized,
        }
    method, url, payload, headers = _model_probe_request(
        normalized,
        service_type,
        api_key,
    )
    request_safety = validate_outbound_http_url(url)
    if not request_safety.allowed:
        return {
            "success": False,
            "message": request_safety.message,
            "endpoint": normalized,
        }
    try:
        async with create_outbound_async_client(
            timeout=10.0,
            follow_redirects=False,
            headers=headers,
        ) as client:
            if method == "post":
                response = await client.post(url, json=payload)
            else:
                response = await client.get(url)
            response.raise_for_status()
    except httpx.RequestError:
        return {
            "success": False,
            "message": "模型服务不可达",
            "endpoint": normalized,
        }
    except httpx.HTTPStatusError as exc:
        return {
            "success": False,
            "message": f"模型服务返回异常状态：{exc.response.status_code}",
            "endpoint": normalized,
        }
    return {
        "success": True,
        "message": f"模型服务连接成功：{url}",
        "endpoint": normalized,
    }


def _clear_default_for_type(
    services: list[dict[str, Any]],
    service_type: str,
) -> None:
    for existing in services:
        if existing.get("type") == service_type:
            existing["default"] = False


def _ensure_safe_endpoint(endpoint: str, service_type: str) -> None:
    if service_type not in RUNTIME_MODEL_SERVICE_TYPES:
        return
    safety = validate_outbound_http_url(endpoint)
    if not safety.allowed:
        raise ValueError(safety.message)


def _model_probe_request(
    endpoint: str,
    service_type: str,
    api_key: str,
) -> tuple[str, str, dict[str, Any] | None, dict[str, str] | None]:
    normalized = endpoint.rstrip("/")
    headers = _authorization_headers(api_key)
    if service_type == "向量模型":
        return (
            "post",
            normalized if normalized.endswith("/embeddings") else urljoin(normalized + "/", "embeddings"),
            {"input": "ping", "model": "probe"},
            headers,
        )
    if service_type == "重排序模型":
        return (
            "post",
            normalized if normalized.endswith("/rerank") else urljoin(normalized + "/", "rerank"),
            {"query": "ping", "documents": ["ping"]},
            headers,
        )
    return (
        "get",
        normalized if normalized.endswith("/models") else urljoin(normalized + "/", "models"),
        None,
        headers,
    )


def build_model_probe(
    endpoint: str,
    service_type: str,
    api_key: str,
) -> tuple[str, str, dict[str, Any] | None, dict[str, str] | None]:
    return _model_probe_request(endpoint.strip(), service_type, api_key)


def _authorization_headers(api_key: str) -> dict[str, str] | None:
    normalized = api_key.strip()
    if not normalized:
        return None
    return {"Authorization": f"Bearer {normalized}"}
