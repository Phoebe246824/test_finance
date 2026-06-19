# LLM Stage Routing Reasoning Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route workflow LLM calls by semantic stage and enable CrewAI native reasoning only for risk and dashboard judgement agents.

**Architecture:** `providers/llm_provider.py` becomes the central stage-to-tier router for CrewAI agents, while call sites in `main.py` declare only their stage name. Graphiti keeps its existing client factory, but its LLM extraction client resolves `LLM_EXTRACT_*` before the old base `LLM_*` values so `load_config()` does not silently bypass the extract tier.

**Tech Stack:** Python 3.13, CrewAI `LLM`/`Agent`, Graphiti OpenAI-compatible client, python-dotenv, pytest, uv.

---

## File Structure

- Modify `providers/llm_provider.py`: add `STAGE_TIERS`, tier env resolution, `get_llm_for(stage, temperature)`, and `reasoning_kwargs_for(stage)` while keeping `get_llm(...)` compatible.
- Modify `main.py`: replace five `get_llm(...)` call sites with `get_llm_for(...)`; add `reasoning_kwargs_for(...)` only to `risk_first`, `risk_second`, and `dashboard` agents.
- Modify `graphiti/graphiti_workflow.py`: make the Graphiti LLM client prefer `LLM_EXTRACT_*`; add a small resolver helper so tests can verify config precedence without real Neo4j or LLM calls.
- Modify `.env.example`: document blank extract/reason tier endpoint variables and `REASON_MAX_ATTEMPTS=2`.
- Modify `docs/env-vars.md`: document the new variables and fallback rules.
- Create `tests/test_llm_stage_routing.py`: unit tests for provider routing, active LLM registration, unknown stages, and reasoning kwargs.
- Create `tests/test_main_llm_stage_wiring.py`: source-level wiring tests for the intended `main.py` stage declarations.
- Create `tests/test_graphiti_extract_llm_routing.py`: unit tests for Graphiti extract LLM config precedence.

## Notes Before Starting

- Do not edit `graphiti_core/`; this refactor stays in the project wrapper layer.
- Do not edit `.env`; update `.env.example` and `docs/env-vars.md` only.
- Keep `parse_llm_json_object(...)` unchanged.
- Keep `get_llm(...)` available for backwards compatibility.
- Do not add Qwen `<think>` parsing, `enable_thinking`, `extra_body`, or `reasoning_effort`.

### Task 1: Provider Stage Router

**Files:**
- Modify: `providers/llm_provider.py:1-69`
- Create: `tests/test_llm_stage_routing.py`

- [ ] **Step 1: Write the failing provider routing tests**

Create `tests/test_llm_stage_routing.py` with this content:

