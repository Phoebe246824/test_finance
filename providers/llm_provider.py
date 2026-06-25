"""LLM 提供商配置与按工作流 stage 路由。"""

from __future__ import annotations

import asyncio
import logging
import os

from crewai import LLM
from crewai.agent.planning_config import PlanningConfig
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

_ACTIVE_LLMS: list[LLM] = []
logger = logging.getLogger(__name__)

STAGE_TIERS: dict[str, str] = {
    "normalize": "extract",
    "classify": "extract",
    "graphiti": "extract",
    "risk_first": "reason",
    "risk_second": "reason",
    "dashboard": "reason",
}

_TIER_ENV_PREFIXES: dict[str, str] = {
    "extract": "LLM_EXTRACT",
    "reason": "LLM_REASON",
}

REASON_MAX_ATTEMPTS = int(os.getenv("REASON_MAX_ATTEMPTS") or "2")
REASON_MAX_STEPS = int(os.getenv("REASON_MAX_STEPS") or "4")

_TIER_SERVICE_TYPES: dict[str, list[str]] = {
    "extract": ["大语言模型"],
    "reason": ["大语言模型"],
}
RUNNABLE_MODEL_STATUS = "运行中"


def _settings_model_params() -> dict[str, float | int]:
    try:
        from backend.app.services.settings_service import load_app_settings
        settings, _ = load_app_settings()
        raw = settings.get("model_params") or {}
        return _coerce_model_params(raw)
    except Exception:
        return {}


def _coerce_model_params(raw: object) -> dict[str, float | int]:
    if not isinstance(raw, dict):
        return {}
    coerced: dict[str, float | int] = {}
    for key in ("maxTokens", "timeout", "concurrency"):
        value = raw.get(key)
        if isinstance(value, int) and value > 0:
            coerced[key] = value
    for key in ("temperature", "topP", "repetitionPenalty"):
        value = raw.get(key)
        if isinstance(value, int | float):
            coerced[key] = float(value)
    return coerced


def _settings_service_endpoint(service_type: str) -> str | None:
    try:
        from backend.app.services.settings_service import load_app_settings
        settings, _ = load_app_settings()
        services = settings.get("model_services") or []
        candidates = [
            s for s in services
            if s.get("type") == service_type and s.get("status") == RUNNABLE_MODEL_STATUS
        ]
        if not candidates:
            return None
        default_svc = next((s for s in candidates if s.get("default")), candidates[0])
        return default_svc.get("endpoint") or None
    except Exception:
        return None


def _tier_service_endpoint(tier: str) -> str | None:
    for service_type in _TIER_SERVICE_TYPES.get(tier, []):
        endpoint = _settings_service_endpoint(service_type)
        if endpoint:
            return endpoint
    return None


def _tier_for_stage(stage: str) -> str:
    """返回 stage 对应的模型档位，未知 stage 直接失败。"""
    try:
        return STAGE_TIERS[stage]
    except KeyError as exc:
        known_stages = ", ".join(sorted(STAGE_TIERS))
        raise ValueError(
            f"unknown LLM stage: {stage}. Known stages: {known_stages}"
        ) from exc


def _tier_env(tier: str, name: str) -> str | None:
    """读取某档位的环境变量，未设置时回退到基础 LLM_*。"""
    prefix = _TIER_ENV_PREFIXES[tier]
    return os.getenv(f"{prefix}_{name}") or os.getenv(f"LLM_{name}")


def _stage_llm_config(stage: str) -> dict[str, str]:
    """解析 stage 对应的 OpenAI-compatible LLM 连接配置。"""
    tier = _tier_for_stage(stage)
    settings_endpoint = _tier_service_endpoint(tier)
    base_url = settings_endpoint or _tier_env(tier, "BASE_URL")
    if not base_url:
        logger.warning(
            "LLM stage %s is falling back to default cloud LLM base_url "
            "https://api.openai.com/v1; this may accidentally connect to "
            "cloud services and violate the local demo constraint.",
            stage,
        )
    return {
        "model": _tier_env(tier, "MODEL") or "gpt-4o",
        "api_key": _tier_env(tier, "API_KEY") or "",
        "base_url": base_url or "https://api.openai.com/v1",
    }


def get_siliconflow_llm(model=None, temperature=None, api_key=None, base_url=None):
    """获取硅基流动或 OpenAI-compatible LLM 实例。"""
    if not model:
        model = os.getenv("LLM_MODEL") or "gpt-4o"
    params = _settings_model_params()
    llm_temperature = (
        float(temperature)
        if temperature is not None
        else float(params.get("temperature", 0.7))
    )
    llm = LLM(
        model=model,
        max_completion_tokens=int(params.get("maxTokens", 8192)),
        top_p=float(params.get("topP", 0.85)),
        api_key=api_key or os.getenv("LLM_API_KEY") or "",
        base_url=base_url or os.getenv("LLM_BASE_URL") or "https://api.openai.com/v1",
        temperature=llm_temperature,
        timeout=int(params.get("timeout", 60)),
        frequency_penalty=float(params.get("repetitionPenalty", 0.0)),
        provider="openai",
    )
    _ACTIVE_LLMS.append(llm)
    return llm


def get_llm_for(stage: str, temperature: float | None = None) -> LLM:
    """按工作流 stage 获取 LLM，call site 只声明语义 stage。"""
    llm_config = _stage_llm_config(stage)
    return get_siliconflow_llm(
        model=llm_config["model"],
        temperature=temperature,
        api_key=llm_config["api_key"],
        base_url=llm_config["base_url"],
    )


def reasoning_kwargs_for(stage: str) -> dict[str, PlanningConfig]:
    """返回 CrewAI Agent reasoning 参数；抽取档保持默认关闭。"""
    tier = _tier_for_stage(stage)
    if tier != "reason" or stage == "dashboard":
        return {}
    return {
        "planning_config": PlanningConfig(
            max_attempts=REASON_MAX_ATTEMPTS,
            max_steps=REASON_MAX_STEPS,
        ),
    }


def get_llm(model=None, temperature=0.7, provider=None, api_key=None, base_url=None):
    """根据提供商获取 LLM 实例，保留旧入口向后兼容。"""
    provider = provider or os.getenv("LLM_PROVIDER") or "openai"
    if provider in ("siliconflow", "openai"):
        return get_siliconflow_llm(
            model=model,
            temperature=temperature,
            api_key=api_key,
            base_url=base_url,
        )
    raise ValueError(f"不支持的LLM提供商: {provider}")


async def close_all_llms() -> None:
    """关闭所有已创建的 LLM 客户端，避免程序退出时残留异步连接。"""
    seen: set[int] = set()
    for llm in list(_ACTIVE_LLMS):
        if llm is None:
            continue
        llm_id = id(llm)
        if llm_id in seen:
            continue
        seen.add(llm_id)
        try:
            async_client = llm._get_async_client()
            if async_client is not None and not getattr(
                async_client, "is_closed", True
            ):
                if hasattr(async_client, "aclose"):
                    await async_client.aclose()
                else:
                    close_result = async_client.close()
                    if asyncio.iscoroutine(close_result):
                        await close_result
        except RuntimeError as e:
            if "Event loop is closed" not in str(e):
                raise
        except Exception:
            # 退出清理阶段尽量静默，不影响主流程结束
            pass
    _ACTIVE_LLMS.clear()
