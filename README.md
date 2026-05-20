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
                                           │  事件分类 + 严重度评估           │
                                           │  意图分析 + 趋势预测 (自适应)    │
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
- **事件分类器**: Jina Rerank API 同时分类事件类别（7 种）和影响严重度（4 级），无 API Key 时回退到关键词匹配
- **意图分析专家**: 根据事件类别使用领域自适应提示词（国际政治/科技/经济/社会/公共卫生/能源/金融各有专属分析维度）
- **趋势预测专家**: 根据类别 + 严重度动态调整时间范围（轻微→几天到几周，重大→5 年以上）

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
pip install -r requirements.txt
```

### 2. 配置环境变量

> **⚠️ 默认配置变更 (2026-05-18)**
> 
> 本次更新将默认 LLM 提供商从 `SiliconFlow` 改为 `OpenAI (gpt-4o)`。
> 
> **影响**：
> - 未配置 `.env` 的用户将默认使用 OpenAI API
> - gpt-4o 费用显著高于 DeepSeek-V3.2
> 
> **回退方法**：
> 在 `.env` 中设置 `LLM_PROVIDER=siliconflow` 并配置对应 API Key

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