```python
import importlib

import pytest


BASE_ENV = {
    'LLM_MODEL': 'base-model',
    'LLM_API_KEY': 'base-key',
    'LLM_BASE_URL': 'http://base-llm.test/v1',
}

STAGE_ENV_KEYS = [
    'LLM_EXTRACT_MODEL',
    'LLM_EXTRACT_API_KEY',
    'LLM_EXTRACT_BASE_URL',
    'LLM_REASON_MODEL',
    'LLM_REASON_API_KEY',
    'LLM_REASON_BASE_URL',
]


def reload_provider(monkeypatch, env: dict[str, str]):
    for key in STAGE_ENV_KEYS:
        monkeypatch.setenv(key, '')
    for key, value in BASE_ENV.items():
        monkeypatch.setenv(key, value)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    import providers.llm_provider as llm_provider

    return importlib.reload(llm_provider)


def test_get_llm_for_uses_base_llm_when_tier_env_is_blank(monkeypatch):
    llm_provider = reload_provider(monkeypatch, {'REASON_MAX_ATTEMPTS': '2'})

    extract_llm = llm_provider.get_llm_for('normalize', 0.3)
    reason_llm = llm_provider.get_llm_for('risk_first', 0.1)

    assert extract_llm.model == 'base-model'
    assert extract_llm.api_key == 'base-key'
    assert extract_llm.base_url == 'http://base-llm.test/v1'
    assert extract_llm.temperature == 0.3

    assert reason_llm.model == 'base-model'
    assert reason_llm.api_key == 'base-key'
    assert reason_llm.base_url == 'http://base-llm.test/v1'
    assert reason_llm.temperature == 0.1
    assert extract_llm in llm_provider._ACTIVE_LLMS
    assert reason_llm in llm_provider._ACTIVE_LLMS


def test_get_llm_for_prefers_tier_specific_endpoint(monkeypatch):
    llm_provider = reload_provider(
        monkeypatch,
        {
            'LLM_EXTRACT_MODEL': 'extract-model',
            'LLM_EXTRACT_API_KEY': 'extract-key',
            'LLM_EXTRACT_BASE_URL': 'http://extract-llm.test/v1',
            'LLM_REASON_MODEL': 'reason-model',
            'LLM_REASON_API_KEY': 'reason-key',
            'LLM_REASON_BASE_URL': 'http://reason-llm.test/v1',
            'REASON_MAX_ATTEMPTS': '2',
        },
    )

    classify_llm = llm_provider.get_llm_for('classify', 0.3)
    risk_llm = llm_provider.get_llm_for('risk_second', 0.1)

    assert classify_llm.model == 'extract-model'
    assert classify_llm.api_key == 'extract-key'
    assert classify_llm.base_url == 'http://extract-llm.test/v1'

    assert risk_llm.model == 'reason-model'
    assert risk_llm.api_key == 'reason-key'
    assert risk_llm.base_url == 'http://reason-llm.test/v1'


def test_get_llm_for_rejects_unknown_stage(monkeypatch):
    llm_provider = reload_provider(monkeypatch, {'REASON_MAX_ATTEMPTS': '2'})

    with pytest.raises(ValueError, match='unknown LLM stage'):
        llm_provider.get_llm_for('unknown_stage', 0.3)


def test_reasoning_kwargs_are_enabled_only_for_reason_tier(monkeypatch):
    llm_provider = reload_provider(monkeypatch, {'REASON_MAX_ATTEMPTS': '4'})

    assert llm_provider.reasoning_kwargs_for('risk_first') == {
        'reasoning': True,
        'max_reasoning_attempts': 4,
    }
    assert llm_provider.reasoning_kwargs_for('risk_second') == {
        'reasoning': True,
        'max_reasoning_attempts': 4,
    }
    assert llm_provider.reasoning_kwargs_for('dashboard') == {
        'reasoning': True,
        'max_reasoning_attempts': 4,
    }
    assert llm_provider.reasoning_kwargs_for('normalize') == {}
    assert llm_provider.reasoning_kwargs_for('classify') == {}
    assert llm_provider.reasoning_kwargs_for('graphiti') == {}


def test_reasoning_kwargs_default_to_two_attempts(monkeypatch):
    llm_provider = reload_provider(monkeypatch, {'REASON_MAX_ATTEMPTS': ''})

    assert llm_provider.reasoning_kwargs_for('dashboard') == {
        'reasoning': True,
        'max_reasoning_attempts': 2,
    }
```

- [ ] **Step 2: Run the provider tests and verify the expected failure**

Run:

```bash
uv run pytest tests/test_llm_stage_routing.py -q
```

Expected: FAIL because `providers.llm_provider` does not yet expose `get_llm_for` or `reasoning_kwargs_for`.

- [ ] **Step 3: Implement the provider router**

Replace `providers/llm_provider.py` with this content:

