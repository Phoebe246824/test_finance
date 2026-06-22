> 所属项目：[AGENTS.md](../AGENTS.md)

## 架构约定

### 当前应用形态

项目现在同时保留两条入口：

- **Web 应用主线**：`backend/app/main.py` 提供 FastAPI API，`frontend/` 提供 Vue3 看板，是当前演示和开发的主要入口。
- **原 Flow Pipeline**：`main.py` 保留 CrewAI Flow 终端 pipeline，用于验证标准化、黑名单、构图、检索、风险评估和趋势预测链路。

两条入口共享 `blacklist/`、`graphiti/`、`trend_prediction/`、`providers/`、`models.py` 等核心模块。文档或任务若提到“启动 Web”，默认指 FastAPI + Vue3，而不是旧的 `dashboard.py`。

### 分层规则

```
Web 入口
  ├── backend/app/main.py — FastAPI 应用入口
  ├── backend/app/api/ — analysis/events/graph/blacklist/dashboard/system API
  ├── backend/app/services/ — 分析与图谱服务封装
  ├── backend/app/repositories/ — SQLite 事件与复核记录访问
  └── frontend/src/ — Vue3 页面、组件、API client 与状态

原 pipeline 入口 (main.py)
  └── Flow 编排 — SentinelPipelineFlow 串联所有 Stage
        ├── 黑名单过滤 (新增) — blacklist/filter.py 三合一 OR 匹配
        ├── SQLite 暂存 — blacklist/sqlite_stash.py 默认同人历史事件池
        ├── Milvus 暂存 — blacklist/milvus_stash.py 可选向量语义相关事件池
        ├── Stage 1: classification — CrewAI Agent 分类
        ├── Stage 2: single_graph_build — 当前事件单条构图
        ├── Stage 3: search_first_risk_context — 首次风险上下文检索
        ├── Stage 4: first_risk_evaluation — 首次风险评估
        ├── Stage 5: route_post_first_risk — 阈值路由（complete/batch_graph）
        ├── Stage 6: batch_graph_build_from_stash — 暂存回捞历史事件补图
        ├── Stage 7: search_second_risk_context + second_risk_evaluation_stage
        └── Stage 8: dashboard — 意图分析与趋势预测
```

- **backend/app/main.py**: 当前 FastAPI 后端入口，注册 `/api/*` 路由并初始化本地 SQLite
- **frontend/**: 当前 Vue3 前端，包含风控总览、分析工作台、事件库、人物图谱、黑名单管理、系统状态页面
- **main.py**: 原 CrewAI Flow 编排和流程控制入口，不再承担 Web 看板职责
- **blacklist/**: 黑名单系统，`sqlite_store.py` 和 `sqlite_stash.py` 是 Web 默认存储；`store.py`/`milvus_stash.py` 保留 Redis/Milvus 可选适配；`filter.py` 执行人员/敏感词/事件相似度三合一 OR 匹配
- **consumer.py**: 事件标准化和去重逻辑，所有函数为纯函数或操作全局缓存
- **graphiti/graphiti_workflow.py**: Graphiti 客户端生命周期管理 + Episode 写入 + 混合检索 + `batch_add_to_graph()` 批量构图
- **trend_prediction/**: 自适应提示词和分类逻辑，通过适配器模式支持多领域
- **providers/**: LLM / Embedder 实例工厂，统一管理外部 API 连接
- **utils/text.py**: 共享文本工具函数（如 `extract_subject_id_numbers`），避免模块间循环导入

### 模块边界

- `models.py` 定义所有共享数据模型，其他模块通过 `from models import ...` 引用
- `log_utils.py` 提供双输出系统：`print_*` 函数用于终端（面向用户），`get_logger()` 用于文件日志（面向开发者）
- `graphiti_core/` 是从 Graphiti 项目嵌入的本地副本，**不应直接修改**（除非明确知晓影响范围）
- `trend_prediction/adapters/` 使用适配器模式：每个领域一个适配器类，继承 `BaseAdapter`，新增领域需同步注册到 `adapters/__init__.py`
- Web 默认黑名单和暂存落 SQLite，减少本地启动依赖；Redis/Milvus 仅在显式设置 `BLACKLIST_BACKEND=redis` / `STASH_BACKEND=milvus` 时使用
- `utils/` 存放跨模块共享的工具函数，避免循环导入（如 `extract_subject_id_numbers` 从 `main.py` 迁出至此）

### API 设计约定

- 当前 FastAPI 应用入口为 `backend.app.main:app`，路由统一挂在 `/api/*`
- `dashboard.py` 仍可作为旧版 Jinja2 看板运行，但不是当前 Web 主线
- 消息队列相关代码保留在原 pipeline/consumer 体系中，消息格式为 `QueueMessage` (Pydantic 模型)
- 前端 API client 统一从 `frontend/src/api/http.ts` 读取 `VITE_API_BASE_URL`

### 状态管理约定

- 全局去重缓存：`consumer._PROCESSED_EVENTS` (内存 dict + TTL)，线程安全通过 `threading.Lock`
- 全局 LLM 实例追踪：`providers.llm_provider._ACTIVE_LLMS`，用于优雅关闭时释放连接
- 统计数据：`consumer._STATS`，通过 `threading.Lock` 保护并发访问
- SQLite 黑名单：`blacklist_items` 表保存人员、关键词和事件样本，是 Web/API 默认匹配源
- SQLite 暂存：`stashed_events` 表保存未命中黑名单事件，支持同人员 ID 回捞和已构图标记
- Redis 黑名单：`person_blacklist`（SortedSet）、`keyword_blacklist`（SortedSet）、`event_blacklist`（Hash），仅 legacy 后端启用时通过 `BlacklistStore` 封装
- Milvus 暂存：`stashed_events` collection，仅向量增强后端启用时支持语义相似召回
