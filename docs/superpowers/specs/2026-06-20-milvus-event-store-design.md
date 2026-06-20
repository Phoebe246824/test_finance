# 设计：事件读取链路迁移到 Milvus 单一真相源

- 日期：2026-06-20
- 状态：已完成设计讨论，待用户审阅
- 范围：`/api/events`、事件详情、Dashboard 事件总览、人工复核记录、Web 分析结果落库、Milvus 事件模型

## 1. 背景与目标

当前 Web 事件链路存在两套账：

1. `process_message_detailed()` 和黑名单暂存流程把事件写入 Milvus。
2. `backend/app/repositories/events.py` 又把分析结果写入 SQLite `financial_events`。
3. `/api/events`、`/api/events/{event_id}`、`/api/dashboard/overview`、`/api/graph/events/{event_id}` 等读取逻辑依赖 SQLite。

这导致系统行为与当前业务语义不一致：

- `scripts/reset_and_seed_blacklist.py` 会 drop Milvus collection，但不会清空 SQLite 事件表。
- 页面上的事件列表、详情和总览不会随 Milvus reset 一起重置。
- `is_graph_built=True` 的历史事件仍应继续出现在事件库中，但当前 Web 读取链路看不到这层真实状态。

本次改造目标是把 Milvus 明确为“全部事件”的唯一真相源，而不再只是“暂存池”：

1. 所有事件列表与详情 API 均直接从 Milvus 读取。
2. `review_actions` 迁移到 Milvus，并作为事件记录中的数组字段保存。
3. Web 分析结果不再写 SQLite 事件表，而是回写同一条 Milvus 事件记录。
4. reset/seed 脚本 drop Milvus collection 后，`/api/events` 等页面数据可随之完整重置。
5. `is_graph_built` 仅表示“是否已参与构图/回捞”，不表示事件是否应从事件库消失。

## 2. 已确认的关键决策

以下决策已经在设计讨论中确认：

1. **Milvus 表示全部事件，不只是暂存事件。**
   - 事件回捞后只把 `is_graph_built` 置为 `true`，不从事件库删除。
2. **`/api/events` 迁移为只读事件列表。**
   - 事件删除能力不再保留。
3. **所有仍依赖 SQLite 事件表的读取逻辑都要改。**
   - 不只是列表，还包含详情、Dashboard、图谱 fallback 所需事件读取。
4. **`review_actions` 迁移到 Milvus。**
   - 采用内嵌数组字段：`review_actions: list[dict]`。
5. **本期不保留 SQLite 事件表作为并行镜像。**
   - SQLite 可以继续承载黑名单 UI 元数据等无关表，但不再作为事件真相源。

## 3. 方案对比

### 方案 A：Milvus 单一事件记录模型（推荐）

- 每个 `event_id` 对应一条 Milvus 记录。
- 原有暂存字段、分析结果字段、复核历史字段都放进同一条记录。
- `POST /api/events/{event_id}/review-actions` 通过“读事件 -> 追加数组 -> upsert 事件”完成。

优点：

- reset/seed 与 Web 读取天然一致。
- 只有一个事件真相源，模型最直观。
- CLI 与 Web 可以复用同一套事件持久化逻辑。

代价：

- 需要扩展当前 `MilvusStashStore` 的 schema/字段管理能力。
- 事件更新从“局部 SQL update”变成“整条记录 read-modify-upsert”。

### 方案 B：Milvus 事件 + 单独 Milvus review collection

- 事件记录保存在主 collection。
- `review_actions` 放到第二个 collection，通过 `event_id` 关联。

优点：

- 复核记录 append-only，更贴近关系表习惯。
- 单次复核更新不必重写整条事件记录。

代价：

- 又回到“两套事件相关数据”的形态。
- Dashboard 和详情页要跨 collection 拼装。
- 与本次“统一事件真相源”的目标不完全一致。

### 方案 C：保留 SQLite 影子事件表，仅把 `/api/events` 改读 Milvus

优点：

- 改动最少。

代价：

- reset/seed 问题仍会残留。
- 详情页、Dashboard、review actions 仍会分裂。
- 长期维护成本最高。