```python
"""LLM 提供商配置与按工作流 stage 路由。"""

from __future__ import annotations

import asyncio
import os

from crewai import LLM
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

_ACTIVE_LLMS: list[LLM] = []

STAGE_TIERS: dict[str, str] = {
    'normalize': 'extract',
    'classify': 'extract',
    'graphiti': 'extract',
    'risk_first': 'reason',
    'risk_second': 'reason',
    'dashboard': 'reason',
}

_TIER_ENV_PREFIXES: dict[str, str] = {
    'extract': 'LLM_EXTRACT',
    'reason': 'LLM_REASON',
}

REASON_MAX_ATTEMPTS = int(os.getenv('REASON_MAX_ATTEMPTS') or '2')


def _tier_for_stage(stage: str) -> str:
    """返回 stage 对应的模型档位，未知 stage 直接失败。"""
    try:
        return STAGE_TIERS[stage]
    except KeyError as exc:
        known_stages = ', '.join(sorted(STAGE_TIERS))
        raise ValueError(
            f'unknown LLM stage: {stage}. Known stages: {known_stages}'
        ) from exc


def _tier_env(tier: str, name: str) -> str | None:
    """读取某档位的环境变量，未设置时回退到基础 LLM_*。"""
    prefix = _TIER_ENV_PREFIXES[tier]
    return os.getenv(f'{prefix}_{name}') or os.getenv(f'LLM_{name}')


def _stage_llm_config(stage: str) -> dict[str, str]:
    """解析 stage 对应的 OpenAI-compatible LLM 连接配置。"""
    tier = _tier_for_stage(stage)
    return {
        'model': _tier_env(tier, 'MODEL') or 'gpt-4o',
        'api_key': _tier_env(tier, 'API_KEY') or '',
        'base_url': _tier_env(tier, 'BASE_URL') or 'https://api.openai.com/v1',
    }


def get_siliconflow_llm(model=None, temperature=0.7, api_key=None, base_url=None):
    """获取硅基流动或 OpenAI-compatible LLM 实例。"""
    if not model:
        model = os.getenv('LLM_MODEL') or 'gpt-4o'
    llm = LLM(
        model=model,
        max_completion_tokens=8192,
        top_p=0.85,
        api_key=api_key or os.getenv('LLM_API_KEY') or '',
        base_url=base_url or os.getenv('LLM_BASE_URL') or 'https://api.openai.com/v1',
        temperature=temperature,
        provider='openai',
    )
    _ACTIVE_LLMS.append(llm)
    return llm


def get_llm_for(stage: str, temperature: float | None = None) -> LLM:
    """按工作流 stage 获取 LLM，call site 只声明语义 stage。"""
    llm_config = _stage_llm_config(stage)
    return get_siliconflow_llm(
        model=llm_config['model'],
        temperature=0.7 if temperature is None else temperature,
        api_key=llm_config['api_key'],
        base_url=llm_config['base_url'],
    )


def reasoning_kwargs_for(stage: str) -> dict[str, int | bool]:
    """返回 CrewAI Agent reasoning 参数；抽取档保持默认关闭。"""
    tier = _tier_for_stage(stage)
    if tier != 'reason':
        return {}
    return {
        'reasoning': True,
        'max_reasoning_attempts': REASON_MAX_ATTEMPTS,
    }


def get_llm(model=None, temperature=0.7, provider=None, api_key=None, base_url=None):
    """根据提供商获取 LLM 实例，保留旧入口向后兼容。"""
    provider = provider or os.getenv('LLM_PROVIDER') or 'openai'
    if provider in ('siliconflow', 'openai'):
        return get_siliconflow_llm(
            model=model,
            temperature=temperature,
            api_key=api_key,
            base_url=base_url,
        )
    raise ValueError(f'不支持的LLM提供商: {provider}')


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
                async_client, 'is_closed', True
            ):
                if hasattr(async_client, 'aclose'):
                    await async_client.aclose()
                else:
                    close_result = async_client.close()
                    if asyncio.iscoroutine(close_result):
                        await close_result
        except RuntimeError as e:
            if 'Event loop is closed' not in str(e):
                raise
        except Exception:
            # 退出清理阶段尽量静默，不影响主流程结束
            pass
    _ACTIVE_LLMS.clear()
```

- [ ] **Step 4: Run the provider tests and verify they pass**

Run:

```bash
uv run pytest tests/test_llm_stage_routing.py -q
```

Expected: PASS with `6 passed`.

- [ ] **Step 5: Commit provider routing**

Run:

```bash
git add providers/llm_provider.py tests/test_llm_stage_routing.py
git commit -m "refactor(llm): add stage-based routing provider"
```

Expected: commit succeeds and includes only the provider file plus its tests.

### Task 2: Main Pipeline Stage Wiring

**Files:**
- Modify: `main.py:64`
- Modify: `main.py:355-360`
- Modify: `main.py:440-453`
- Modify: `main.py:511-519`
- Modify: `main.py:1003-1068`
- Modify: `main.py:1160`
- Create: `tests/test_main_llm_stage_wiring.py`

- [ ] **Step 1: Write the failing main wiring tests**

Create `tests/test_main_llm_stage_wiring.py` with this content:

