# AGENTS.md — Sentinel 舆情分析系统

## 1. 项目概述

Sentinel 是一个多源事件实时接入 → AI 分类评级 → 知识图谱构建 → 混合检索 → 意图分析 → 趋势预测的舆情分析系统。

**主要技术栈：**
- Python 3.13
- CrewAI (Flow + Agent + Task + Crew) — 多 Agent 流水线编排
- Graphiti + Neo4j — 时序知识图谱
- FastAPI + Jinja2 — Web 看板
- RabbitMQ (pika) — 消息队列
- Pydantic v2 — 数据模型
- httpx — 异步 HTTP 客户端
- Milvus — 向量数据库（Docker Compose 依赖）
- Jina Rerank API — 事件分类与重排序
- SiliconFlow / OpenAI API — LLM 和 Embedding
- uv — 依赖管理与脚本运行器

## 2. 项目结构

```
test_Sentinel/
├── main.py                         # 主入口，CrewAI Flow 流水线编排 (SentinelPipelineFlow)
├── models.py                       # 共享 Pydantic 数据模型 (NormalizedEvent, ClassifiedEvent, QueueMessage 等)
├── consumer.py                     # 事件标准化服务 (Ingestion) — RabbitMQ 消费、标准化、去重、转发
├── classifier.py                   # 事件分类服务 (Classification) — CrewAI Agent 类型分类 + 风险评估
├── dashboard.py                    # Web 看板服务 (FastAPI) — 事件列表、统计、风险分布 API
├── graph_service.py                # 知识图谱服务 (Graph) — Graphiti 客户端封装（已声明但待实现）
├── log_utils.py                    # 双输出日志系统 — Rich Console 终端输出 + RotatingFileHandler 文件日志
│
├── graphiti/                       # Graphiti 知识图谱操作层
│   ├── graphiti_workflow.py        # 核心：客户端初始化、Episode 写入、混合检索、重排序
│   └── test.py                     # Graphiti 功能测试脚本（写入 + 检索验证）
│
├── graphiti_core/                  # Graphiti 内核库（本地嵌入副本，非 pip 包）
│   ├── graphiti.py                 # Graphiti 主类
│   ├── driver/                     # 多数据库驱动 (Neo4j / FalkorDB / Kuzu / Neptune)
│   ├── cross_encoder/              # 重排序客户端 (Jina / BGE / OpenAI / Gemini)
│   ├── llm_client/                 # LLM 客户端 (OpenAI / Anthropic / Gemini / Groq / Azure)
│   ├── embedder/                   # Embedder (OpenAI / Azure / Gemini / Voyage)
│   ├── search/                     # 搜索实现 (混合检索、RRF 融合)
│   ├── prompts/                    # LLM 提示词模板 (实体提取、关系提取、去重等)
│   └── utils/                      # 工具函数 (批量写入、内容分块、节点操作、社区检测)
│
├── trend_prediction/               # 事件分类与自适应提示词模块
│   ├── __init__.py                 # 公共 API 导出 (EventClassifier, PROMPTS_DIR)
│   ├── classifier.py               # Jina Rerank 事件分类器 (7 类别 + 4 严重度)
│   ├── task_templates.py            # 自适应任务模板工厂 (意图分析 / 趋势预测)
│   ├── adapters/                   # 7 个领域适配器 + 基类
│   │   ├── base.py                 # 基类 BaseAdapter
│   │   ├── intl_politics.py        # 国际政治
│   │   ├── tech.py                 # 科技
│   │   ├── economy.py              # 经济
│   │   ├── society.py              # 社会/文化
│   │   ├── public_health.py        # 公共卫生
│   │   ├── energy.py               # 能源
│   │   └── finance.py              # 金融
│   └── prompts/                    # 兜底提示词模板 (.md 文件)
│       ├── intent_analysis.md
│       └── trend_prediction.md
│
├── providers/                      # LLM / Embedder 提供商封装
│   ├── __init__.py                 # 公共导出
│   ├── llm_provider.py             # LLM 实例管理 (get_llm / get_siliconflow_llm / close_all_llms)
│   └── embedder_provider.py        # Embedder 配置 (get_embedder)
│
├── docs/                           # 项目文档目录
│   ├── setup.md                    # 开发环境搭建
│   ├── commands.md                 # 常用命令
│   ├── conventions.md              # 代码规范
│   ├── architecture.md             # 架构约定
│   ├── env-vars.md                 # 环境变量说明
│   ├── pitfalls.md                 # 已知陷阱
│   ├── restrictions.md             # 禁止事项
│   ├── category_severity_adaptation_report.md
│   ├── dry_run_env_var_report.md
│   ├── logging_separation_report.md
│   └── search_relevance_refactoring_report.md
│
├── compose/                        # Docker Compose 服务定义
│   ├── milvus.yaml                 # Milvus + etcd + MinIO + Attu
│   ├── neo4j.yaml                  # Neo4j 5.26.0
│   └── rabbitmq.yaml               # RabbitMQ 4.0.9 (management)
│
├── docker-compose.yaml             # Compose 入口 (引用 compose/*.yaml)
├── .env.example                    # 环境变量示例
├── requirements.txt                # Python 依赖列表
└── logs/                           # 运行日志输出目录
```

**模块依赖关系（数据流）：**
```
用户输入 → main.py (Flow 编排)
           ├── consumer.py (标准化 + 去重)
           ├── classifier.py (CrewAI 分类 + 风险评估)
           ├── graphiti/graphiti_workflow.py (Graphiti + Neo4j 构图)
           ├── graphiti/graphiti_workflow.py (混合检索 + 重排序)
           └── trend_prediction/ (Jina Rerank 分类 + 领域适配器 + 意图/趋势分析)
```

## 3. 快速索引

| 你想了解的内容 | 文档 |
|---|---|
| 如何搭建开发环境 | [docs/setup.md](docs/setup.md) |
| 常用命令 | [docs/commands.md](docs/commands.md) |
| 代码规范与提交格式 | [docs/conventions.md](docs/conventions.md) |
| 架构设计与模块边界 | [docs/architecture.md](docs/architecture.md) |
| 所有环境变量 | [docs/env-vars.md](docs/env-vars.md) |
| 已知陷阱与注意事项 | [docs/pitfalls.md](docs/pitfalls.md) |
| 禁止事项 | [docs/restrictions.md](docs/restrictions.md) |

## 7. 测试规范

见 [docs/testing.md](docs/testing.md)（待建立，参见 TODO 标注）
