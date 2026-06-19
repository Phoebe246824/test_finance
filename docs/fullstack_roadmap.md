# Sentinel Edge 全栈改造路线图

> 历史规划文档：本文记录全栈改造路线，不保证所有命令仍是最新。当前启动方式以 [README.md](../README.md)、[commands.md](commands.md) 和 [docs/README.md](README.md) 为准。

> 新版、更清晰的 FastAPI + Vue3 开发流程见 [fullstack_fastapi_vue3_plan.md](fullstack_fastapi_vue3_plan.md)。后续建议以新版文档为准。

这份路线图按“先跑通，再变好看，再变稳定”的顺序来。不要一开始就追求大而全，先做一个能演示的闭环。

## 最终要做成什么

一个金融风控 Web 应用：

1. 用户在网页里输入一条交易/客户事件。
2. 后端调用 Sentinel pipeline 分析风险。
3. 页面展示风险等级、风险分数、命中原因、关联历史交易、知识图谱摘要和处置建议。
4. 管理员可以维护金融黑名单关键词、客户黑名单和高危事件样本。
5. 演示时能看到本地模型、Milvus、Neo4j、Redis 和 AMD 硬件画像。

## 第 1 阶段：先让后端稳定跑起来

目标：命令行 Demo 不报错。

需要做：

- 修好 Docker 服务：Redis、Milvus、Neo4j 必须是 `Up` 或 `healthy`。
- 重建 Python 3.13 环境，因为当前 Python 3.14 会让 CrewAI/ChromaDB 导入失败。
- 确认本地 LLM endpoint 可用，例如 Ollama 或 LM Studio 的 OpenAI-compatible API。
- 运行金融种子：

```bash
python scripts/reset_and_seed_blacklist.py
```

- 运行金融 Demo：

```bash
python scripts/sentinel_competition_demo.py --run-pipeline
```

完成标准：能得到一个 `output/competition/sentinel_edge_demo_report.json`，里面有金融用例结果。

## 第 2 阶段：把 pipeline 包成 API

目标：前端不用直接跑脚本，而是请求后端接口。

### 技术栈选择

后端：

- FastAPI：写 HTTP API。
- SQLAlchemy 2.x：操作 SQLite/PostgreSQL。
- Alembic：管理数据库表结构变更。
- Pydantic：定义请求和响应格式。
- Redis：继续存黑名单和缓存。
- Milvus：继续做相似交易召回。
- Neo4j：继续做关系图谱。

前端：

- Vue 3 + Vite：开发页面。
- TypeScript：减少字段名写错。
- Pinia：存登录状态、系统状态、当前分析结果。
- Vue Router：页面路由。
- Element Plus 或 Naive UI：快速做表格、表单、弹窗。
- ECharts：画风险分布、耗时图、维度评分。

推荐目录：

```text
test_finance/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── routes_analysis.py
│   │   │   ├── routes_events.py
│   │   │   ├── routes_blacklist.py
│   │   │   └── routes_system.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   └── security.py
│   │   ├── db/
│   │   │   ├── session.py
│   │   │   └── models.py
│   │   ├── schemas/
│   │   │   ├── analysis.py
│   │   │   ├── events.py
│   │   │   └── blacklist.py
│   │   ├── services/
│   │   │   ├── analysis_service.py
│   │   │   ├── blacklist_service.py
│   │   │   └── system_service.py
│   │   └── main.py
│   └── alembic/
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── views/
│   │   ├── components/
│   │   ├── stores/
│   │   └── router/
│   └── package.json
└── main.py  # 现有 pipeline 先保留，后端 service 调用它
```

### 数据库怎么设计

这个项目不是只用一个数据库，建议按用途分工：

- **PostgreSQL 或 SQLite**：存业务主表，前端列表和详情页主要查这里。开发早期用 SQLite，正式演示或部署用 PostgreSQL。
- **Redis**：继续存黑名单、关键词、短期缓存和任务状态。
- **Milvus**：继续存事件向量和暂存池，用来做相似交易召回。不要把它当普通业务数据库。
- **Neo4j**：继续存客户、账户、商户、设备、交易之间的关系图谱。
- **本地文件或对象存储**：存日志、报告 JSON、PPT、视频素材。

最小业务表建议：