```python
import inspect

import main


def _function_source(name: str) -> str:
    return inspect.getsource(getattr(main, name))


def test_main_imports_stage_router_helpers():
    module_source = inspect.getsource(main)

    assert 'get_llm_for' in module_source
    assert 'reasoning_kwargs_for' in module_source
    assert (
        'from providers.llm_provider import close_all_llms, get_llm'
        not in module_source
    )


def test_main_stage_llm_call_sites_use_semantic_router():
    assert 'get_llm_for("classify", 0.3)' in _function_source('classify_event')
    assert 'get_llm_for("risk_first", 0.1)' in _function_source('evaluate_risk')
    assert 'get_llm_for("risk_second", 0.1)' in _function_source(
        'second_evaluate_risk'
    )
    assert 'get_llm_for("dashboard", 0.3)' in _function_source('simulate_dashboard')
    assert 'get_llm_for("normalize", 0.3)' in _function_source(
        'normalize_payload_to_event'
    )


def test_main_reasoning_kwargs_are_attached_to_reasoning_agents_only():
    assert '**reasoning_kwargs_for("risk_first")' in _function_source('evaluate_risk')
    assert '**reasoning_kwargs_for("risk_second")' in _function_source(
        'second_evaluate_risk'
    )
    dashboard_source = _function_source('simulate_dashboard')
    assert dashboard_source.count('**reasoning_kwargs_for("dashboard")') == 2

    assert 'reasoning_kwargs_for("classify")' not in _function_source('classify_event')
    assert 'reasoning_kwargs_for("normalize")' not in _function_source(
        'normalize_payload_to_event'
    )
```

- [ ] **Step 2: Run the main wiring tests and verify the expected failure**

Run:

```bash
uv run pytest tests/test_main_llm_stage_wiring.py -q
```

Expected: FAIL because `main.py` still imports and calls `get_llm(...)`.

- [ ] **Step 3: Update the `main.py` provider import**

Replace the import at `main.py:64`:

```python
from providers.llm_provider import close_all_llms, get_llm
```

with:

```python
from providers.llm_provider import (
    close_all_llms,
    get_llm_for,
    reasoning_kwargs_for,
)
```

- [ ] **Step 4: Route classification through the extract tier**

Replace the `llm = ...` block in `classify_event(...)`:

```python
    llm = get_llm(
        model=config["llm"]["model"],
        api_key=config["llm"]["api_key"],
        base_url=config["llm"]["base_url"],
        temperature=0.3,
    )
```

with:

```python
    llm = get_llm_for("classify", 0.3)
```

- [ ] **Step 5: Route first risk evaluation through the reason tier**

Replace the `llm = ...` block in `evaluate_risk(...)`:

```python
    llm = get_llm(
        model=config["llm"]["model"],
        api_key=config["llm"]["api_key"],
        base_url=config["llm"]["base_url"],
        temperature=0.1,
    )
```

with:

```python
    llm = get_llm_for("risk_first", 0.1)
```

Then add the reasoning kwargs to the same function's `risk_evaluator = Agent(...)` call:

```python
    risk_evaluator = Agent(
        llm=llm,
        role="风险评估专家",
        goal="评估事件的风险等级和风险分数",
        backstory="你是一位风险评估专家，擅长评估事件的潜在风险。",
        verbose=True,
        **reasoning_kwargs_for("risk_first"),
    )
```

- [ ] **Step 6: Route second risk evaluation through the reason tier**

Replace:

```python
    llm = get_llm(temperature=0.1)
```

with:

```python
    llm = get_llm_for("risk_second", 0.1)
```

Then update the `risk_evaluator = Agent(...)` call in `second_evaluate_risk(...)`:

```python
    risk_evaluator = Agent(
        llm=llm,
        role="风险评估专家",
        goal="评估事件的风险等级和风险分数",
        backstory="你是一位风险评估专家，擅长评估事件的潜在风险。",
        verbose=True,
        **reasoning_kwargs_for("risk_second"),
    )
```

- [ ] **Step 7: Route dashboard analysis through the reason tier**

Replace:

```python
    llm = get_llm(temperature=0.3)
```

with:

```python
    llm = get_llm_for("dashboard", 0.3)
```

Then update `intent_analyzer = Agent(...)`:

