> 所属项目：[AGENTS.md](../AGENTS.md)

## 注意事项 / 已知陷阱

### 环境与平台

- **Windows 路径问题**：`graphiti/test.py` 中包含 macOS 硬编码路径 `sys.path.insert(0, "/Users/phoebe/project/zxy/test_Sentinel")`，在 Windows 上运行需修改
- **Python 版本**：项目使用 Python 3.13，部分依赖（如 `pika`）需要确认兼容性
- **Docker 资源**：Milvus compose 包含 4 个容器（etcd + MinIO + Milvus + Attu），请确保 Docker 分配了至少 8GB 内存

### 依赖与架构

- **`graphiti_core/` 是本地嵌入副本**：不是通过 pip 安装的 `graphiti-core` 包，而是直接嵌入在项目中的代码。这意味着 Graphiti 升级需要手动同步
- **三组 API 凭证独立**：LLM、Embedder、Reranker 使用三组独立的 API Key / Base URL 配置，未设置时逐级 fallback（Reranker → Embedder → LLM）
- **重排序使用 Jina Rerank API**：Graphiti 的 cross_encoder 通过 Jina Reranker 客户端调用 Jina API 进行重排序，不是在本地运行模型

### 日志系统

- **双输出系统**：`print_*` 函数使用 Rich Console 输出到终端（彩色），`logging.getLogger()` 输出到 RotatingFileHandler 文件日志
- **文件日志自动轮转**：单个日志文件最大 5MB，保留 3 个备份
- **第三方日志静默**：`neo4j`、`httpx`、`urllib3`、`httpcore`、`crewai`、`asyncio` 的日志级别被设为 WARNING

### Flow 执行注意事项

- **`SentinelPipelineFlow.kickoff()` 是同步方法**，但内部包含异步操作（通过 `asyncio.run()` 或直接 await）
- **Graphiti 客户端在每个 Stage 中独立创建和关闭**，不跨 Stage 共享，确保连接不泄漏
- **风险评估路由**：`risk_score > RISK_THRESHOLD` 进入二次评估（含图谱检索），`risk_level == LOW` 直接结束流程
- **`GRAPHITI_DRY_RUN=true`** 时跳过 Neo4j 写入，但 LLM 实体/关系提取仍会执行，用于调试提取效果

### 搜索与检索

- **混合搜索默认使用 `COMBINED_HYBRID_SEARCH_CROSS_ENCODER`**（语义向量 + BM25 + BFS 图遍历 → Cross-Encoder 重排序）
- **主体 Episode 过滤**：搜索时会自动从 `event.raw_content` 提取 `id_number`（如 P01），并只保留包含该主体的 Episode 及其关联结果
- **搜索超时**：`hybrid_search()` 设置了 20 秒超时，超时不会抛异常而是返回空结果

### 分类器注意事项

- **Jina Rerank 分类需要 API Key**：`EventClassifier` 默认 `use_rerank=True`，但没有 API Key 时会自动回退到关键词匹配
- **回退关键词匹配精度有限**：关键词列表硬编码在 `trend_prediction/classifier.py` 中，覆盖 7 类别约 140 个关键词 + 4 级严重度约 48 个关键词
- **合并分类**：`_rerank_classify_combined()` 通过一次 API 调用同时完成类别和严重度分类，使用 `CATEGORY:` / `SEVERITY:` 前缀区分

### 消息队列

- **`pika` 是惰性导入**：`consumer.py` 中 `pika` 是可选依赖，未安装时不影响 `normalize_event()` 等纯函数使用
- **RabbitMQ 初始化数据会持久化**：`.env.example` 与 Compose 默认使用 `root/pa55w0rd` 和 `/` vhost。若本地已有旧的 `compose/volumes/rabbitmq/data`，修改 `.env` 后需要清理旧数据目录或重建容器数据，RabbitMQ 才会重新初始化默认用户。