**结论：采用方案 A。**

## 4. 目标架构

改造后事件读写链路如下：

```text
文本输入
  -> process_message_detailed()
  -> 产出标准化 + 黑名单 + 风险评估 + 趋势报告
  -> EventArchiveStore.upsert_event_snapshot(...)
  -> Milvus event collection

FastAPI
  -> /api/events                 -> Milvus 查询
  -> /api/events/{event_id}      -> Milvus 单条查询
  -> /api/events/{event_id}/review-actions
                                -> Milvus 单条读取 + 追加 review_actions + upsert
  -> /api/dashboard/overview     -> Milvus 聚合统计
  -> /api/graph/events/{event_id}
                                -> 先取 Milvus 事件，再走 Neo4j / fallback
```

SQLite 退到非事件主链路：

- `blacklist_items` 仍可暂留，继续服务前端黑名单管理页面。
- `financial_events`、`review_actions` 不再参与业务读写。
- `analysis_tasks` 维持保留状态，不在本次范围内扩展。

## 5. Milvus 事件记录模型

### 5.1 记录定位

- collection：沿用当前 `MILVUS_STASH_COLLECTION`，但语义升级为“事件档案 collection”。
- 主键：`event_id`
- 向量字段：`embedding`

### 5.2 必备字段

在当前 `MilvusStashStore` 基础上扩展出完整事件模型。目标字段如下：

```text
event_id: str
title: str
raw_content: str
content_hash: str
source: str
status: str                  # stashed / analyzed
event_type: str
summary: str
risk_level: str | null
risk_score: float | null
reasoning: str
blacklist_decision: str      # STASH / PASS
matched_persons: list[str]
matched_keywords: list[str]
event_similarity: dict
dimension_scores: dict
trend_report: dict
graph_result: dict | null
second_risk_applied: bool
person_ids: list[str]
review_actions: list[dict]
created_at: str
updated_at: str
expire_at: str
is_graph_built: bool
embedding: vector
```

### 5.3 `review_actions` 结构

`review_actions` 内嵌数组中的每一项结构统一为：

```json
{
  "id": "uuid-or-ulid",
  "action_type": "suggest_freeze",
  "comment": "可选备注",
  "created_at": "2026-06-20T12:34:56"
}
```

说明：

- `id` 保留为前端列表 key，避免只靠时间戳。
- 顺序约定为倒序返回，最新记录在前。
- 本期不单独维护“最后复核状态字段”；Dashboard 若需要，可从 `review_actions[0]` 推导最新状态。

### 5.4 关于 `expire_at`

当前 `MilvusStashStore` 带有 TTL/过期语义。既然 collection 升级为“全部事件档案”，本期明确修改语义：

1. `expire_at` 字段暂时保留，避免破坏现有回捞过滤逻辑。
2. 但 **Web 事件列表和详情不能因为 `expire_at` 到期而隐藏事件**。
3. `cleanup_expired()` 不再允许作为默认事件清理策略接入主链路。
4. 若未来确实需要归档/清理，应新增显式归档策略，而不是复用“暂存 TTL”语义。

## 6. 组件设计

### 6.1 新的 Milvus 事件存储抽象

推荐把当前 `MilvusStashStore` 收敛/升级为一个更清晰的事件档案接口，例如：

```text
MilvusEventStore
  - upsert_stashed_event(...)
  - upsert_analyzed_event(...)
  - list_events(...)
  - get_event(...)
  - append_review_action(...)
  - mark_events_graph_built(...)
  - fetch_related_events(...)
```

设计原则：

1. 统一承接“事件档案读写”和“历史回捞”。
2. 对外暴露的是事件领域对象，不是“Milvus query row”。
3. 现有 `stash_event()` 和 `fetch_related_events()` 能力保留，但名称和职责要与“全部事件”语义一致。

### 6.2 API 层改动

#### `/api/events`

- `GET /api/events`
  - 改为从 Milvus 拉取列表。
  - 保留分页、`risk_level`、`keyword` 参数。
  - `keyword` 本期支持对 `raw_content` / `title` / `summary` 的应用层过滤。