```python
    intent_analyzer = Agent(
        llm=llm,
        role="意图分析专家",
        goal="深入分析事件背后的真实意图、动机和潜在影响",
        backstory=(
            "你是一个资深的意图分析专家，擅长从复杂的事件描述中挖掘真实意图。"
            f"当前事件分类为「{category_name}」，请从该领域的专业视角进行分析。"
        ),
        verbose=True,
        allow_delegation=False,
        **reasoning_kwargs_for("dashboard"),
    )
```

Then update `trend_predictor = Agent(...)`:

```python
    trend_predictor = Agent(
        llm=llm,
        role="趋势预测专家",
        goal="基于事件意图分析，预测事件的发展趋势和可能的演变路径",
        backstory=(
            "你是一个资深的趋势预测专家，擅长基于事件意图分析预测发展趋势。"
            f"当前事件分类为「{category_name}」，影响严重度为「{severity_name}」。"
        ),
        verbose=True,
        allow_delegation=False,
        **reasoning_kwargs_for("dashboard"),
    )
```

- [ ] **Step 8: Route normalization through the extract tier**

Replace:

```python
        llm = get_llm(temperature=0.3)
```

with:

```python
        llm = get_llm_for("normalize", 0.3)
```

- [ ] **Step 9: Run the main wiring tests and verify they pass**

Run:

```bash
uv run pytest tests/test_main_llm_stage_wiring.py -q
```

Expected: PASS with `3 passed`.

- [ ] **Step 10: Run provider and main wiring tests together**

Run:

```bash
uv run pytest tests/test_llm_stage_routing.py tests/test_main_llm_stage_wiring.py -q
```

Expected: PASS with `9 passed`.

- [ ] **Step 11: Commit main stage wiring**

Run:

```bash
git add main.py tests/test_main_llm_stage_wiring.py
git commit -m "refactor(pipeline): route llm calls by stage"
```

Expected: commit succeeds and includes only `main.py` plus the main wiring tests.

### Task 3: Graphiti Extract LLM Routing

**Files:**
- Modify: `graphiti/graphiti_workflow.py:31-36`
- Modify: `graphiti/graphiti_workflow.py:162-164`
- Create: `tests/test_graphiti_extract_llm_routing.py`

- [ ] **Step 1: Write the failing Graphiti routing tests**

Create `tests/test_graphiti_extract_llm_routing.py` with this content:

```python
from graphiti import graphiti_workflow as workflow


def test_graphiti_llm_config_prefers_extract_env_over_base_config(monkeypatch):
    monkeypatch.setenv('LLM_EXTRACT_API_KEY', 'extract-key')
    monkeypatch.setenv('LLM_EXTRACT_BASE_URL', 'http://extract-llm.test/v1')
    monkeypatch.setenv('LLM_EXTRACT_MODEL', 'extract-model')

    resolved = workflow._resolve_graphiti_llm_config(
        {
            'api_key': 'base-key-from-config',
            'base_url': 'http://base-config.test/v1',
            'model': 'base-model-from-config',
        }
    )

    assert resolved == {
        'api_key': 'extract-key',
        'base_url': 'http://extract-llm.test/v1',
        'model': 'extract-model',
    }


def test_graphiti_llm_config_falls_back_to_base_config_when_extract_env_is_blank(
    monkeypatch,
):
    monkeypatch.setenv('LLM_EXTRACT_API_KEY', '')
    monkeypatch.setenv('LLM_EXTRACT_BASE_URL', '')
    monkeypatch.setenv('LLM_EXTRACT_MODEL', '')

    resolved = workflow._resolve_graphiti_llm_config(
        {
            'api_key': 'base-key-from-config',
            'base_url': 'http://base-config.test/v1',
            'model': 'base-model-from-config',
        }
    )

    assert resolved == {
        'api_key': 'base-key-from-config',
        'base_url': 'http://base-config.test/v1',
        'model': 'base-model-from-config',
    }


def test_graphiti_llm_config_uses_module_defaults_without_config(monkeypatch):
    monkeypatch.setenv('LLM_EXTRACT_API_KEY', '')
    monkeypatch.setenv('LLM_EXTRACT_BASE_URL', '')
    monkeypatch.setenv('LLM_EXTRACT_MODEL', '')

    resolved = workflow._resolve_graphiti_llm_config()

    assert resolved['api_key'] == workflow.LLM_API_KEY
    assert resolved['base_url'] == workflow.LLM_BASE_URL
    assert resolved['model'] == workflow.LLM_MODEL
```

