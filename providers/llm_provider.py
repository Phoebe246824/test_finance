"""LLM提供商配置管理"""
from __future__ import annotations

import asyncio
import os
from typing import Any

from crewai import LLM
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

_ACTIVE_LLMS: list[Any] = []


def get_siliconflow_llm(model=None, temperature=0.7, api_key=None, base_url=None):
    """获取硅基流动LLM实例"""
    # 确保模型名称不为空
    if not model:
        model = os.getenv("LLM_MODEL") or "gpt-4o"
    llm = LLM(
        model=model,
        # max_tokens=5120,
        max_completion_tokens=8192,
        top_p=0.85,
        api_key=api_key or os.getenv("LLM_API_KEY") or "",
        base_url=base_url or os.getenv("LLM_BASE_URL") or "https://api.openai.com/v1",
        temperature=temperature,
        provider="openai"
    )
    _ACTIVE_LLMS.append(llm)
    return llm


def get_llm(model=None, temperature=0.7, provider=None, api_key=None, base_url=None):
    """根据提供商获取LLM实例"""
    provider = provider or os.getenv("LLM_PROVIDER") or "openai"
    if provider in ("siliconflow", "openai"):
        return get_siliconflow_llm(model=model, temperature=temperature, api_key=api_key, base_url=base_url)
    else:
        raise ValueError(f"不支持的LLM提供商: {provider}")


async def close_all_llms() -> None:
    """关闭所有已创建的 LLM 客户端，避免程序退出时残留异步连接。"""
    global _ACTIVE_LLMS
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
            if async_client is not None and not getattr(async_client, "is_closed", True):
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
