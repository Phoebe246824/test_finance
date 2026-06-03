# Sentinel 舆情分析系统

多源事件实时接入 → 黑名单过滤 → AI 分类评级 → 单条构图 → 风险上下文检索 → 首次风险评估 → （仅超阈值）批量补图 + 二次风险评估 → （仍超阈值）意图分析与趋势预测。

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                     用户输入 (终端 / Web 看板)                    │
└────┬────────────────────────────────────────────────────────────┘
     │
     ▼
┌────────────────────────────────────────────────────────────────┐
│  Stage 1  事件标准化 (CrewAI Agent)                              │
│  Normalizer Agent → 原始消息 → NormalizedEvent                   │
└────────────────────────────┬───────────────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────────────┐
│  Stage 1.5  黑名单过滤 (新增)                                     │
│  ├─ 人员 ID 比对  → person_blacklist (Redis)                     │
│  ├─ 敏感词比对    → keyword_blacklist (Redis)                    │
│  └─ 事件相似度比对 → event_blacklist (Redis)                     │
│                                                                 │
│  OR 逻辑：任一命中 → PASS      全未命中 → STASH                   │
│            │                       │                             │
│            ▼                       ▼                             │
│        进入 Stage 2          存入 Milvus 暂存池                   │
│                          支持人员 ID + 语义召回                  │
│                                                                 │
│  PASS 后在 main.py 中自动积累命中记录                              │
└────────────────────────────┬───────────────────────────────────┘
                             │ (PASS 路径)
                             ▼
┌────────────────────────────────────────────────────────────────┐
│  Stage 2  事件分类 (CrewAI Agent)                                │
│  TypeClassifier Agent → 事件类型 + 关键实体提取                   │
└────────────────────────────┬───────────────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────────────┐
│  Stage 3  当前事件单条构图 (Graphiti + Neo4j)                    │
│  Episode 写入 → LLM 实体/关系提取 → 去重合并 → 向量               │
└────────────────────────────┬───────────────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────────────┐
│  Stage 4  首次风险上下文检索 (Graphiti)                          │
│  语义向量 + BM25 + 图遍历                                        │
└────────────────────────────┬───────────────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────────────┐
│  Stage 5  首次风险评估 (CrewAI Agent)                            │
│  RiskEvaluator Agent（使用 Stage 4 上下文）                      │
└────────────────────────────┬───────────────────────────────────┘
                             │
                 ┌───────────┴───────────┐
                 │                       │
                 ▼                       ▼
       score <= threshold         score > threshold
                 │                       │
                 │                       ▼
                 │         ┌──────────────────────────────────────┐
                 │         │ Stage 6 批量补图 (Milvus 回捞候选)      │
                 │         │ 共享人员直通；非同人候选需通过 rerank    │
                 │         │ 已构图 Episode 跳过，避免重复写 Neo4j    │
                 │         └────────────────┬─────────────────────┘
                 │                          │
                 │          ┌───────────────┴───────────────┐
                 │          │                               │
                 │          ▼                               ▼
                 │   无回捞事件 fetched=0             有回捞事件 fetched>0
                 │          │                               │
                 │          │                               ▼
                 │          │               ┌──────────────────────────────────────┐
                 │          │               │ Stage 7 二次风险上下文检索 + 二次评估    │
                 │          │               │ (有回捞候选时重新检索并评估)             │
                 │          │               └────────────────┬─────────────────────┘
                 │          │                                │
                 │          │                    ┌───────────┴───────────┐
                 │          │                    │                       │
                 │          │                    ▼                       ▼
                 │          │          second_score <= threshold  second_score > threshold
                 │          │                    │                       │
                 ▼          ▼                    ▼                       ▼
           ┌────────────┐  ┌──────────────────────────────┐  ┌────────────┐  ┌──────────────────────────────┐
           │  complete  │  │ Stage 8 Dashboard            │  │  complete  │  │ Stage 8 Dashboard            │
           │  流程结束   │  │ 意图分析 + 趋势预测 (自适应) │  │  流程结束   │  │ 意图分析 + 趋势预测 (自适应) │
           └────────────┘  └──────────────┬───────────────┘  └────────────┘  └──────────────┬───────────────┘
                                                           │
                                                           ▼
                                                     ┌────────────┐
                                                     │  complete  │
                                                     │  流程结束   │
                                                     └────────────┘