```text
users
- id
- username
- password_hash
- role
- is_active
- created_at
- updated_at

financial_events
- id
- event_id
- title
- raw_content
- title
- source
- event_type
- status
- blacklist_decision
- matched_persons_json
- matched_keywords_json
- event_similarity_json
- created_at
- updated_at

risk_assessments
- id
- event_id
- risk_level
- risk_score
- dimension_scores_json
- reasoning
- stage           # first / second
- created_at

blacklist_items
- id
- item_type      # customer / keyword / event
- value
- summary
- description
- enabled
- created_at
- updated_at

analysis_tasks
- id
- task_id
- event_id
- status         # queued / running / success / failed
- error_message
- started_at
- finished_at

related_events
- id
- event_id
- related_event_id
- match_source   # person_match / semantic_match / both
- score
- raw_content
- created_at

system_metrics
- id
- metric_type    # latency / gpu / npu / memory
- value_json
- created_at
```

第一版为了简单，可以先用 SQLite：

```text
DATABASE_URL=sqlite:///./sentinel_edge.db
```

后面要正式一点，再换 PostgreSQL：

```text
DATABASE_URL=postgresql+psycopg://sentinel:password@localhost:5432/sentinel_edge
```

简单理解：

- 页面要展示的东西，放 PostgreSQL/SQLite。
- 要快速判断命中不命中，放 Redis。
- 要查“相似文本/相似交易”，放 Milvus。
- 要查“客户 A 和账户 B、设备 C、商户 D 有什么关系”，放 Neo4j。

### 接口怎么设计

先做这些就够用了。

分析接口：

```text
POST /api/analyze
请求:
{
  "text": "2026年...【P102# 客户B】..."
}
返回:
{
  "task_id": "task_xxx",
  "event_id": "event_xxx",
  "status": "success",
  "risk_level": "high",
  "risk_score": 0.82,
  "dimension_scores": {...},
  "blacklist": {
    "decision": "PASS",
    "matched_persons": ["P105"],
    "matched_keywords": ["虚拟币"],
    "event_similarity": {"hit": true, "score": 0.91}
  }
}
```

```text
GET /api/tasks/{task_id}
用途：查看分析任务状态。以后做异步任务时很有用。
```

事件接口：

```text
GET /api/events
参数：page、page_size、risk_level、keyword、date_from、date_to
用途：事件列表页。

GET /api/events/{event_id}
用途：事件详情页。

DELETE /api/events/{event_id}
用途：删除一条演示/测试事件记录。
```

风险评估接口：

```text
GET /api/events/{event_id}/risk-assessments
用途：查看首次和二次风险评估。

GET /api/events/{event_id}/related-events
用途：查看 Milvus 回捞到的历史事件。
```

黑名单接口：

```text
GET /api/blacklist/persons
POST /api/blacklist/persons
DELETE /api/blacklist/persons/{person_id}

GET /api/blacklist/keywords
POST /api/blacklist/keywords
DELETE /api/blacklist/keywords/{keyword}

GET /api/blacklist/events
POST /api/blacklist/events
DELETE /api/blacklist/events/{event_id}
```

示例：

```text
POST /api/blacklist/keywords
{
  "keyword": "虚拟币",
  "description": "反洗钱高风险关键词"
}

POST /api/blacklist/events
{
  "event_id": "E-FIN-AML-001",
  "summary": "客户短时间向多个新账户转账后资金归集至虚拟币平台"
}
```

系统接口：

```text
GET /api/system/health
返回 Redis、Milvus、Neo4j、本地 LLM 是否可用。

GET /api/system/hardware
返回 AMD/GPU/NPU/模型配置画像。

GET /api/system/metrics
返回最近 N 次分析耗时、平均风险分、系统资源。
```

技术选择：

- 后端继续用 FastAPI。
- 先复用现在的 `dashboard.py`，不要另起一套复杂后端。
- 分析结果先存 SQLite，后面再换 PostgreSQL。

### 后端怎么拆

建议后端分 5 层，不要都堆在 `main.py`：

```text
api/              # FastAPI 路由，只负责收请求和返回结果
services/         # 业务服务，例如 AnalysisService、BlacklistService
repositories/     # 数据库读写，例如 EventRepository
schemas/          # API 输入输出模型
workers/          # 后台任务，跑耗时 pipeline
```

第一版可以先做同步接口：前端点按钮后等结果返回。等系统能跑了，再改成后台任务。

### 后端开发顺序

按这个顺序写，不容易乱：

1. 建 `backend/app/main.py`，跑通一个 `/api/system/health`。
2. 建数据库连接和 `financial_events` 表。
3. 写 `POST /api/analyze`，内部先直接调用现有 `process_message()`。
4. 把分析结果存进 `financial_events` 和 `risk_assessments`。
5. 写 `GET /api/events` 和 `GET /api/events/{event_id}`。
6. 写黑名单增删查接口，并复用 `BlacklistStore`。
7. 最后再做任务表 `analysis_tasks`，把同步分析改成异步任务。