- `GET /api/events/{event_id}`
  - 改为从 Milvus 读取单条事件。
  - 返回值中直接包含 `review_actions`。
- `DELETE /api/events/{event_id}`
  - 移除。
- `POST /api/events/{event_id}/review-actions`
  - 保留。
  - 实现改为 Milvus 读-改-写。

#### `/api/dashboard/overview`

- 不再读 SQLite `financial_events` 和 `review_actions`。
- 改为从 Milvus 读取事件集合并在应用层聚合：
  - 总事件数
  - 今日事件数
  - 近 7 日事件数
  - 风险分布
  - 事件类型分布
  - 高频命中关键词
  - `pending_review`
  - `recent_events`
  - `recent_reviews`

#### `/api/graph/events/{event_id}`

- `EventRepository().get_event(event_id)` 改为 Milvus 事件读取。
- 这样 Neo4j fallback 图和事件详情共享同一份事件内容。

### 6.3 Web 分析结果持久化

当前 `AnalysisService.analyze()` 在 `process_message_detailed()` 返回后又执行一次 SQLite `upsert_from_analysis(result)`。

本期改为：

1. `process_message_detailed()` 在流程出口统一调用 Milvus 事件 snapshot upsert。
2. `AnalysisService` 不再把结果写入 SQLite。
3. CLI 和 Web 共用完全相同的事件持久化逻辑。

这意味着事件持久化应尽量靠近 `process_message_detailed()` 的两个退出口：

- `status=stashed`
- `status=analyzed`

这样任何调用方只要复用该函数，就不会出现“分析结果没入事件库”的分叉。

## 7. 数据流细节

### 7.1 STASH 分支

当事件未命中黑名单、进入 Milvus 时：

1. 若内容去重命中，沿用当前“跳过重复暂存”策略。
2. 若新写入，则立刻创建一条完整事件记录，至少包含：
   - 基础文本信息
   - `status=stashed`
   - `blacklist_decision=STASH`
   - 空的 `review_actions`
   - `is_graph_built=false`
3. `created_at` 取首次写入时间，`updated_at` 与其一致。

### 7.2 PASS / analyzed 分支

当事件完成分析流程：

1. 以同一个 `event_id` 为主键写回完整分析快照。
2. 若该事件此前已存在于 Milvus，则执行 upsert 覆盖：
   - 风险等级/分数
   - 维度评分
   - 趋势报告
   - 图谱结果摘要
   - `status=analyzed`
   - `blacklist_decision=PASS`
   - `updated_at`
3. `review_actions` 必须被原样保留，不能在分析结果回写时丢失。

### 7.3 复核分支

当调用 `POST /api/events/{event_id}/review-actions`：

1. 先读取事件。
2. 将新的 action 追加到 `review_actions`。
3. 对数组按 `created_at DESC` 排序，或在返回前倒序。
4. upsert 整条事件。
5. 同步更新 `updated_at`。

## 8. 查询、过滤与分页策略

Milvus 不是关系型业务库，本期采用保守策略，避免过度依赖其全文检索能力。

### 8.1 列表查询

实现建议：

1. 先用 Milvus query 拉取候选事件行。
2. 在 Python 应用层完成：
   - `risk_level` 过滤
   - `keyword` 模糊匹配
   - `updated_at DESC` 排序
   - 分页切片

这样做的原因：

- 与现有前端需求匹配；
- 不依赖 Milvus 的复杂文本过滤能力；
- 更容易兼容 JSON / 数组字段。

### 8.2 Dashboard 聚合

Dashboard 统计量同样在应用层计算，而不是试图让 Milvus 承担复杂聚合 SQL 的角色。

本期接受的代价：

- 数据量较大时，`/api/events` 和 `/api/dashboard/overview` 会比 SQLite 更重。

本期不做：

- 独立 OLAP 统计层
- 额外缓存
- 专门的 dashboard summary collection

如果后续事件量上升，再考虑补充缓存层或派生统计表。

## 9. 兼容与迁移策略

### 9.1 SQLite 退场范围

本期不再使用：

