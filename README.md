# Sentinel 舆情分析系统

多源事件实时接入 → AI 分类评级 → 知识图谱构建 → 混合检索 → 意图分析 → 趋势预测。

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
│  Stage 2  事件分类 (CrewAI Agent)                                │
│  TypeClassifier Agent → 事件类型 + 关键实体提取                   │
│                        ↓                                        │
│              ┌─────────────────────┐                            │
│              │ 人物提取 → 关系型数据库 │  ← 所有事件的人物提取      │
│              │ (人物库/关键词库)      │                            │
│              └──────────┬──────────┘                            │
│                         │                                       │
│                         ▼                                       │
│              ┌─────────────────────┐                            │
│              │  监控匹配引擎        │  ← 人物/关键词/相似事件监控  │
│              │ 人物 + 关键词 + 相似  │                            │
│              └──────────┬──────────┘                            │
└─────────────────────────┼───────────────────────────────────────┘
                          │
                          ▼
┌────────────────────────────────────────────────────────────────┐
│  Stage 3  知识图谱构建 (Graphiti + Neo4j)                        │
│  监控事件 → Episode 写入 → LLM 实体/关系提取 → 去重合并 → 向量    │
└────────────────────────────┬───────────────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────────────┐
│  Stage 4  风险评估 (CrewAI Agent)                                │
│  RiskEvaluator Agent → 风险等级 + 风险分数                        │
└────────────────────────────┬───────────────────────────────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
              ▼                             ▼
        low risk                      high/medium risk
              │                             │
              │                          ┌──┴────────────────────────────────────────────────────┐
              │                          │  Stage 4-1  二次分析评估 (CrewAI Agent)                │
              │                          │  ① 从关系型数据库召回关联事件                           │
              │                          │  ② RiskEvaluator Agent → 风险等级 + 风险分数            │
              │                          └──┬────────────────────────────────────────────────────┘
              │                             │
              ▼                             ▼
           流程结束                         ┌────────────────────────────────┐
                                          │  Stage 5  混合检索 (Graphiti)  │
                                          │  语义向量 + BM25 + 图遍历       │
                                          └────────────┬─────────────────┘
                                                       │
                                                       ▼
                                          ┌────────────────────────────────┐
                                          │  Stage 6  消息推送              │
                                          │  按事件类型 → 不同消息通道       │
                                          │  突发事件→短信/邮件              │
                                          │  负面舆情→企业微信/钉钉          │
                                          │  商业动态→内部系统              │
                                          └────────────┬─────────────────┘
                                                       │
                                                       ▼
                                          ┌────────────────────────────────┐
                                          │  Stage 7  Dashboard            │
                                          │  意图分析 + 趋势预测 (CrewAI)   │
                                          └────────────────────────────────┘
```

**数据流说明**:
1. 用户通过终端或 Web 看板输入消息
2. Stage 1-2: 标准化 → 分类，同时提取人物存入关系型数据库
3. 监控匹配引擎检查人物/关键词/相似事件，决定是否构图
4. Stage 3: 监控事件写入知识图谱
5. Stage 4: 风险评估，低风险结束，高/中风险进入 Stage 4-1
6. Stage 4-1: 从关系型数据库召回关联事件，进行二次分析
7. Stage 5: 混合检索
8. Stage 6: 按事件类型推送到不同消息通道
9. Stage 7: Dashboard 意图分析和趋势预测

**核心组件**:
- **关系型数据库**: 存储人物库、关键词库、事件索引
- **监控匹配引擎**: 人物监控 + 关键词监控 + 相似事件监控
- **消息推送网关**: 短信/邮件/企业微信/钉钉/内部系统

## 项目结构

```
case_analysis/
├── main.py                  # 主入口，CrewAI Flow 流水线编排
├── models.py                # 共享 Pydantic 数据模型
├── consumer.py              # 事件标准化服务
├── classifier.py            # 事件分类服务 (CrewAI)
├── dashboard.py             # Web 看板服务 (FastAPI)
├── graph_service.py         # 知识图谱服务 (Graphiti)
├── graphiti/
│   └── graphiti_workflow.py # Graphiti 知识图谱操作
├── providers/
│   ├── __init__.py          # LLM/Embedder 提供商
│   ├── llm_provider.py      # LLM 提供商 (SiliconFlow)
│   └── embedder_provider.py # Embedder 提供商
├── .env                     # 环境变量配置
├── .env.example             # 环境变量示例
└── requirements.txt         # Python 依赖
```

## 核心模块说明

### main.py — Pipeline 编排

`SentinelPipelineFlow` (CrewAI Flow):

```
Classification → Graph Build → Risk Evaluation → [Router]
                                            ├── low risk  → 结束
                                            └── high/medium → Search → Dashboard
```

**Dashboard 阶段**:
- **意图分析专家**: 分析表面意图、深层动机、利益相关方、潜在影响、信号强度
- **趋势预测专家**: 预测短期/中期/长期趋势、关键转折点、概率评估、风险预警

**运行方式**: 从终端输入消息进行分析

```bash
python main.py
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
python -m uvicorn dashboard:app --reload --port 8000
```

### graph_service.py — 知识图谱服务

基于 Graphiti 构建时序知识图谱，将所有分类后的事件写入图谱。

**核心功能**:
- `init_graphiti()`: 初始化 Graphiti 客户端（连接 Neo4j、配置 LLM/Embedder）
- `add_episode()`: 将事件作为 Episode 写入 Graphiti，自动提取实体和关系
- `search()`: 混合检索（语义 + 关键词 + 图遍历 + 重排序）
- `close_graphiti()`: 关闭连接释放资源

### graphiti/graphiti_workflow.py — Graph 底层操作

- `add_event_to_graph()`: 将事件写入图谱，Graphiti 自动提取实体/关系/向量嵌入
- `hybrid_search()`: 混合检索 — 语义向量 + BM25 + BFS 图遍历 → RRF 融合

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`，填入实际配置:

```env
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

确保以下服务已运行:
- **Neo4j**: `localhost:7687` (知识图谱存储)

### 4. 启动系统

#### 方式一：终端 Pipeline（分析消息）

```bash
python main.py
```

#### 方式二：Web 看板（可视化界面）

```bash
python -m uvicorn dashboard:create_dashboard_app --factory --reload --port 8000
```

然后访问 http://localhost:8000 查看看板。

系统启动后，在终端输入消息进行分析:

```
======================================================================
  Sentinel Pipeline Flow — CrewAI Flow 驱动
  输入消息进行分析 (输入 'quit' 或 'exit' 退出)
======================================================================

请输入消息内容:
> 某科技公司因产品质量问题被监管部门立案调查
============================================ 消息处理开始 =============================================

[Flow] 用户输入: 某科技公司因产品质量问题被监管部门立案调查
[Flow] 标准化事件: event_id=01JQ..., source=news
[Flow] Stage 2: Classification
[Flow] Stage 3: Graph Build
[Flow] Stage 4: Risk Evaluation
[Flow] 非低风险事件，进入 Search
[Flow] Stage 5: Search
[Flow] Stage 6: Dashboard

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