- [ ] **Step 2: Run the Graphiti routing tests and verify the expected failure**

Run:

```bash
uv run pytest tests/test_graphiti_extract_llm_routing.py -q
```

Expected: FAIL because `graphiti.graphiti_workflow` does not yet expose `_resolve_graphiti_llm_config`.

- [ ] **Step 3: Add Graphiti extract env helpers**

In `graphiti/graphiti_workflow.py`, replace the current LLM constants:

```python
LLM_API_KEY = os.environ.get("LLM_API_KEY")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL") or "https://api.openai.com/v1"
LLM_MODEL = os.environ.get("LLM_MODEL") or "gpt-4o"
```

with:

```python
def _get_llm_extract_env(name: str) -> str | None:
    """读取 Graphiti 抽取档 LLM 环境变量，未设置时回退到基础 LLM_*。"""
    return os.environ.get(f"LLM_EXTRACT_{name}") or os.environ.get(f"LLM_{name}")


LLM_API_KEY = _get_llm_extract_env("API_KEY")
LLM_BASE_URL = _get_llm_extract_env("BASE_URL") or "https://api.openai.com/v1"
LLM_MODEL = _get_llm_extract_env("MODEL") or "gpt-4o"
```

Below the reranker constants and above the credential validation comment, add:

```python
def _resolve_graphiti_llm_config(
    llm_config: dict[str, Any] | None = None,
) -> dict[str, str | None]:
    """解析 Graphiti 内部抽取 LLM 配置。

    `main.load_config()` 会携带基础 `LLM_*` 配置传入 Graphiti。这里让
    `LLM_EXTRACT_*` 优先于传入 config，确保 Graphiti 抽取走 extract 档。
    """
    llm_config = llm_config or {}
    return {
        "api_key": os.environ.get("LLM_EXTRACT_API_KEY")
        or llm_config.get("api_key")
        or LLM_API_KEY,
        "base_url": os.environ.get("LLM_EXTRACT_BASE_URL")
        or llm_config.get("base_url")
        or LLM_BASE_URL,
        "model": os.environ.get("LLM_EXTRACT_MODEL")
        or llm_config.get("model")
        or LLM_MODEL,
    }
```

- [ ] **Step 4: Use the resolver inside `init_graph_client(...)`**

Replace:

```python
    llm_api_key = llm_config.get("api_key") or LLM_API_KEY
    llm_base_url = llm_config.get("base_url") or LLM_BASE_URL
    llm_model = llm_config.get("model") or LLM_MODEL
```

with:

```python
    graphiti_llm_config = _resolve_graphiti_llm_config(llm_config)
    llm_api_key = graphiti_llm_config["api_key"]
    llm_base_url = graphiti_llm_config["base_url"]
    llm_model = graphiti_llm_config["model"]
```

- [ ] **Step 5: Run the Graphiti routing tests and verify they pass**

Run:

```bash
uv run pytest tests/test_graphiti_extract_llm_routing.py -q
```

Expected: PASS with `3 passed`.

- [ ] **Step 6: Run the existing Graphiti import-safety regressions**

Run:

```bash
uv run pytest tests/test_milvus_stash_flow.py::test_import_graphiti_workflow_without_llm_key tests/test_milvus_stash_flow.py::test_init_graph_client_rejects_missing_llm_key tests/test_milvus_stash_flow.py::test_init_graph_client_rejects_missing_neo4j_creds -q
```

Expected: PASS with `3 passed`.

- [ ] **Step 7: Commit Graphiti extract routing**

Run:

```bash
git add graphiti/graphiti_workflow.py tests/test_graphiti_extract_llm_routing.py
git commit -m "refactor(graphiti): route extraction llm env"
```

Expected: commit succeeds and includes only the Graphiti wrapper plus its tests.

### Task 4: Env Skeleton and Documentation

**Files:**
- Modify: `.env.example:30-47`
- Modify: `docs/env-vars.md:16-20`

- [ ] **Step 1: Add tier endpoint skeleton to `.env.example`**

In `.env.example`, insert this block immediately after the existing base LLM values:

