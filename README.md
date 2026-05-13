# Sentinel 舆情分析系统

多源事件实时接入 → AI 分类评级 → 知识图谱构建 → 混合检索 → 可视化看板。

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        RabbitMQ 消息总线                         │
│   sentinel.events.* (入站)          sentinel.internal.* (站内)   │
└────┬──────┬──────┬──────┬─────────────────┬─────────────────────┘
     │      │      │      │                 │
  news   chat  txn  behavior          classified / high_risk
     │      │      │      │                 │
┌────▼──────▼──────▼──────▼─────────────────▼─────────────────────┐
│  Stage 1  Ingestion (consumer.py)                               │
│  多队列消费 → 事件标准化(NormalizedEvent) → 幂等去重 → 转发下游    │
└────────────────────────────┬────────────────────────────────────┘
                             │ sentinel.internal.normalized
                             ▼
┌────────────────────────────────────────────────────────────────┐
│  Stage 2  Classification (classifier.py + CrewAI)               │
│  TypeClassifier Agent → 事件类型 + 关键实体提取                   │
│  RiskEvaluator Agent → 风险等级(high/medium/low) + 风险分数       │
│  Fallback: 关键词规则引擎(LLM 不可用时降级)                       │
└────────────────────────────┬───────────────────────────────────┘
                             │ sentinel.internal.classified
                             ▼
┌────────────────────────────────────────────────────────────────┐
│  Stage 3  Graph (graph_service.py + Graphiti + Neo4j)           │
│  Episode 写入 → LLM 实体/关系提取 → 去重合并 → 向量嵌入            │
│  Bi-temporal 模型追踪事实演变                                    │
└────────────────────────────┬───────────────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────────────┐
│  Stage 4  Search (混合检索)                                      │
│  语义向量 + BM25 全文 + BFS 图遍历 → RRF 融合重排序               │
└────────────────────────────┬───────────────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────────────┐
│  Stage 5  Dashboard (dashboard.py + FastAPI + Jinja2)           │
│  统计卡片 / 风险分布饼图 / 来源柱状图 / 事件列表(分页+多维过滤)     │
└────────────────────────────────────────────────────────────────┘
```

## 项目结构

```
case_analysis/
├── main.py                  # 主入口，Pipeline 流水线编排 + CrewAI Flow
├── models.py                # 共享 Pydantic 数据模型
├── consumer.py              # Stage 1: 事件接入(Ingestion)服务
├── classifier.py            # Stage 2: CrewAI 分类评级服务
├── graph_service.py         # Stage 3: Graphiti 知识图谱服务
├── dashboard.py             # Stage 5: FastAPI Web 看板
├── providers/
│   ├── llm_provider.py      # LLM 提供商(SiliconFlow / DeepSeek-V3)
│   └── embedder_provider.py # Embedding 提供商(BAAI/bge-m3)
├── .env                     # 环境变量配置
└── requirements.txt         # Python 依赖
```

## 核心模块说明

### models.py — 数据模型

所有服务共用的 Pydantic 模型，通过 RabbitMQ JSON 序列化传递:

| 模型 | 用途 | 关键字段 |
|------|------|----------|
| `NormalizedEvent` | Ingestion 产出 | event_id, source, raw_content, structured_data, trace_id |
| `ClassifiedEvent` | Classification 产出 | event_type, risk_level, risk_score, key_entities, summary |
| `QueueMessage` | RabbitMQ 消息封装 | payload, msg_type, version, trace_id |

枚举类型: `EventSource`(news/chat/transaction/behavior), `RiskLevel`(high/medium/low), `EventType`(突发事件/负面舆情/正面舆情/信息传播/商业动态)

### consumer.py — Ingestion 服务

- **多队列消费**: 同时监听 4 个源队列(news/chat/transaction/behavior)
- **事件标准化**: `normalize_event()` 将不同来源的原始事件统一为 `NormalizedEvent`
- **幂等去重**: 内存缓存 + TTL(1h)，Phase 3 升级为 Redis
- **RabbitMQ 拓扑**: Topic Exchange(sentinel.events) + Direct Exchange(sentinel.internal) + DLQ
- **FastAPI 接口**: `/send-message`(测试发送) + `/events`(分页查询) + `/stats`(消费统计)

### classifier.py — Classification 服务

CrewAI Agent 驱动的两阶段分类:

1. **TypeClassifier Agent**: 识别事件类型 + 提取关键实体(快速模型)
2. **RiskEvaluator Agent**: 评估风险等级 + 风险分数 0-1(推理模型)

内置降级策略 `fallback_classify()`: LLM 不可用时使用关键词匹配规则引擎。

### graph_service.py — Graph 服务

基于 Graphiti 构建时序知识图谱:

- `add_episode()`: 将事件写入图谱，Graphiti 自动提取实体/关系/向量嵌入
- `search()`: 混合检索 — 语义向量 + BM25 + BFS 图遍历 → RRF 融合
- `get_graph_stats()`: 图谱统计(节点数/关系数/类型分布)

### dashboard.py — Dashboard 服务

FastAPI + Jinja2 服务端渲染看板:

- 统计卡片(总事件数/高风险数/图谱节点数/处理速率)
- 风险分布饼图 / 来源分布柱状图(Chart.js)
- 事件列表(分页 + 来源/风险等级/事件类型/关键词多维过滤)

### main.py — Pipeline 编排

`SentinelPipelineFlow`(CrewAI Flow):

```
Classification → Graph Build → Risk Evaluation → [Router]
                                            ├── low risk  → 结束
                                            └── high/medium → Search → Dashboard
