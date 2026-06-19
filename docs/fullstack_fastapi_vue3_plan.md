# Sentinel Edge FastAPI + Vue3 开发计划

> 历史规划文档：本文记录 FastAPI + Vue3 改造计划，不保证所有命令仍是最新。当前启动方式以 [README.md](../README.md)、[commands.md](commands.md) 和 [docs/README.md](README.md) 为准。

这份文档按“现在已经做了什么、怎么运行、下一步怎么继续做”的顺序写。目标是把当前 Sentinel 金融风控智能体做成一个可以演示、可以继续扩展的全栈项目。

## 1. 项目目标

做一个金融风控智能体工作台：

1. 在网页输入金融事件文本。
2. 后端调用现有 Sentinel pipeline。
3. 展示黑名单命中、风险等级、风险分数、多维度评分、事件分类、图谱关系。
4. 管理人员黑名单、关键词黑名单、高危事件样本。
5. 查看系统状态和硬件信息。

## 2. 当前已实现的 MVP

后端已经新增：

```text
backend/app/main.py
backend/app/api/routes_analysis.py
backend/app/api/routes_events.py
backend/app/api/routes_blacklist.py
backend/app/api/routes_graph.py
backend/app/api/routes_system.py
backend/app/db/session.py
backend/app/repositories/events.py
backend/app/services/analysis_service.py
backend/app/schemas/analysis.py
```

前端已经新增：

```text
frontend/src/App.vue
frontend/src/styles.css
frontend/src/api/
frontend/src/router/
frontend/src/views/AnalyzeView.vue
frontend/src/views/DashboardView.vue
frontend/src/views/EventsView.vue
frontend/src/views/EventDetailView.vue
frontend/src/views/BlacklistView.vue
frontend/src/views/PersonGraphView.vue
frontend/src/views/SystemStatusView.vue
frontend/src/components/RiskBadge.vue
frontend/src/components/BlacklistHitPanel.vue
frontend/src/components/DimensionScoreBars.vue
frontend/src/components/GraphViewer.vue
frontend/src/components/ReviewActionPanel.vue
frontend/src/components/TrendReportPanel.vue
```

现在已经能做这些事：

1. `POST /api/analyze`：输入事件文本，调用现有 pipeline 分析。
2. 分析结果写入 SQLite。
3. `/dashboard`：风控总览、风险分布、趋势报告覆盖率、待复核任务。
4. `/analysis`：前端风险分析页面，展示结果、命中详情、事件图谱、趋势预测报告。
5. `/events`：事件列表、搜索、删除。
6. `/events/:eventId`：事件详情、风险分数、命中详情、交互图谱、趋势报告、人工复核。
7. `/graph/person`：按客户/人员搜索 Neo4j 图谱，支持节点扩展。
8. `/blacklist`：人员、关键词、高危事件增删查。
9. `/system`：API、Redis、数据库、硬件信息。

## 3. 总体架构

```text
Vue 3 前端
  |
  | HTTP API
  v
FastAPI 后端
  |
  |-- main.py 现有 Sentinel pipeline
  |-- SQLite MVP 数据库
  |-- Redis 黑名单
  |-- Milvus 暂存与相似召回
  |-- Neo4j/Graphiti 图谱构建
  |-- 本地或远程 LLM 风险分析
```

第一版采用同步分析：前端点击“开始分析”，等待后端返回结果。后面再升级为异步任务。

## 4. 启动方式

后端：

```bash
cd /Users/phoebe/project/test_finance
uv run uvicorn backend.app.main:app --reload --port 8000
```

前端：

```bash
cd /Users/phoebe/project/test_finance/frontend
npm install
npm run dev
```

浏览器打开：

```text
http://localhost:5173
```

前端默认访问：

```text
http://127.0.0.1:8000
```

如果后端地址变了，在 `frontend/.env.development` 写：

