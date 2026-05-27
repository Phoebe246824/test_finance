# SentinelPipelineFlow 阶段重构 — 报告

## 问题描述

旧流程虽然已经修复了“高风险事件重复构图”的直接问题，但仍存在三个明显缺陷：

1. Stage 语义不清：构图、检索、风险评估的关系在代码结构上不够直观。
2. 路由规则不一致：低于或等于阈值的事件仍可能进入 Dashboard，和当前业务预期不一致。
3. 暂存存储职责混杂：黑名单和事件暂存都依赖 Redis，不利于语义召回与后续扩展。

业务要求是：

- 事件暂存从 Redis 迁移到 Milvus（支持向量语义召回）；
- 先构图，再基于图上下文做风险评估；
- 仅首次超阈值才走 Milvus 回捞与批量补图；
- 仅二次评估仍超阈值才进入 Dashboard；
- `score <= threshold` 直接结束流程。

## 根因分析

1. 首次/二次风险评估对应的上下文来源在流程表达上耦合，阶段边界不清晰。
2. 高风险分支中的“当前事件 vs 历史暂存事件”边界不清，容易引入重复构图。
3. 事件暂存如果仅按 Redis KV 组织，难以兼顾同人召回与语义召回。
4. 文档与代码执行路径曾出现漂移，导致理解成本上升。

## 解决方案

将“事件暂存迁移 + Flow 阶段重排”作为一次完整重构落地：

1. 事件暂存由 Redis 迁移至 Milvus，黑名单仍保留在 Redis。
2. 主流程重排为显式阶段链路。
3. 两段阈值路由规则固化在 `main.py`。

### 新流程（核心）

```
classification
  -> single_graph_build
  -> search_first_risk_context
  -> first_risk_evaluation
  -> route_post_first_risk
       ├─ score <= threshold -> complete
       └─ score > threshold  -> batch_graph_build_from_stash
                                -> search_second_risk_context
                                -> second_risk_evaluation_stage
                                -> route_post_second_risk
                                     ├─ score <= threshold -> complete
                                     └─ score > threshold  -> go_dashboard -> dashboard -> complete
```

### 关键策略

1. **暂存迁移**：未命中黑名单事件写入 Milvus collection（默认 `stashed_events`），而非 Redis KV。
2. **召回增强**：高风险批量补图前，从 Milvus 同时执行人员 ID 召回与语义召回并合并去重。
3. **防重复构图**：当前事件在 `single_graph_build` 成功后立即标记为已构图，防止被后续回捞再次带入。
4. **批量边界**：批量补图 helper 仅处理历史暂存事件，不把当前事件重复加入批次。
5. **阈值分流**：二次评估后仅在超阈值时进入 Dashboard；否则直接结束。
6. **上下文复用**：Dashboard 优先复用二次上下文，避免重复检索。

## 变更详情

| 环节 | 文件 | 变更内容 |
|---|---|---|
| 暂存存储迁移 | `blacklist/milvus_stash.py` | 新增 `MilvusStashStore`：事件暂存、人员召回、语义召回、过期过滤、已构图标记 |
| 黑名单职责收敛 | `blacklist/store.py` | `BlacklistStore` 仅保留 Redis 黑名单 CRUD，不再承担事件暂存 |
| 入口初始化 | `main.py` | 运行时初始化 `MilvusStashStore.from_config(config)`；PASS/STASH 分支接入 Milvus 暂存 |
| Flow 阶段重排 | `main.py` | 增加并串联 `single_graph_build -> search_first_risk_context -> first_risk_evaluation -> route_post_first_risk -> batch_graph_build_from_stash -> search_second_risk_context -> second_risk_evaluation_stage -> route_post_second_risk -> dashboard` |
| 首次路由规则 | `main.py` | `risk_score > threshold` 才进入 `batch_graph`，否则 `complete` |
| 二次路由规则 | `main.py` | `risk_score > threshold` 才进入 `go_dashboard`，否则 `complete` |
| 批量补图约束 | `main.py` | `batch_graph_event_with_related_stash(...)` 仅批量历史暂存事件，成功后标记已构图 |
| 文档同步 | `README.md` | 系统流程图与数据流说明改为双阈值路由，明确 `score <= threshold` 不进 Dashboard |
| 架构同步 | `docs/architecture.md` | `route_post_first_risk` 描述改为 `complete/batch_graph` |

## 测试与验证

针对 `tests/test_milvus_stash_flow.py` 的覆盖重点：

1. 批量补图成功时仅标记已消费暂存事件。
2. 无暂存事件时不触发批量写图。
3. 批量补图失败时不标记已构图。
4. 低风险路径不进 Dashboard，并且当前事件被标记为已构图。
5. 高风险路径使用二次上下文并在超阈值时进入 Dashboard。
6. 二次评估回落到阈值及以下时结束流程。

验证结果：

- `uv run pytest tests/test_milvus_stash_flow.py -q` 通过
- `uv run pytest -q` 全量通过

与暂存迁移相关的关键验证点：

1. Milvus 回捞结果为空时，批量补图流程跳过。
2. 批量补图成功时仅标记本次消费的历史暂存事件为已构图。
3. 当前触发事件在单条构图后立即标记为已构图，避免回捞重复命中。

## 影响范围

1. **存储层职责**：Redis 聚焦黑名单，Milvus 负责事件暂存与检索召回，职责边界更清晰。
2. **流程控制层**：`SentinelPipelineFlow` 的阶段顺序与路由分支更清晰。
3. **风险分流行为**：`score <= threshold` 不再进入 Dashboard。
4. **图构建行为**：高风险路径避免当前事件重复构图。
5. **检索能力**：暂存回捞从纯 KV 升级为“同人 + 语义”混合召回。
6. **文档一致性**：README 与架构文档与当前代码执行逻辑一致。

## 后续建议

1. 补充依赖真实 Milvus/Neo4j/Graphiti 的端到端回归测试。
2. 增加关键 Stage 指标（耗时、命中数、路由计数）用于可观测性。