```bash
# 抽取档（高频 JSON：normalize/classify/Graphiti）；留空回退 LLM_*
LLM_EXTRACT_BASE_URL=
LLM_EXTRACT_MODEL=
LLM_EXTRACT_API_KEY=
# 研判档（reasoning：风险评估/报告）；留空回退 LLM_*
LLM_REASON_BASE_URL=
LLM_REASON_MODEL=
LLM_REASON_API_KEY=
# 研判档 reasoning 多轮上限（控演示延迟）
REASON_MAX_ATTEMPTS=2
```

The resulting LLM section should read:

```bash
# ============ LLM 配置 (聊天模型) ============
# 参赛建议：优先接入本地 OpenAI-compatible 服务，核心推理不上传隐私数据。
# 示例 A: LM Studio
#   LLM_PROVIDER=openai
#   LLM_MODEL=qwen2.5-14b-instruct
#   LLM_API_KEY=lm-studio
#   LLM_BASE_URL=http://127.0.0.1:1234/v1
# 示例 B: Ollama OpenAI-compatible endpoint
#   LLM_PROVIDER=openai
#   LLM_MODEL=qwen2.5:14b-instruct-q4_K_M
#   LLM_API_KEY=ollama
#   LLM_BASE_URL=http://127.0.0.1:11434/v1
LLM_PROVIDER=openai
LLM_MODEL=qwen3.5
LLM_API_KEY=ollama
LLM_BASE_URL=http://127.0.0.1:11434/v1
# 抽取档（高频 JSON：normalize/classify/Graphiti）；留空回退 LLM_*
LLM_EXTRACT_BASE_URL=
LLM_EXTRACT_MODEL=
LLM_EXTRACT_API_KEY=
# 研判档（reasoning：风险评估/报告）；留空回退 LLM_*
LLM_REASON_BASE_URL=
LLM_REASON_MODEL=
LLM_REASON_API_KEY=
# 研判档 reasoning 多轮上限（控演示延迟）
REASON_MAX_ATTEMPTS=2
```

- [ ] **Step 2: Document new env vars in `docs/env-vars.md`**

Insert these table rows immediately after `LLM_BASE_URL`:

```markdown
| `LLM_EXTRACT_MODEL` | 抽取档聊天模型名称；留空回退 `LLM_MODEL` | 继承 `LLM_MODEL` |
| `LLM_EXTRACT_API_KEY` | 抽取档 API 密钥；留空回退 `LLM_API_KEY` | 继承 `LLM_API_KEY` |
| `LLM_EXTRACT_BASE_URL` | 抽取档 API 地址；留空回退 `LLM_BASE_URL` | 继承 `LLM_BASE_URL` |
| `LLM_REASON_MODEL` | 研判档聊天模型名称；留空回退 `LLM_MODEL` | 继承 `LLM_MODEL` |
| `LLM_REASON_API_KEY` | 研判档 API 密钥；留空回退 `LLM_API_KEY` | 继承 `LLM_API_KEY` |
| `LLM_REASON_BASE_URL` | 研判档 API 地址；留空回退 `LLM_BASE_URL` | 继承 `LLM_BASE_URL` |
| `REASON_MAX_ATTEMPTS` | CrewAI reasoning 规划/反思最大尝试次数，仅用于研判档 Agent | 2 |
```

Then replace the final paragraph:

```markdown
LLM / Embedder / Reranker 三组凭证独立，可分别配置不同的 API 地址和密钥。
```

with:

```markdown
LLM / Embedder / Reranker 三组凭证独立，可分别配置不同的 API 地址和密钥。`LLM_EXTRACT_*` 与 `LLM_REASON_*` 是聊天 LLM 的工作流分档：留空时复用基础 `LLM_*`，需要多模型常驻时分别指向快抽取模型和高质量研判模型。
```

- [ ] **Step 3: Verify docs diff only touches intended files**

Run:

```bash
git diff -- .env.example docs/env-vars.md
```

Expected: diff shows only the new tier env rows and final paragraph update.

- [ ] **Step 4: Commit env documentation**

Run:

```bash
git add .env.example docs/env-vars.md
git commit -m "docs(env): document llm stage tiers"
```

Expected: commit succeeds and does not include `.env`.

### Task 5: Full Verification and Manual Demo Check

**Files:**
- Verify: `providers/llm_provider.py`
- Verify: `main.py`
- Verify: `graphiti/graphiti_workflow.py`
- Verify: `.env.example`
- Verify: `docs/env-vars.md`
- Verify: `tests/test_llm_stage_routing.py`
- Verify: `tests/test_main_llm_stage_wiring.py`
- Verify: `tests/test_graphiti_extract_llm_routing.py`

