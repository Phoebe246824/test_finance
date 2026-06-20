> 所属项目：[AGENTS.md](../AGENTS.md)

## 环境变量说明

`.env` 文件中的所有配置项（详见 `.env.example`）：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `BACKEND_HOST` / `BACKEND_PORT` | 本地 FastAPI 启动地址 | 127.0.0.1:8000 |
| `VITE_API_BASE_URL` | 前端访问后端 API 的地址 | http://127.0.0.1:8000 |
| `RABBITMQ_HOST` / `RABBITMQ_PORT` / `RABBITMQ_USER` / `RABBITMQ_PASSWORD` | RabbitMQ 连接 | localhost:5672, root/pa55w0rd |
| `RABBITMQ_MANAGEMENT_PORT` | RabbitMQ Management UI 宿主机端口 | 15672 |
| `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` / `NEO4J_DATABASE` | Neo4j 连接 | bolt://localhost:7687, neo4j/pa55w0rd |
| `NEO4J_HTTP_PORT` / `NEO4J_BOLT_PORT` | Neo4j Browser / Bolt 宿主机端口 | 7474 / 7687 |
| `GRAPHITI_DRY_RUN` | 设为 true 跳过 Neo4j 写入，LLM 提取仍会执行 | false |
| `LLM_PROVIDER` | LLM 提供商 (openai / siliconflow) | openai |
| `LLM_MODEL` | 聊天模型名称 | gpt-4o |
| `LLM_API_KEY` | LLM API 密钥 | - (必填) |
| `LLM_BASE_URL` | LLM API 地址 | https://api.openai.com/v1 |
| `LLM_EXTRACT_MODEL` | 抽取档聊天模型名称；留空回退 `LLM_MODEL` | 继承 `LLM_MODEL` |
| `LLM_EXTRACT_API_KEY` | 抽取档 API 密钥；留空回退 `LLM_API_KEY` | 继承 `LLM_API_KEY` |
| `LLM_EXTRACT_BASE_URL` | 抽取档 API 地址；留空回退 `LLM_BASE_URL` | 继承 `LLM_BASE_URL` |
| `LLM_REASON_MODEL` | 研判档聊天模型名称；留空回退 `LLM_MODEL` | 继承 `LLM_MODEL` |
| `LLM_REASON_API_KEY` | 研判档 API 密钥；留空回退 `LLM_API_KEY` | 继承 `LLM_API_KEY` |
| `LLM_REASON_BASE_URL` | 研判档 API 地址；留空回退 `LLM_BASE_URL` | 继承 `LLM_BASE_URL` |
| `REASON_MAX_ATTEMPTS` | CrewAI reasoning 规划/反思最大尝试次数，仅用于研判档 Agent | 2 |
| `EMBEDDER_MODEL` | 嵌入模型名称 | BAAI/bge-m3 |
| `EMBEDDER_API_KEY` | 嵌入 API 密钥 | 未设置时 fallback 到 LLM_API_KEY |
| `EMBEDDER_API_BASE` | 嵌入 API 地址 | 未设置时 fallback 到 LLM_BASE_URL |
| `EMBEDDING_DIM` | 嵌入向量维度，需与 Milvus 暂存 collection 维度一致 | 1024 |
| `RERANKER_MODEL` | 重排序模型 | BAAI/bge-reranker-v2-m3 |
| `RERANKER_API_KEY` | 重排序 API 密钥 | 未设置时 fallback 到 LLM_API_KEY |
| `RERANKER_BASE_URL` | 重排序 API 地址 | 未设置时 fallback 到 LLM_BASE_URL |
| `SEARCH_NUM_RESULTS` | 默认搜索返回数 | 10 |
| `RISK_SEARCH_NUM_RESULTS` | 风险评估搜索返回数 | 20 |
| `SEARCH_MIN_SCORE` | 搜索相关性阈值（0.0 关闭） | 0.0 |
| `RISK_THRESHOLD` | 风险评分阈值 | 0.7 |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_PASSWORD` | Redis 连接（黑名单使用） | localhost:6379 |
| `MINIO_API_PORT` / `MINIO_CONSOLE_PORT` | MinIO API / Console 宿主机端口 | 9000 / 9001 |
| `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | MinIO 访问凭证 | minioadmin / minioadmin |
| `MILVUS_GRPC_PORT` / `MILVUS_HTTP_PORT` | Milvus gRPC / HTTP WebUI 宿主机端口 | 19530 / 9091 |
| `ATTU_PORT` | Attu 宿主机端口，默认避开 FastAPI 的 8000 | 8002 |
| `MILVUS_URI` / `MILVUS_TOKEN` | Milvus 连接（事件暂存使用） | http://localhost:19530, 空 |
| `MILVUS_STASH_COLLECTION` | Milvus 暂存 collection 名称 | stashed_events |
| `KV_TTL_DAYS` | 暂存事件过期天数 | 90 |
| `STASH_SEMANTIC_TOP_K` | Milvus 暂存语义召回数量 | 10 |
| `BATCH_MAX_PER_PERSON` | 批量构图时每人最多取事件数 | 20 |
| `BLACKLIST_REDIS_DB` | 黑名单使用的 Redis DB 编号 | 1 |
| `BLACKLIST_EVENT_SIMILARITY_THRESHOLD` | 事件相似度阈值 | 0.5 |
| `BLACKLIST_PERSON_MIN_HITS` | 人员命中次数阈值 | 1 |

LLM / Embedder / Reranker 三组凭证独立，可分别配置不同的 API 地址和密钥。`LLM_EXTRACT_*` 与 `LLM_REASON_*` 是聊天 LLM 的工作流分档：留空时复用基础 `LLM_*`，需要多模型常驻时分别指向快抽取模型和高质量研判模型。