```text
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## 5. 当前数据库设计

MVP 先用 SQLite：

```text
data/sentinel_edge.db
```

### 5.1 financial_events

用于前端事件列表和详情。

```text
id
event_id
title
raw_content
source
event_type
summary
status
risk_level
risk_score
reasoning
blacklist_decision
matched_persons_json
matched_keywords_json
event_similarity_json
dimension_scores_json
created_at
updated_at
```

### 5.2 blacklist_items

用于前端黑名单管理页面，同时 Redis 仍然负责实际快速匹配。

```text
id
item_type          # person / keyword / event
value
summary
description
enabled
created_at
updated_at
```

### 5.3 analysis_tasks

为后续异步任务预留，现在暂时不用。

```text
id
task_id
event_id
status
error_message
started_at
finished_at
```

## 6. 当前 API

### 6.1 分析

```text
POST /api/analyze
```

请求：

```json
{
  "text": "2026年6月14日，【P102# 客户B】..."
}
```

返回重点字段：

```json
{
  "event_id": "uuid",
  "status": "analyzed",
  "risk_level": "high",
  "risk_score": 0.795,
  "event_type": "反洗钱风险",
  "summary": "客户疑似分拆转账并向虚拟币商户归集资金",
  "dimension_scores": {
    "transaction_behavior": {
      "score": 0.9,
      "weight": 0.25,
      "weighted_score": 0.225
    }
  },
  "trend_report": {
    "category_name": "金融",
    "severity_name": "高",
    "report": "趋势预测报告正文..."
  },
  "blacklist": {
    "decision": "PASS",
    "matched_persons": ["P102"],
    "matched_keywords": ["虚拟币"],
    "event_similarity": {
      "hit": true,
      "score": 0.91
    }
  },
  "second_risk_applied": false
}
```

### 6.2 事件

```text
GET    /api/events
GET    /api/events/{event_id}
DELETE /api/events/{event_id}
POST   /api/events/{event_id}/review-actions
```

列表支持：

```text
page
page_size
risk_level
keyword
```

复核动作请求：

```json
{
  "action_type": "suggest_freeze",
  "comment": "建议先冻结后续出金并人工核验客户身份"
}
```

### 6.3 黑名单

```text
GET    /api/blacklist/persons
POST   /api/blacklist/persons
DELETE /api/blacklist/persons/{value}

GET    /api/blacklist/keywords
POST   /api/blacklist/keywords
DELETE /api/blacklist/keywords/{value}

GET    /api/blacklist/events
POST   /api/blacklist/events
DELETE /api/blacklist/events/{value}
```

新增请求：

```json
{
  "value": "P102",
  "summary": "高风险客户",
  "description": "历史存在虚拟币平台资金归集"
}
```

### 6.4 图谱

```text
GET /api/graph/events/{event_id}
```

当前图谱接口优先查询 Neo4j/Graphiti 中的真实节点和关系，返回 1-2 跳子图；Neo4j 不可用或查不到时，才从事件原文中抽取形如 `【P102# 客户B】`、`【A601# 账户】`、`【M301# 商户】` 的实体作为兜底图。

返回：

```json
{
  "nodes": [
    {"id": "event-id", "label": "事件标题", "type": "event"},
    {"id": "P102", "label": "客户B", "type": "customer"}
  ],
  "edges": [
    {"source": "P102", "target": "event-id", "label": "出现在事件中"}
  ]
}
```

人物图谱与节点扩展：

```text
GET /api/graph/persons?q=P102
GET /api/graph/nodes/{node_id}/expand
```

### 6.5 总览

```text
GET /api/dashboard/overview
```

返回：

```json
{
  "metrics": {
    "total_events": 10,
    "high_risk_events": 3,
    "pending_review": 2,
    "trend_report_coverage": 0.6
  },
  "risk_distribution": {
    "high": 3,
    "medium": 2,
    "low": 5
  },
  "recent_events": []
}
```

### 6.6 系统

```text
GET /api/system/health
GET /api/system/hardware
```

## 7. 前端页面设计