```

**数据流说明**:
1. 用户通过终端或 Web 看板输入消息
2. Stage 1: 标准化 → NormalizedEvent
3. Stage 1.5: 黑名单过滤（三合一 OR 匹配）→ PASS 进入 pipeline / STASH 暂存 Milvus
4. Stage 2: 事件分类 + 关键实体提取
5. Stage 3: 当前事件单条构图，并立即将当前事件标记为已构图
6. Stage 4: 在当前图上检索首次风险上下文
7. Stage 5: 首次风险评估（使用 Stage 4 上下文）
8. 若 Stage 5 `score <= threshold`：直接结束流程（不进入 Dashboard）
9. 若 Stage 5 `score > threshold`：从 Milvus 回捞历史暂存事件候选，并先做相关性准入过滤
10. Stage 6: 共享人员 ID 的历史事件直接进入批量补图；非同人候选需通过 rerank 阈值过滤；Neo4j 已存在相同 Episode 时跳过重复构图并标记 Milvus `is_graph_built=True`
11. 若 Stage 6 `fetched_count == 0`：跳过二次检索和二次风险评估，直接进入 Stage 8 Dashboard（保留首次风险评估结果）
12. 若 Stage 6 `fetched_count > 0`：Stage 7 在补图/去重检查后检索二次风险上下文并执行二次风险评估；即使过滤后没有新增构图，也会继续二次检索和二次评估
13. 若二次评估 `score > threshold`：进入 Stage 8 Dashboard；否则结束流程

**核心组件**:
- **Redis**: 黑名单存储（人员 / 关键词 / 相似事件）
- **Milvus**: 未命中事件暂存与同人/语义候选回捞，构图后通过 `is_graph_built` 避免重复回捞
- **黑名单过滤器**: 人员监控 + 关键词监控 + 相似事件监控
- **Rerank 过滤**: 对非共享人员 ID 的 Milvus 候选做精排过滤，避免语义粗召回噪声进入批量构图
- **批量构图**: 中/高风险触发，合并通过准入的历史事件一次性写入图谱，并跳过 Neo4j 已存在 Episode

## 项目结构

```
test_Sentinel/
├── main.py                  # 主入口，CrewAI Flow 流水线编排（含黑名单过滤 + Milvus 暂存 + 批量构图）
├── models.py                # 共享 Pydantic 数据模型
├── consumer.py              # 事件标准化服务
├── classifier.py            # 事件分类服务 (CrewAI)
├── dashboard.py             # Web 看板服务 (FastAPI)
├── graph_service.py         # 知识图谱服务 (Graphiti)
├── log_utils.py             # 双输出日志系统
├── blacklist/               # 黑名单系统
│   ├── __init__.py          # BlacklistStore, BlacklistFilter, MilvusStashStore
│   ├── store.py             # Redis 黑名单 CRUD
│   ├── milvus_stash.py      # Milvus 暂存、回捞、已构图标记
│   └── filter.py            # 三合一 OR 匹配器
├── utils/
│   └── text.py              # 人员 ID 提取工具
├── graphiti/
│   └── graphiti_workflow.py # Graphiti 知识图谱操作（含批量构图）
├── trend_prediction/        # 事件分类与自适应提示词模块
│   ├── __init__.py          # 公共 API 导出
│   ├── classifier.py        # 事件分类器（Jina Rerank + 关键词回退）
│   ├── task_templates.py    # 自适应任务模板工厂
│   ├── adapters/            # 领域适配器（7 个领域 + 基类）
│   └── prompts/             # 兜底提示词模板
├── providers/
│   ├── __init__.py          # LLM/Embedder 提供商
│   ├── llm_provider.py      # LLM 提供商
│   └── embedder_provider.py # Embedder 提供商
├── scripts/
│   ├── reset_and_seed_blacklist.py  # 重置并写入测试种子数据
│   └── run_blacklist_kv_demo.py     # 15 个测试用例自动回放
├── tests/                   # 单元测试（51 tests）
├── compose/                 # Docker Compose 服务定义
├── .env                     # 环境变量配置
├── .env.example             # 环境变量示例
└── requirements.txt         # Python 依赖
```

## 核心模块说明

### main.py — Pipeline 编排

`SentinelPipelineFlow` (CrewAI Flow):

```
标准化 → 黑名单过滤 → Classification → Single Graph Build
                                          → Search First Risk Context
                                          → First Risk Evaluation
                                          → Router
                                            ├── complete
                                            └── batch_graph
                                                  → Search Second Risk Context
                                                  → Second Risk Evaluation
                                                  → Router
                                                    ├── go_dashboard
                                                    └── complete
                                          → Dashboard (仅 go_dashboard) → complete
