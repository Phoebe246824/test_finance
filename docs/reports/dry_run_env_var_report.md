# GRAPHITI_DRY_RUN 环境变量 — 重构报告

## 问题描述

1. **反复调试同一事件时产生重复数据**：开发过程中多次运行 `simulate_graph_build` 调试同一事件，每次都会在 Neo4j 中写入相同的实体和关系，导致图谱中出现重复节点
2. **无法单独测试 LLM 提取效果**：想验证 LLM 提取的实体和关系是否准确，但必须连接 Neo4j 且会产生写入，无法在不污染数据库的情况下调试
3. **调试成本高**：每次调试后需要手动清理 Neo4j 中的测试数据，或重置整个图谱

## 根因分析

1. **无跳过写入机制**：`add_event_to_graph()` 调用 `graphiti.add_episode()` 后必然执行 `_process_episode_data()`，该方法内部调用 `add_nodes_and_edges_bulk()` 写入 Neo4j，无法跳过
2. **无环境变量控制**：没有配置项可以控制是否执行 DB 写入步骤

## 解决方案

新增 `GRAPHITI_DRY_RUN` 环境变量，通过 monkey-patch `_process_episode_data` 为空操作，跳过 Neo4j 写入但保留 LLM 提取流程。

### 架构

```
simulate_graph_build()
  ├─ 读取 GRAPHITI_DRY_RUN 环境变量 → config["graphiti"]["dry_run"]
  ├─ dry_run=True 时打印提示信息
  └─ add_event_to_graph(dry_run=dry_run)
       ├─ LLM 提取实体和关系（正常执行）
       ├─ dry_run=True: monkey-patch _process_episode_data → _noop_process
       │   └─ 跳过 add_nodes_and_edges_bulk()，不写入 Neo4j
       └─ dry_run=False: 正常写入 Neo4j
```

### 数据流

```
事件文本
  │
  ▼
add_event_to_graph(dry_run=True)
  │
  ├─ _summarize_for_extraction()（如启用）→ 摘要文本
  │
  ├─ graphiti.add_episode()
  │   ├─ extract_nodes()          → LLM 提取实体
  │   ├─ resolve_extracted_nodes() → 节点消解
  │   ├─ _extract_and_resolve_edges() → LLM 提取关系
  │   ├─ extract_attributes_from_nodes() → 属性提取
  │   └─ _process_episode_data()  ← monkey-patched
  │       └─ _noop_process()      → 仅设置 entity_edges，不写入 DB
  │
  ▼
AddEpisodeResults(nodes=..., edges=...)  ← 提取结果正常返回
  │
  ▼
entities_extracted = len(nodes)  ← 数量统计正确
relations_created = len(edges)   ← 数量统计正确
```

### 变更详情

| 环节 | 文件 | 变更内容 |
|---|---|---|
| 环境变量 | `.env.example` | 新增 `GRAPHITI_DRY_RUN=false` 及注释 |
| 配置加载 | `main.py:load_config()` | 新增 `graphiti.dry_run` 配置项，解析 `1`/`true`/`yes` 为 True |
| 图谱构建 | `main.py:simulate_graph_build()` | 读取 `dry_run` 配置，打印提示信息，传递给 `add_event_to_graph()` |
| 写入逻辑 | `graphiti/graphiti_workflow.py:add_event_to_graph()` | 新增 `dry_run` 参数；monkey-patch `_process_episode_data` 为空操作；`try/finally` 确保恢复原始方法 |

### 涉及的文件

| 文件 | 变更行数 | 变更类型 |
|---|---|---|
| `.env.example` | +2 | 新增：环境变量配置 |
| `main.py` | +12 | 修改：配置加载 + dry_run 提示 + 参数传递 |
| `graphiti/graphiti_workflow.py` | +27 / -14 | 修改：dry_run 参数 + monkey-patch 逻辑 |

### 不修改的范围

- `graphiti_core/` — 第三方库，未修改
- `consumer.py` — RabbitMQ 消费者，未改动
- Stage 5–7（风险评估、搜索、Dashboard）— 流程不变
- Neo4j 连接初始化 — dry_run 模式下仍需连接（Graphiti 初始化依赖）

## 实现细节

### monkey-patch 机制

```python
_original_process: Any = None
if dry_run:
    _original_process = graphiti._process_episode_data

    async def _noop_process(...) -> tuple[list, Any]:
        episodes = episode if isinstance(episode, list) else [episode]
        for ep in episodes:
            ep.entity_edges = [e.uuid for e in entity_edges]
        return [], episodes[0]

    graphiti._process_episode_data = _noop_process

try:
    result = await graphiti.add_episode(...)
finally:
    if dry_run and _original_process is not None:
        graphiti._process_episode_data = _original_process
```

### 为什么不跳过 Graphiti 初始化

`graphiti.add_episode()` 内部流程中，LLM 提取（`extract_nodes`、`_extract_and_resolve_edges`、`extract_attributes_from_nodes`）在 `_process_episode_data` 调用**之前**执行。跳过初始化会导致 LLM 提取也无法执行，违背"保留提取结果"的设计目标。

### 并发安全

每次 `simulate_graph_build` 创建新的 `graphiti` 实例，不存在多个协程共享同一实例的情况。`try/finally` 确保即使异常也能恢复原始方法，是防御性编程。

## 配置说明

```env
# 调试模式：设为 true 跳过 Neo4j 写入（LLM 提取仍会执行）
GRAPHITI_DRY_RUN=false
```

支持的值：`1`、`true`、`yes`（不区分大小写），其他值视为 `false`。

## 影响范围

- **Stage 3（图谱构建）**：`simulate_graph_build()` 在 dry_run 模式下跳过 DB 写入，日志显示"提取完成（dry run，未写入数据库）"及提取数量
- **向后兼容**：默认 `false`，不影响现有流程
- **API 兼容**：`add_event_to_graph()` 新增可选参数 `dry_run: bool = False`，调用方无需修改
