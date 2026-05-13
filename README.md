# Sentinel 舆情分析系统

多源事件实时接入 → AI 分类评级 → 知识图谱构建 → 混合检索 → 意图分析 → 趋势预测。

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户输入 (终端)                           │
└────┬────────────────────────────────────────────────────────────┘
     │
     ▼
┌────────────────────────────────────────────────────────────────┐
│  Stage 1  事件标准化 (normalize_payload_to_event)               │
│  CrewAI Agent 将原始消息转换为 NormalizedEvent                   │
└────────────────────────────┬───────────────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────────────┐
│  Stage 2  Classification (CrewAI Agent)                         │
│  TypeClassifier Agent → 事件类型 + 关键实体提取                   │
└────────────────────────────┬───────────────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────────────┐
│  Stage 3  Graph Build (Graphiti + Neo4j)                        │
│  Episode 写入 → LLM 实体/关系提取 → 去重合并 → 向量嵌入            │
└────────────────────────────┬───────────────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────────────┐
│  Stage 4  Risk Evaluation (CrewAI Agent)                        │
│  RiskEvaluator Agent → 风险等级(high/medium/low) + 风险分数       │
└────────────────────────────┬───────────────────────────────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
              ▼                             ▼
        low risk                      high/medium risk
              │                             │
              ▼                             ▼
        流程结束                    ┌────────────────────────────────┐
                                   │  Stage 5  Search (Graphiti)    │
                                   │  混合检索: 语义向量 + BM25      │
                                   └────────────┬───────────────────┘
                                                │
                                                ▼
                                   ┌────────────────────────────────┐
                                   │  Stage 6  Dashboard            │
                                   │  意图分析 + 趋势预测 (CrewAI)   │
                                   └────────────────────────────────┘
```

## 项目结构

```
case_analysis/
├── main.py                  # 主入口，CrewAI Flow 流水线编排
├── models.py                # 共享 Pydantic 数据模型
├── consumer.py              # 事件标准化服务
├── classifier.py            # 事件分类服务 (CrewAI)
├── graphiti/
│   └── graphiti_workflow.py # Graphiti 知识图谱操作
├── providers/
│   ├── __init__.py          # LLM/Embedder 提供商
│   └── llm_provider.py      # LLM 提供商 (SiliconFlow)
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
| `NormalizedEvent` | 标准化事件 | event_id, source, raw_content, structured_data, trace_id |
| `ClassifiedEvent` | 分类结果 | event_type, risk_level, risk_score, key_entities, summary |
| `QueueMessage` | RabbitMQ 消息封装 | payload, msg_type, version, trace_id |

### graphiti/graphiti_workflow.py — Graph 服务

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

```bash
python main.py
```

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