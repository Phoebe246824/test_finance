# 黑名单 / Milvus / Neo4j 构图流程重构报告

## 背景

本次调整围绕 blacklist demo 回放、Milvus 暂存回捞、Neo4j 构图去重和二次风险评估路由展开。原流程在以下场景存在问题：

- Milvus 写入后测试脚本立刻查询，可能因未 flush 导致断言看不到新记录。
- Neo4j 已存在同文本 Episode 时，重复运行 demo 仍可能触发重复构图或断言误判。
- Milvus 回捞候选直接进入批量构图，语义粗召回噪声可能导致不相关事件入图。
- CrewAI/LLM 偶尔返回 Markdown fenced JSON，直接 `json.loads()` 会导致风险评估解析失败。
- Stage 6 无回捞事件时仍可能继续二次检索/二次评估，流程和预期不一致。
- 自动回放日志缺少按 case 归档，排查链路较长。

## 主要变更

### 1. LLM JSON 解析增强

新增通用解析函数，支持：

- 纯 JSON 对象
- ```json fenced Markdown 输出
- 前后带解释文本的 JSON 对象

应用位置包括：

- 事件分类结果解析
- 首次风险评估解析
- 二次风险评估解析
- 事件标准化解析

这避免了 LLM 返回 Markdown 代码块时出现“风险评估结果解析失败”。

### 2. Milvus 暂存写入可见性修复

在 Milvus 暂存写入和 `is_graph_built` 更新后执行 collection flush，确保 demo 回放脚本可以在写入后立即查询到状态。

### 3. Neo4j 构图去重

当前事件单条构图前增加 Neo4j Episode 内容检查：

- 已存在同 `content` / `raw_content`：跳过单条构图，避免重复写 Neo4j。
- 不存在：正常调用 Graphiti 构图。

Milvus 回捞后的批量构图也增加同文本检查：

- 已存在 Neo4j 的候选不会重复构图。
- 对应 Milvus 记录标记为 `is_graph_built=True`，避免后续重复回捞。

### 4. Milvus 回捞候选 rerank 精过滤

Milvus 回捞结果现在先作为候选集，不再默认全部批量构图。

准入规则：

1. 与当前事件共享人员 ID 的历史事件直接通过。
2. 非共享人员 ID 的候选需要调用 reranker，并满足 `STASH_RERANK_MIN_SCORE` 阈值。
3. 未通过 rerank 的候选跳过构图，但不标记 `is_graph_built=True`，保留为未来可能相关事件使用。

新增配置：

- `STASH_RERANK_ENABLED`：是否启用回捞候选 rerank 过滤，默认启用。
- `STASH_RERANK_MIN_SCORE`：非同人候选进入批量构图的 rerank 最低分，默认 `0.7`。

### 5. Stage 6 / Stage 7 路由调整

首次风险评估超阈值后进入 Stage 6。

- 若 Stage 6 `batched_count == 0`：没有新增候选真正写入 Neo4j，跳过二次检索和二次风险评估，保留首次风险评估结果，直接进入 Stage 8 Dashboard。
- 若 Stage 6 `batched_count > 0`：继续 Stage 7 二次检索和二次风险评估。

该行为符合“只有新增补图后才需要二次检索/评估”的预期。

### 6. 自动回放脚本增强

`run_blacklist_kv_demo.py` 增强：

- 保留 Neo4j 既有图谱，只重置 Redis 黑名单和 Milvus 暂存。
- 记录每条 case 执行前 Neo4j baseline，用于判断是否新增重复构图，而非要求 Neo4j 必须为空。
- 总览日志写入 `logs/blacklist_kv_demo_*.log`。
- 每条测试文本单独写入 `logs/blacklist_kv_demo_cases_*/`。
- 子进程输出、输入文本、断言快照、PASS/FAIL 结果都进入日志。

## 数据保留策略

Milvus 记录不物理删除，而是使用 `is_graph_built` 标记：

- 成功构图：标记 `True`。
- Neo4j 已存在并跳过重复构图：标记 `True`。
- rerank 判定不相关：不标记，继续保留为未构图候选。

这样既避免重复回捞，又保留审计和未来复用能力。

## 风险与注意事项

- reranker 未配置时，非共享人员 ID 的 Milvus 候选默认不会进入批量构图。
- `STASH_RERANK_MIN_SCORE` 需要根据实际 reranker 模型分布调参。
- 若 Neo4j 历史库中已有旧数据，demo 断言依赖 baseline 判断“是否新增重复构图”，不再等价于干净库测试。

## 验证建议

1. 运行语法检查：

```bash
uv run python -m py_compile main.py scripts/run_blacklist_kv_demo.py
```

2. 运行 demo 回放：

```bash
uv run python scripts/run_blacklist_kv_demo.py
```

3. 重点检查日志：

- 是否出现 `Milvus 暂存回捞为空，跳过二次检索和二次风险评估`
- 是否出现 `未通过 rerank 过滤，跳过批量构图`
- 是否出现 `已存在 Neo4j，跳过重复批量构图`
- Milvus 中已构图或已存在 Neo4j 的记录是否被标记为 `is_graph_built=True`