第一版不要追求完美，目标是“前端能点按钮，后端能返回风险结果”。

## 第 3 阶段：做一个简单清楚的前端

目标：评委打开网页就知道这个系统在干什么。

建议页面：

- **风险分析页**：一个输入框、一个“开始分析”按钮、结果面板。
- **事件列表页**：按时间查看历史分析记录。
- **事件详情页**：展示风险分、命中规则、关联历史、模型解释。
- **黑名单管理页**：维护关键词、客户编号、高危事件样本。
- **系统状态页**：展示 Milvus/Neo4j/Redis/LLM/硬件画像。

技术选择：

- 如果想快：用现有 FastAPI + Jinja2 模板。
- 如果想更像正式全栈项目：React/Vite + FastAPI。
- 先不要做登录注册，比赛 Demo 阶段可以用一个简单的管理口令。

### 前端怎么设计

第一版页面布局可以很简单：

```text
左侧导航：
- 风险分析
- 事件记录
- 黑名单
- 知识图谱
- 系统状态

风险分析页：
- 顶部：输入框 + 分析按钮
- 中间：风险等级、风险分数、多维度评分条
- 下方：模型理由、命中规则、关联历史交易、处置建议

事件详情页：
- 原始文本
- 标准化结果
- 首次风险评估
- 二次风险评估
- Milvus 回捞结果
- Neo4j 图谱摘要
```

前端不要一开始做复杂动画，先把信息展示清楚。评分条、标签、表格、详情抽屉就够了。

### Vue3 页面和组件

页面：

```text
views/
- AnalyzeView.vue          # 风险分析
- EventsView.vue           # 事件列表
- EventDetailView.vue      # 事件详情
- BlacklistView.vue        # 黑名单管理
- SystemStatusView.vue     # 系统状态
```

组件：

```text
components/
- RiskBadge.vue            # high / medium / low 标签
- RiskScoreGauge.vue       # 风险分仪表盘或进度条
- DimensionScoreBars.vue   # 多维度评分条
- BlacklistHitPanel.vue    # 命中详情
- RelatedEventsTable.vue   # 关联历史事件
- SystemHealthCards.vue    # Redis/Milvus/Neo4j/LLM 状态卡片
```

前端 API 文件：

```text
src/api/analysis.ts
src/api/events.ts
src/api/blacklist.ts
src/api/system.ts
```

前端开发顺序：

1. 先做 `AnalyzeView.vue`，一个文本框，一个按钮，一个结果 JSON 区域。
2. 把 JSON 区域拆成风险分、维度评分、命中详情。
3. 做 `EventsView.vue`，展示历史事件表格。
4. 做 `BlacklistView.vue`，实现关键词、人员、高危事件的新增/删除。
5. 做 `SystemStatusView.vue`，展示服务健康状态。

推荐路由：

```text
/analysis
/events
/events/:eventId
/blacklist
/system
```

### 前后端联调流程

1. 启动后端：

```bash
uv run uvicorn backend.app.main:app --reload --port 8000
```

2. 启动前端：

```bash
cd frontend
npm install
npm run dev
```

3. 前端 `.env.development`：

```text
VITE_API_BASE_URL=http://127.0.0.1:8000
```

4. 前端请求后端时统一从 `src/api/http.ts` 里读 `VITE_API_BASE_URL`。

## 第 4 阶段：做比赛展示增强

目标：让作品看起来“确实用到了端侧 AI 和 AMD 平台”。

需要补：

- 性能记录：每个阶段耗时，例如标准化、分类、构图、检索、风险评估。
- 硬件状态：GPU/NPU 是否检测到，当前模型名称，推理 endpoint。
- 资源监控截图：内存、GPU、CPU 占用。
- 对比实验：云端/CPU 基线 vs 本地 GPU 量化模型。
- 隐私说明：客户编号脱敏、日志脱敏、数据不出内网。

## 推荐开发顺序

1. 修 Docker + Python 环境。
2. 跑通 `finance_demo_cases.py` 三个默认用例。
3. 新增 `POST /api/analyze`。
4. 做一个最简单的网页输入框和结果展示。
5. 增加系统状态页。
6. 增加黑名单管理页。
7. 补性能统计和演示视频素材。

## 你现在最该做的三件事

1. 让 Milvus 变成 healthy。
2. 换到 Python 3.13 环境。
3. 用金融 Demo 跑出第一份完整 JSON 报告。
