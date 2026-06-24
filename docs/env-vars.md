> 所属项目：[AGENTS.md](../AGENTS.md)

## 环境变量说明

`.env` 文件中的所有配置项（详见 `.env.example`）：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `BACKEND_HOST` / `BACKEND_PORT` | 本地 FastAPI 启动地址 | 127.0.0.1:8000 |
| `VITE_API_BASE_URL` | 前端访问后端 API 的地址 | http://127.0.0.1:8000 |
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
| `REASON_MAX_STEPS` | CrewAI reasoning 单次规划最大步骤数，仅用于研判档 Agent | 4 |
| `EMBEDDER_MODEL` | 嵌入模型名称 | BAAI/bge-m3 |
| `EMBEDDER_API_KEY` | 嵌入 API 密钥 | 未设置时 fallback 到 LLM_API_KEY |
| `EMBEDDER_API_BASE` | 嵌入 API 地址 | 未设置时 fallback 到 LLM_BASE_URL |
| `EMBEDDING_DIM` | embedding 维度，需与 `EMBEDDER_MODEL` 输出一致 | 1024 |
| `RERANKER_MODEL` | 重排序模型 | BAAI/bge-reranker-v2-m3 |
| `RERANKER_API_KEY` | 重排序 API 密钥 | 未设置时 fallback 到 LLM_API_KEY |
| `RERANKER_BASE_URL` | 重排序 API 地址 | 未设置时 fallback 到 LLM_BASE_URL |
| `SEARCH_NUM_RESULTS` | 默认搜索返回数 | 10 |
| `RISK_SEARCH_NUM_RESULTS` | 风险评估搜索返回数 | 20 |
| `SEARCH_MIN_SCORE` | 搜索相关性阈值（0.0 关闭） | 0.0 |
| `RISK_THRESHOLD` | 风险评分阈值 | 0.7 |
| `RAGFLOW_ENABLED` | 是否启用可选 RAGFlow 金融知识检索 | `false` |
| `RAGFLOW_BASE_URL` | RAGFlow API 地址 | `http://127.0.0.1:9380` |
| `RAGFLOW_API_KEY` | RAGFlow API Key | 空 |
| `RAGFLOW_DATASET_ID` | 单个 RAGFlow dataset ID | 空 |
| `RAGFLOW_DATASET_IDS` | 多个 RAGFlow dataset ID，逗号分隔；优先级高于 `RAGFLOW_DATASET_ID` | 空 |
| `RAGFLOW_TOP_K` | RAGFlow 检索候选数 | `5` |
| `RAGFLOW_SIMILARITY_THRESHOLD` | RAGFlow 相似度阈值 | `0.2` |
| `RAGFLOW_VECTOR_SIMILARITY_WEIGHT` | RAGFlow 向量相似度权重 | `0.7` |
| `RAGFLOW_TIMEOUT_SECONDS` | RAGFlow HTTP 请求超时秒数 | `15` |
| `RAGFLOW_MAX_CONTEXT_CHARS` | 注入 Agent prompt 的 RAGFlow 知识上下文最大字符数 | `4000` |
| `RAGFLOW_FAIL_OPEN` | RAGFlow HTTP/JSON envelope 失败时是否继续原流程；`false` 时抛出错误 | `true` |
| `RAGFLOW_IMAGE` | Docker Compose RAGFlow 镜像 | `infiniflow/ragflow:v0.26.1` |
| `RAGFLOW_WEB_PORT` / `RAGFLOW_API_PORT` | RAGFlow Web / API 宿主机端口，仅绑定 `127.0.0.1` | `8088` / `9380` |
| `RAGFLOW_MYSQL_PASSWORD` / `RAGFLOW_REDIS_PASSWORD` / `RAGFLOW_MINIO_PASSWORD` / `RAGFLOW_ELASTIC_PASSWORD` | RAGFlow Docker profile 本地依赖服务密码；共享环境启动前必须替换示例值 | `change-me-*` |
| `RAGFLOW_MINIO_USER` | RAGFlow Docker profile MinIO 用户名 | `ragflow-local` |
| `MINIO_API_PORT` / `MINIO_CONSOLE_PORT` | MinIO API / Console 宿主机端口 | 9000 / 9001 |
| `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | MinIO 访问凭证 | minioadmin / minioadmin |
| `MILVUS_GRPC_PORT` / `MILVUS_HTTP_PORT` | Milvus gRPC / HTTP WebUI 宿主机端口 | 19530 / 9091 |
| `ATTU_PORT` | Attu 宿主机端口，默认避开 FastAPI 的 8000 | 8002 |
| `MILVUS_URI` | Milvus SDK 连接地址 | `http://127.0.0.1:19530` |
| `MILVUS_TOKEN` | Milvus 鉴权 token，未启用鉴权时为空 | 空 |
| `MILVUS_STASH_COLLECTION` | 统一事件 collection 名称 | `events` |
| `KV_TTL_DAYS` | 暂存事件过期天数 | 90 |
| `STASH_SEMANTIC_TOP_K` | 高风险补图前语义召回候选数 | `10` |
| `STASH_RERANK_ENABLED` | 是否启用召回候选重排序 | `true` |
| `STASH_RERANK_MIN_SCORE` | 召回候选进入补图的最低重排序分数 | `0.7` |
| `BATCH_MAX_PER_PERSON` | 每个人员 ID 的同人历史召回上限 | `20` |
| `BLACKLIST_EVENT_SIMILARITY_THRESHOLD` | 事件相似度阈值 | 0.5 |
| `BLACKLIST_PERSON_MIN_HITS` | 人员命中次数阈值 | 1 |

LLM / Embedder / Reranker 三组凭证独立，可分别配置不同的 API 地址和密钥。`LLM_EXTRACT_*` 与 `LLM_REASON_*` 是聊天 LLM 的工作流分档：留空时复用基础 `LLM_*`，需要多模型常驻时分别指向快抽取模型和高质量研判模型。`REASON_MAX_ATTEMPTS` 控制规划/反思尝试轮数，`REASON_MAX_STEPS` 控制每次规划最多包含的步骤数。

`DATABASE_URL`、`BLACKLIST_BACKEND`、`STASH_BACKEND`、`REDIS_*`、`RABBITMQ_*` 不再参与默认运行路径。