### 7.1 风险分析页 `/analysis`

负责：

1. 输入金融事件文本。
2. 调用 `POST /api/analyze`。
3. 展示风险等级、风险分数、状态、摘要。
4. 展示黑名单命中详情。

后续可加：

1. 示例 case 下拉选择。
2. 分析耗时。
3. 日志流式输出。

### 7.2 事件库 `/events`

负责：

1. 展示事件列表。
2. 按关键词和风险等级筛选。
3. 删除事件。
4. 点击进入详情页。

后续可加：

1. 时间范围筛选。
2. 批量删除。
3. 导出报告。

### 7.3 事件详情 `/events/:eventId`

负责：

1. 展示风险等级、风险分数、事件类型。
2. 展示原文和评估说明。
3. 展示黑名单命中。
4. 展示关系图谱。
5. 展示多维度评分条。

后续可加：

1. 关联历史事件表格。
2. 意图识别结果。
3. 趋势预测结果。
4. 人工复核按钮。

### 7.4 黑名单 `/blacklist`

负责：

1. 人员黑名单增删查。
2. 关键词黑名单增删查。
3. 高危事件样本增删查。

后续可加：

1. 启用/停用开关。
2. 批量导入。
3. 操作审计日志。

### 7.5 系统状态 `/system`

负责：

1. 展示 API 是否正常。
2. 展示 Redis 是否正常。
3. 展示数据库是否存在。
4. 展示硬件信息。

后续可加：

1. Milvus 状态。
2. Neo4j 状态。
3. LLM 状态。
4. 最近 10 次分析耗时。

## 8. 下一阶段开发顺序

### 第一步：把 MVP 跑稳定

1. 启动 Redis、Milvus、Neo4j。
2. 启动 FastAPI。
3. 启动 Vue3。
4. 在 `/analysis` 输入一个真实金融 case。
5. 看 `/events` 是否出现记录。
6. 看 `/events/:eventId` 是否有图谱和风险分数。

### 第二步：补异步任务

现在分析接口可能等待很久。后面改成：

```text
POST /api/tasks/analyze      创建任务
GET  /api/tasks/{task_id}    查询任务状态
```

前端点击分析后显示：

```text
排队中 -> 分析中 -> 完成 / 失败
```

### 第三步：补人工复核

新增表：

```text
review_records
```

字段：

```text
id
event_id
review_status       # pending / approved / rejected / frozen
reviewer
comment
created_at
updated_at
```

前端在详情页加按钮：

```text
标记已复核
标记误报
建议冻结
```

### 第四步：图谱升级

当前 `GraphViewer.vue` 是轻量 SVG，优点是稳定、依赖少。

后续如果要做更强交互，升级为 AntV G6：

1. 拖拽节点。
2. 缩放画布。
3. 点击节点打开详情抽屉。
4. 一跳/两跳关系切换。
5. 按客户、账户、商户搜索。

### 第五步：数据库升级到 PostgreSQL

SQLite 适合比赛 Demo 和本地开发。正式一点建议换 PostgreSQL：

```text
DATABASE_URL=postgresql+psycopg://sentinel:password@localhost:5432/sentinel_edge
```

同时引入：

```text
SQLAlchemy
Alembic
```

这样后续改表不会混乱。

### 第六步：比赛展示增强

为了比赛演示，建议做：

1. 首页实时大屏：今日高风险事件数、平均风险分、黑名单命中数。
2. 事件详情报告导出：JSON 或 PDF。
3. Demo case 一键运行。
4. 端侧硬件页：CPU/GPU/NPU/内存/推理耗时。
5. 视频脚本和 PPT 截图素材。

## 9. 你后面开发时的简单规则

每次只做一小步：

1. 先加后端接口。
2. 用浏览器或 `curl` 测接口。
3. 再做前端页面。
4. 页面能跑后再美化。
5. 最后补文档。

不要一上来同时改数据库、后端、前端、样式和 pipeline。这样最容易乱。