- `financial_events`
- `review_actions`

本期继续保留：

- `blacklist_items`
- `analysis_tasks`

`init_db()` 可暂时保留这些表的创建逻辑，直到实现稳定后再做收尾清理。这样能降低一次性改动风险。

### 9.2 历史数据

本期默认把 SQLite 现存事件视为旧版演示遗留数据，不自动回填。

如果需要保留历史，可后续补一个一次性迁移脚本：

```text
SQLite financial_events + review_actions
  -> merge by event_id
  -> Milvus upsert
```

但这不属于本次第一阶段必做项。

## 10. 前端影响

### 10.1 事件列表

- 去掉删除按钮。
- API client 删除 `deleteEvent()`。
- 文案保持“只读事件库”语义。

### 10.2 事件详情

- `event.review_actions` 继续存在，前端无需改交互模型。
- `ReviewActionPanel` 继续走原接口。

### 10.3 Dashboard

- 数据结构尽量保持原样，减少前端页面变更。

## 11. 错误处理

### 11.1 Milvus collection 不存在

- 对 `GET /api/events` 返回空列表而不是 500。
- 对 `GET /api/events/{event_id}` 返回 404。
- 对 dashboard 返回 0 统计项。

### 11.2 事件读取后复核写回冲突

由于 `review_actions` 采用整条记录 upsert，本期接受“最后一次写入覆盖”的简化并发模型。

前提：

- 当前系统使用场景以单人演示和低并发为主。

若未来需要多人同时复核，再考虑：

- 乐观锁版本号
- review append-only 独立 collection

### 11.3 旧事件字段缺失

对历史 Milvus 记录允许字段缺省，API 层做兜底：

- 缺 `review_actions` -> `[]`
- 缺 `dimension_scores` -> `{}`
- 缺 `trend_report` -> `{}`
- 缺 `matched_persons` / `matched_keywords` -> `[]`

## 12. 测试设计

### 12.1 单元测试

1. 事件 snapshot upsert：
   - 新事件写入
   - 已有事件覆盖更新
   - 更新时保留既有 `review_actions`
2. `append_review_action()`：
   - 能向空数组追加
   - 能保留历史并倒序返回
3. `list_events()`：
   - `risk_level` 过滤
   - `keyword` 过滤
   - `updated_at` 排序
   - 分页切片
4. `get_event()`：
   - 字段缺失兜底
5. Dashboard 聚合：
   - `pending_review`
   - `recent_reviews`
   - 风险桶统计

### 12.2 API 测试

1. `GET /api/events`
2. `GET /api/events/{event_id}`
3. `POST /api/events/{event_id}/review-actions`
4. `GET /api/dashboard/overview`
5. `GET /api/graph/events/{event_id}`

重点验证：

- reset/seed drop collection 后，`/api/events` 为空。
- 新分析事件写入后，`/api/events` 立即可见。
- 历史事件被标记 `is_graph_built=true` 后，仍出现在列表和详情中。

## 13. 实施边界

本期应完成：

1. Milvus 事件记录模型扩展。
2. 事件读取 API 全面迁移。
3. `review_actions` 迁移到 Milvus 内嵌数组。
4. Web 分析结果持久化迁移到 Milvus。
5. 前端删除按钮下线。

本期不做：

1. 黑名单 UI 元数据从 SQLite 再迁走。
2. 独立历史数据回填脚本。
3. 大规模事件集的专门优化。
4. 多人并发复核冲突控制。

## 14. 验收标准

满足以下条件视为迁移完成：

1. `scripts/reset_and_seed_blacklist.py` 执行后，`/api/events` 与 Dashboard 事件视图被完整重置。
2. 任意新分析事件都只写入 Milvus，不再依赖 SQLite `financial_events`。
3. `GET /api/events`、`GET /api/events/{event_id}`、`GET /api/dashboard/overview`、`GET /api/graph/events/{event_id}` 均不再读取 SQLite 事件表。
4. 在事件详情页新增复核动作后，刷新页面仍能看到完整 `review_actions` 历史。
5. `is_graph_built=true` 的事件仍保留在事件列表中。
