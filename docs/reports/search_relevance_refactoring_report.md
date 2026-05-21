# 搜索结果相关性阈值 — 重构报告

## 问题描述

当输入事件与知识图谱中已有数据**完全不相关**时，`simulate_search()` 仍硬返回 `num_results` 条上下文。

**复现场景：** 图中仅含「逃犯事件」数据，输入「情感纠纷」，检索结果仍为逃犯相关上下文。下游的意图分析、趋势预测、二次风险评估均被无关信息污染。

## 根因分析

1. **无分数截断机制**：`hybrid_search()` 始终取 cross-encoder 重排序后的 top-K 结果返回，不检查最低分数
2. **固定结果数**：`num_results` 为固定值（默认 10 / 20），即使所有候选分数极低也强制补足
3. **无实体保护**：当新事件不含已知实体 ID 时，`filter_search_result_by_subject_episodes()` 直接放行全部结果

## 解决方案

在 cross-encoder 重排序后添加 **相关性分数阈值过滤**，低于阈值的结果直接丢弃。阈值通过环境变量配置，默认关闭（`0.0`），用户按需开启。

### 数据流（变更后）

```
simulate_search()
  ├─ hybrid_search(query, num_results, min_score)
  │   ├─ graphiti.search_()                → BM25 + 向量 + BFS，取 candidate_limit 个候选
  │   ├─ _global_merge_rerank_top_k()      → cross-encoder 全局重排序，取 top num_results
  │   └─ score 过滤                         → 丢弃 score < min_score 的条目  ← ★
  │   └─ return {"results": filtered_list, ...}
  ├─ get_subject_episode_uuids()           → 实体匹配
  ├─ filter_search_result_by_subject_episodes()
  └─ return result
```

### 变更详情

| 环节 | 文件 | 变更内容 |
|---|---|---|
| Stage 5 混合检索 | `graphiti/graphiti_workflow.py:hybrid_search()` | 新增 `min_score: float = 0.0` 参数；在 `_global_merge_rerank_top_k()` 返回后增加分数过滤逻辑；过滤时打印丢弃数量 |
| Stage 5 配置入口 | `main.py:load_config()` | 新增 `search.min_score` 配置项，读取 `SEARCH_MIN_SCORE` 环境变量 |
| Stage 5 搜索调用 | `main.py:simulate_search()` | 从配置读取 `min_score` 并传入 `hybrid_search()`；打印 min_score 日志 |
| 配置模板 | `.env.example` | 新增 `SEARCH_NUM_RESULTS`、`RISK_SEARCH_NUM_RESULTS`、`SEARCH_MIN_SCORE` 配置项及说明 |
| 方案文档 | `docs/search_relevance_threshold_plan.md` | 新增重构方案文档 |

### 涉及的文件

| 文件 | 变更行数 | 变更类型 |
|---|---|---|
| `graphiti/graphiti_workflow.py` | +9 | `hybrid_search()` 参数 + 过滤逻辑 |
| `main.py` | +10 / -1 | `load_config()` 配置项 + `simulate_search()` 传参 |
| `.env.example` | +7 | 新增搜索配置项 |

### 不修改的范围

- `graphiti_core/` — 第三方库，未修改
- `_global_merge_rerank_top_k()` — 保持通用性，未侵入
- `run_full_pipeline.py` — 无改动，向后兼容
- `filter_search_result_by_subject_episodes()` — 暂未修改（可选，待评估）

## 配置说明

在 `.env` 中设置：

```env
# 搜索结果数量
SEARCH_NUM_RESULTS=10
# 二次风险评估时的搜索结果数量
RISK_SEARCH_NUM_RESULTS=20
# 相关性分数阈值（0.0 = 关闭过滤，建议首次开启设为 0.3）
SEARCH_MIN_SCORE=0.0
```

默认 `SEARCH_MIN_SCORE=0.0` 保持原有行为不变，开启后需根据实际效果调整阈值。

## 影响范围

- **Stage 4（风险评估）**：二次评估的检索走同一个 `hybrid_search()`，同样受 `min_score` 过滤
- **Stage 5（混合检索）**：直接修改点
- **Stage 7（Dashboard）**：依赖搜索上下文，当检索结果为空时意图分析/趋势预测将跳过
- **所有调用方**：`hybrid_search()` 签名兼容（ `min_score` 有默认值 `0.0`）
