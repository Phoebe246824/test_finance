> 所属项目：[AGENTS.md](../AGENTS.md)

## 架构约定

### 分层规则

```
入口层 (main.py)
  └── Flow 编排 — SentinelPipelineFlow 串联所有 Stage，不包含业务逻辑
        ├── 黑名单过滤 (新增) — blacklist/filter.py 三合一 OR 匹配
        ├── KV 暂存 (新增) — kvstore/redis_store.py 人员→事件链表
        ├── Stage 1: consumer.py — 事件标准化 + 去重（纯函数，可独立测试）
        ├── Stage 2: classifier.py — CrewAI Agent 分类 + 风险评估
        ├── Stage 3: graphiti/graphiti_workflow.py — 知识图谱写入 + 批量构图
        ├── Stage 4: graphiti/graphiti_workflow.py — 混合检索
        └── Stage 5: trend_prediction/ — Jina Rerank 分类 + 意图/趋势分析
```

- **main.py**: 只负责 Flow 编排和流程控制，不包含具体的业务逻辑实现
- **blacklist/**: 黑名单系统，`manager.py` 负责 CRUD，`filter.py` 执行人员/敏感词/事件相似度三合一 OR 匹配
- **kvstore/**: Redis KV 暂存，方案 A（一人一链表），负责暂存未命中黑名单的事件
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
- `blacklist/` 和 `kvstore/` 通过 `redis.asyncio.Redis` 通信，不直接操作 Redis key 字符串（统一封装在 manager/store 中）
- `utils/` 存放跨模块共享的工具函数，避免循环导入（如 `extract_subject_id_numbers` 从 `main.py` 迁出至此）

### API 设计约定

- FastAPI 应用使用 **factory 模式**：`create_app(config)` / `create_dashboard_app(config)`
- 所有服务间通信通过 RabbitMQ 消息队列，消息格式为 `QueueMessage` (Pydantic 模型)
- 路由：`/api/` 前缀为 JSON API，`/` 为 HTML 页面

### 状态管理约定

- 全局去重缓存：`consumer._PROCESSED_EVENTS` (内存 dict + TTL)，线程安全通过 `threading.Lock`
- 全局 LLM 实例追踪：`providers.llm_provider._ACTIVE_LLMS`，用于优雅关闭时释放连接
- 统计数据：`consumer._STATS`，通过 `threading.Lock` 保护并发访问
- Redis 黑名单：`person_blacklist`（SortedSet）、`keyword_blacklist`（SortedSet）、`event_blacklist`（Hash），通过 `BlacklistManager` 封装
- Redis KV 暂存：`person:<id_number>` 链表，通过 `EventKVStore` 封装，TTL 默认 90 天
- Redis 连接生命周期：在 `run_flow()` 中创建，`try/finally` 确保 `aclose()` 始终执行
