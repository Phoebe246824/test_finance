# AGENTS.md — Sentinel Edge 金融风控智能体

## 1. 项目概述

Sentinel Edge 是面向 AMD 锐龙 AI MAX+ 赛题改造的端侧金融风控智能体。系统围绕银行零售风险事件输入 → 黑名单过滤 → AI 分类评级 → 知识图谱构建 → 混合检索 → 历史事件回捞 → 二次风险评估 → 趋势预测与人工复核闭环展开。

当前 Web 演示主线是 `backend/app/main.py` + `frontend/`。根目录 `main.py` 保留原 CrewAI Flow 终端 pipeline。

**主要技术栈：**
- Python 3.13
- CrewAI (Flow + Agent + Task + Crew) — 多 Agent 流水线编排
- Graphiti + Neo4j — 时序知识图谱
- FastAPI — 后端 API
- Vue 3 + Vite — Web 看板
- RabbitMQ (pika) — 消息队列
- Redis (redis-py) — 黑名单存储 + 事件暂存/回捞
- Pydantic v2 — 数据模型
- httpx — 异步 HTTP 客户端
- Milvus — 向量数据库（Docker Compose 依赖）
- Jina Rerank API / 本地 reranker — 事件分类与重排序
- SiliconFlow / OpenAI API — LLM 和 Embedding
- uv — 依赖管理与脚本运行器
- AMD Ryzen AI MAX+ / ROCm / Ryzen AI SDK — 参赛目标平台与本地推理加速栈

## 2. 项目结构

```
test_finance/
├── backend/                        # 当前 FastAPI 后端
│   └── app/
│       ├── main.py                 # FastAPI app 入口 (backend.app.main:app)
│       ├── api/                    # analysis/events/graph/blacklist/dashboard/system API
│       ├── services/               # 分析与 Neo4j 图谱服务
│       ├── repositories/           # SQLite 事件与复核记录访问
│       └── db/                     # SQLite 初始化
├── frontend/                       # 当前 Vue3 + Vite 前端
│   └── src/
│       ├── views/                  # Dashboard/Analyze/Events/Graph/Blacklist/SystemStatus
│       ├── components/             # 风险、图谱、趋势报告、复核组件
│       ├── api/                    # Axios API client
│       └── router/                 # Vue Router
├── main.py                         # 主入口，CrewAI Flow 流水线编排 (SentinelPipelineFlow)
├── models.py                       # 共享 Pydantic 数据模型 (NormalizedEvent, ClassifiedEvent, QueueMessage 等)
├── consumer.py                     # 事件标准化服务 (Ingestion) — RabbitMQ 消费、标准化、去重、转发
├── classifier.py                   # 事件分类服务 (Classification) — CrewAI Agent 类型分类 + 风险评估
├── dashboard.py                    # 旧版 Jinja2 看板入口；当前 Web 主线见 backend/ + frontend/
├── graph_service.py                # 知识图谱服务 (Graph) — Graphiti 客户端封装（已声明但待实现）
├── log_utils.py                    # 双输出日志系统 — Rich Console 终端输出 + RotatingFileHandler 文件日志
│
├── blacklist/                      # 黑名单系统
│   ├── __init__.py                 # 导出 BlacklistStore, BlacklistFilter
│   ├── store.py                    # 统一存储：黑名单 CRUD + 事件暂存/回捞/删除
│   └── filter.py                   # 三合一 OR 匹配器（人员/敏感词/事件相似度）
│
├── utils/                          # 工具函数
│   └── text.py                     # extract_subject_id_numbers() + extract_person_id_numbers()
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
│   ├── README.md                   # 文档导览与当前事实入口
│   ├── setup.md                    # 开发环境搭建
│   ├── commands.md                 # 常用命令
│   ├── conventions.md              # 代码规范
│   ├── architecture.md             # 架构约定
│   ├── env-vars.md                 # 环境变量说明
│   ├── testing.md                  # 测试规范
│   ├── pitfalls.md                 # 已知陷阱
│   ├── restrictions.md             # 禁止事项
│   ├── category_severity_adaptation_report.md
│   ├── dry_run_env_var_report.md
│   ├── logging_separation_report.md
│   ├── search_relevance_refactoring_report.md
│   ├── 2026第二十一届研电赛赛题指南及清单.pdf
│   ├── 2026第二十一届研电赛赛题指南及清单_节选.md
│   └── 2026第二十一届研电赛赛题指南及清单_节选.pdf
│
├── compose/                        # Docker Compose 服务定义
│   ├── milvus.yaml                 # Milvus + etcd + MinIO + Attu
│   ├── neo4j.yaml                  # Neo4j 5.26.0
│   ├── rabbitmq.yaml               # RabbitMQ 4.0.9 (management)
│   └── redis.yaml                  # Redis 7-alpine
│
├── scripts/                        # 测试与运维脚本
│   ├── sentinel_competition_demo.py # 参赛演示报告与硬件画像脚本
│   ├── reset_and_seed_blacklist.py # 重置 Redis 并写入黑名单种子数据
│   └── run_blacklist_kv_demo.py    # 15 个测试用例自动回放
│
├── docker-compose.yaml             # Compose 入口 (引用 compose/*.yaml)
├── .env.example                    # 环境变量示例
├── requirements.txt                # Python 依赖列表
└── logs/                           # 运行日志输出目录
```

**模块依赖关系（数据流）：**
```
Web 输入 → frontend/ → backend/app/main.py
           ├── backend/app/api/routes_analysis.py (分析入口)
           ├── backend/app/services/analysis_service.py (调用核心流程)
           ├── backend/app/repositories/events.py (SQLite 事件/复核记录)
           └── backend/app/api/routes_graph.py (Neo4j 图谱查询)

终端输入 → main.py (Flow 编排)
           ├── consumer.py (标准化 + 去重)
           ├── blacklist/filter.py (黑名单过滤 → PASS/STASH)
           ├── blacklist/store.py (事件暂存/回捞)
           ├── classifier.py (CrewAI 分类 + 风险评估)
           ├── graphiti/graphiti_workflow.py (Graphiti + Neo4j 构图 + 批量构图)
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
| 测试规范 | [docs/testing.md](docs/testing.md) |
| 已知陷阱与注意事项 | [docs/pitfalls.md](docs/pitfalls.md) |
| 禁止事项 | [docs/restrictions.md](docs/restrictions.md) |
| 文档与赛题材料导览 | [docs/README.md](docs/README.md) |
| AMD 赛题节选 | [docs/2026第二十一届研电赛赛题指南及清单_节选.md](docs/2026第二十一届研电赛赛题指南及清单_节选.md) |

## 7. 测试规范

见 [docs/testing.md](docs/testing.md)。