```

**Dashboard 阶段**:
- **事件分类器**: Jina Rerank API 同时分类事件类别（7 种）和影响严重度（4 级），无 API Key 时回退到关键词匹配
- **意图分析专家**: 根据事件类别使用领域自适应提示词（国际政治/科技/经济/社会/公共卫生/能源/金融各有专属分析维度）
- **趋势预测专家**: 根据类别 + 严重度动态调整时间范围（轻微→几天到几周，重大→5 年以上）

**运行方式**: 从终端输入消息进行分析

```bash
uv run main.py
# 输入消息内容进行分析，输入 'quit' 或 'exit' 退出
```

### models.py — 数据模型

| 模型 | 用途 | 关键字段 |
|------|------|----------|
| `NormalizedEvent` | 标准化事件 | event_id, source, raw_content, structured_data, trace_id, event_type, risk_level, risk_score |
| `ClassifiedEvent` | 分类结果 | event_type, risk_level, risk_score, key_entities, summary, reasoning |
| `QueueMessage` | RabbitMQ 消息封装 | payload, msg_type, version, trace_id |
| `EventSource` | 事件来源枚举 | NEWS, CHAT, TRANSACTION, BEHAVIOR |
| `RiskLevel` | 风险等级枚举 | HIGH, MEDIUM, LOW |
| `EventType` | 事件类型枚举 | EMERGENCY, NEGATIVE, POSITIVE, INFORMATION, BUSINESS |
| `KeyEntity` | 关键实体 | name, type |

### dashboard.py — Web 看板服务

基于 FastAPI 构建的 Web 看板，提供事件可视化与统计分析。

**主要端点**:
- `GET /` — 看板主页（HTML）
- `GET /api/events` — 事件列表（分页、过滤）
- `GET /api/events/{event_id}` — 事件详情
- `GET /api/stats` — 统计数据
- `GET /api/stats/risk-distribution` — 风险分布
- `GET /api/stats/source-distribution` — 来源分布
- `GET /api/graph/stats` — 图谱统计

**启动方式**:
```bash
uv run uvicorn dashboard:app --reload --port 8000
```

### graph_service.py — 知识图谱服务

基于 Graphiti 构建时序知识图谱，将命中黑名单的当前事件先单条入图；若 Neo4j 已存在同文本 Episode，则跳过重复单条构图。若首次风险超阈值，再从 Milvus 回捞历史暂存候选：共享人员 ID 的候选直接补图，非同人候选必须通过 rerank 阈值过滤；已存在 Neo4j 的候选只标记 Milvus 已构图，不重复写图。有回捞候选时基于补图/去重后的上下文执行二次风险评估；无回捞候选时跳过二次检索和二次评估，直接进入 Dashboard。

**核心功能**:
- `init_graphiti()`: 初始化 Graphiti 客户端（连接 Neo4j、配置 LLM/Embedder）
- `add_episode()`: 将事件作为 Episode 写入 Graphiti，自动提取实体和关系
- `search()`: 混合检索（语义 + 关键词 + 图遍历 + 重排序）
- `close_graphiti()`: 关闭连接释放资源

### graphiti/graphiti_workflow.py — Graph 底层操作

- `add_event_to_graph()`: 将事件写入图谱，Graphiti 自动提取实体/关系/向量嵌入
- `hybrid_search()`: 混合检索 — 语义向量 + BM25 + BFS 图遍历 → RRF 融合，支持 `min_score` 相关性阈值过滤低分结果

### trend_prediction/ — 事件分类与自适应提示词

**EventClassifier**: 基于 Jina Rerank API 的事件分类器，支持 7 种事件类别和 4 级影响严重度评估。

- `classify_with_severity()`: 单次 API 调用同时返回类别 + 严重度，失败时自动回退到关键词匹配
- 关键词覆盖：7 类别 × 约 20 关键词 + 4 级严重度 × 约 12 关键词

**领域适配器**: 每个领域有专属的分析维度和提示词模板。

| 适配器 | 类别标识 | 专注维度 |
|---|---|---|
| `intl_politics` | 国际政治 | 地缘冲突、外交关系、制裁禁令 |
| `tech` | 科技 | 技术创新、芯片/AI、竞争格局 |
| `economy` | 经济 | 宏观经济、货币政策、供应链 |
| `society` | 社会/文化 | 性别/种族、教育医疗、社会福利 |
| `public_health` | 公共卫生 | 传染病、疫苗、医疗资源 |
| `energy` | 能源 | 石油/新能源、碳排放、电网 |
| `finance` | 金融 | 银行保险、证券基金、金融风险 |

**严重度到时间范围映射**:

| 严重度 | 短期 | 中期 | 长期 |
|---|---|---|---|
| 轻微 | 几天到几周 | 几周（无显著持续影响） | 无显著长期影响 |
| 一般 | 1-3 个月 | 3-12 个月 | 1-2 年（有限长期影响） |
| 严重 | 1-3 个月 | 3-12 个月 | 1-5 年（显著长期影响） |
| 重大 | 1-3 个月 | 3-12 个月 | 5 年以上（深远长期影响） |

## 快速开始

### 1. 安装依赖

```bash
uv sync --dev
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`，填入实际配置:

```env
# Redis 配置（黑名单）
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
BLACKLIST_REDIS_DB=1