- [ ] **Step 1: Run the focused refactor tests**

Run:

```bash
uv run pytest tests/test_llm_stage_routing.py tests/test_main_llm_stage_wiring.py tests/test_graphiti_extract_llm_routing.py -q
```

Expected: PASS with `12 passed`.

- [ ] **Step 2: Run existing regression tests that exercise Graphiti import safety and pipeline risk scoring**

Run:

```bash
uv run pytest tests/test_milvus_stash_flow.py::test_import_graphiti_workflow_without_llm_key tests/test_milvus_stash_flow.py::test_init_graph_client_rejects_missing_llm_key tests/test_milvus_stash_flow.py::test_init_graph_client_rejects_missing_neo4j_creds tests/test_risk_scoring.py -q
```

Expected: PASS with `4 passed`.

- [ ] **Step 3: Run lint on changed Python files**

Run:

```bash
uv run ruff check providers/llm_provider.py graphiti/graphiti_workflow.py main.py tests/test_llm_stage_routing.py tests/test_main_llm_stage_wiring.py tests/test_graphiti_extract_llm_routing.py
```

Expected: PASS with `All checks passed!`.

- [ ] **Step 4: Run the full test suite**

Run:

```bash
uv run pytest tests/ -q
```

Expected: PASS. If integration services are down, record the failing service-dependent tests and still include the focused test results from Steps 1 and 2 in the final handoff.

- [ ] **Step 5: Run cloud/manual finance cases when LLM and local services are configured**

Run:

```bash
docker compose up -d redis milvus neo4j
GRAPHITI_DRY_RUN=true uv run python scripts/sentinel_competition_demo.py \
  --run-pipeline \
  --case finance_01_low_risk_salary_stash \
  --case finance_04_aml_high_risk_recall
```

Expected:
- Process exits `0`.
- The generated report under `logs/sentinel_competition_demo_*/` contains both selected case IDs.
- `finance_01_low_risk_salary_stash` still completes low-risk/stash behavior.
- `finance_04_aml_high_risk_recall` still reaches risk evaluation, historical recall, second risk evaluation, and dashboard report generation.
- Console or log output shows CrewAI reasoning/planning activity for risk/dashboard agents while normalize/classify/Graphiti extraction remains standard LLM execution.

- [ ] **Step 6: Inspect final diff for forbidden changes**

Run:

```bash
git status --short
git diff --stat
git diff --name-only
```

Expected:
- No changes under `graphiti_core/`.
- No `.env` modification.
- No logs, caches, SQLite databases, or frontend lockfiles added by this refactor.
- Only the files listed in this plan are modified or newly created.

- [ ] **Step 7: Final commit if verification changed any tracked files**

Run:

```bash
git add providers/llm_provider.py main.py graphiti/graphiti_workflow.py .env.example docs/env-vars.md tests/test_llm_stage_routing.py tests/test_main_llm_stage_wiring.py tests/test_graphiti_extract_llm_routing.py
git commit -m "refactor(llm): enable stage routing and reasoning"
```

Expected: If previous task commits were made, Git reports nothing to commit. If the executor batched work without intermediate commits, this final commit succeeds with the full refactor.

## Self-Review

**Spec coverage:** Covered provider routing, stage tier mapping, fail-fast unknown stages, active LLM registration, CrewAI native `reasoning=True`, `REASON_MAX_ATTEMPTS`, five `main.py` call sites, Graphiti extract routing, `.env.example`, `docs/env-vars.md`, focused tests, full tests, and manual finance case validation.

**Explicit exclusions:** No Qwen token-level thinking, no `<think>` stripping, no `enable_thinking`, no `extra_body`, no `reasoning_effort`, no embedding/reranker endpoint changes, no `parse_llm_json_object(...)` changes, no structural `load_config()` refactor.

**Type consistency:** `get_llm_for(stage: str, temperature: float | None = None) -> LLM`; `reasoning_kwargs_for(stage: str) -> dict[str, int | bool]`; `_resolve_graphiti_llm_config(llm_config: dict[str, Any] | None = None) -> dict[str, str | None]`; all stage names match `STAGE_TIERS`.