```

`run_flow()`: 持续监听 RabbitMQ 队列，消费消息后启动 Flow 处理。

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env` 文件，填入实际的 Neo4j / LLM / Embedding 配置:

```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password

LLM_PROVIDER=siliconflow
LLM_MODEL=deepseek-ai/DeepSeek-V3.2
LLM_API_KEY=sk-your-api-key
LLM_BASE_URL=https://api.siliconflow.cn/v1
```

### 3. 启动依赖服务

确保以下服务已运行:
- **RabbitMQ**: `localhost:5672` (消息队列)
- **Neo4j**: `localhost:7687` (知识图谱存储)

### 4. 启动系统

```bash
# 启动完整 Pipeline (监听 RabbitMQ)
python main.py
```

系统启动后会持续监听 `fastapi_queue` 队列，消费消息并执行完整流水线。

## 技术栈

| 组件 | 技术选型 |
|------|----------|
| Agent 框架 | CrewAI (Flow + Agent + Crew) |
| 消息队列 | RabbitMQ (pika) |
| 知识图谱 | Graphiti + Neo4j |
| LLM | SiliconFlow API (DeepSeek-V3) |
| Embedding | BAAI/bge-m3 (SiliconFlow) |
| Web 框架 | FastAPI + Jinja2 |
| 数据模型 | Pydantic v2 |

## 消息队列拓扑

```
sentinel.events (Topic Exchange)
  ├── sentinel.events.news
  ├── sentinel.events.chat
  ├── sentinel.events.transaction
  └── sentinel.events.behavior

sentinel.internal (Direct Exchange)
  ├── sentinel.internal.normalized    (→ Classification)
  ├── sentinel.internal.classified    (→ Graph)
  └── sentinel.internal.high_risk     (Phase 2 告警)

sentinel.dlx (Dead Letter Exchange)
  └── sentinel.dlq.ingestion          (消费失败消息)
```

## 依赖

```
fastapi          # Web 框架
uvicorn          # ASGI 服务器
pika             # RabbitMQ 客户端
crewai           # 多 Agent 框架
graphiti-core    # 时序知识图谱
neo4j            # Neo4j 驱动
pydantic         # 数据模型
python-dotenv    # 环境变量
jinja2           # 模板引擎
ulid-py          # 唯一 ID 生成
httpx            # HTTP 客户端
```