# Milvus 配置（事件暂存）
MILVUS_URI=http://localhost:19530
MILVUS_TOKEN=
MILVUS_STASH_COLLECTION=stashed_events
KV_TTL_DAYS=90
STASH_SEMANTIC_TOP_K=10
BATCH_MAX_PER_PERSON=20

# RabbitMQ 配置
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest

# Neo4j 配置
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password

# LLM 配置
LLM_PROVIDER=siliconflow
LLM_MODEL=deepseek-ai/DeepSeek-V3.2
LLM_API_KEY=sk-your-api-key
LLM_BASE_URL=https://api.siliconflow.cn/v1

# Embedding 配置
EMBEDDER_MODEL=BAAI/bge-m3
EMBEDDER_API_BASE=https://api.siliconflow.cn/v1

# 风险阈值
RISK_THRESHOLD=0.7
```

### 3. 启动依赖服务

```bash
docker compose up -d
```

确保以下服务已运行:
- **Redis**: `localhost:6379` (黑名单存储 + 事件暂存)
- **Neo4j**: `localhost:7687` (知识图谱存储)
- **RabbitMQ**: `localhost:5672` (消息队列)

### 4. 启动系统

#### 方式一：终端 Pipeline（分析消息）

```bash
uv run main.py
```

#### 方式二：Web 看板（可视化界面）

```bash
uv run uvicorn dashboard:create_dashboard_app --factory --reload --port 8000
```

然后访问 http://localhost:8000 查看看板。

系统启动后，在终端输入消息进行分析:

```
======================================================================
  Sentinel Pipeline — CrewAI Flow 驱动
  输入消息进行分析 (输入 'quit' 或 'exit' 退出)
======================================================================

请输入消息内容:
> 某科技公司因产品质量问题被监管部门立案调查
============================================ 消息处理开始 =============================================

[Flow] 用户输入: 某科技公司因产品质量问题被监管部门立案调查
[Flow] 标准化事件: event_id=01JQ..., source=news
[Flow] 黑名单过滤: PASS (命中敏感词) or STASH (暂存到 Milvus)
[Flow] Stage 2: Classification
[Flow] Stage 3: Single Graph Build
[Flow] Stage 4: Search First Risk Context
[Flow] Stage 5: First Risk Evaluation
[Flow] risk_score > threshold: 执行 Milvus 回捞 + 批量补图准入过滤
[Flow] Stage 6: Batch Graph Build from Stash (共享人员直通；非同人候选 rerank 过滤；Neo4j 已存在则跳过重复构图)
[Flow] fetched_count == 0: 跳过二次检索/二次评估，直接进入 Stage 8
[Flow] fetched_count > 0: Stage 7 Search Second Risk Context + Second Risk Evaluation
[Flow] Stage 8: Dashboard

[dashboard] 分析结果:
======================================================================
# 意图分析报告
...
# 趋势预测报告
...
======================================================================

[Flow] 消息处理完成 ✓

请输入消息内容:
> quit
退出程序
```

## 技术栈

| 组件 | 技术选型 |
|------|----------|
| Agent 框架 | CrewAI (Flow + Agent + Crew) |
| 知识图谱 | Graphiti + Neo4j |
| 黑名单/缓存 | Redis (redis-py) |
| LLM | SiliconFlow API (DeepSeek-V3) |
| Embedding | BAAI/bge-m3 (SiliconFlow) |
| 数据模型 | Pydantic v2 |
| Web 框架 | FastAPI + Jinja2 |
| 向量检索 | Graphiti Hybrid Search |

## 依赖

```
fastapi          # Web 框架
uvicorn          # ASGI 服务器
crewai           # 多 Agent 框架
graphiti-core    # 时序知识图谱
neo4j            # Neo4j 驱动
redis            # Redis 客户端（黑名单）
pymilvus         # Milvus 客户端（事件暂存，可按需安装）
pydantic         # 数据模型
python-dotenv    # 环境变量
ulid-py          # 唯一 ID 生成
httpx            # HTTP 客户端
```

## providers 模块说明

### providers/llm_provider.py — LLM 提供商

封装 SiliconFlow LLM 调用，提供统一的接口供 CrewAI Agent 使用。

**主要功能**:
- `get_llm()`: 获取配置好的 LLM 实例
- 支持自定义模型、温度、max_tokens 等参数

### providers/embedder_provider.py — Embedder 提供商

封装 SiliconFlow Embedding 调用，提供向量嵌入能力。

**主要功能**:
- `get_embedder()`: 获取配置好的 Embedder 实例
- 支持 BAAI/bge-m3 等模型
