> 所属项目：[AGENTS.md](../AGENTS.md)

## 环境变量说明

`.env` 文件中的所有配置项（详见 `.env.example`）：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `RABBITMQ_HOST` / `RABBITMQ_PORT` / `RABBITMQ_USER` / `RABBITMQ_PASSWORD` | RabbitMQ 连接 | localhost:5672 |
| `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` / `NEO4J_DATABASE` | Neo4j 连接 | bolt://localhost:7687 |
| `GRAPHITI_DRY_RUN` | 设为 true 跳过 Neo4j 写入，LLM 提取仍会执行 | false |
| `LLM_PROVIDER` | LLM 提供商 (openai / siliconflow) | openai |
| `LLM_MODEL` | 聊天模型名称 | gpt-4o |
| `LLM_API_KEY` | LLM API 密钥 | - (必填) |
| `LLM_BASE_URL` | LLM API 地址 | https://api.openai.com/v1 |
| `EMBEDDER_MODEL` | 嵌入模型名称 | BAAI/bge-m3 |
| `EMBEDDER_API_KEY` | 嵌入 API 密钥 | 未设置时 fallback 到 LLM_API_KEY |
| `EMBEDDER_API_BASE` | 嵌入 API 地址 | 未设置时 fallback 到 LLM_BASE_URL |
| `RERANKER_MODEL` | 重排序模型 | BAAI/bge-reranker-v2-m3 |
| `RERANKER_API_KEY` | 重排序 API 密钥 | 未设置时 fallback 到 LLM_API_KEY |
| `RERANKER_BASE_URL` | 重排序 API 地址 | 未设置时 fallback 到 LLM_BASE_URL |
| `SEARCH_NUM_RESULTS` | 默认搜索返回数 | 10 |
| `RISK_SEARCH_NUM_RESULTS` | 风险评估搜索返回数 | 20 |
| `SEARCH_MIN_SCORE` | 搜索相关性阈值（0.0 关闭） | 0.0 |
| `RISK_THRESHOLD` | 风险评分阈值 | 0.7 |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_PASSWORD` / `REDIS_DB` | Redis 连接（KV 暂存使用） | localhost:6379, db=0 |
| `KV_TTL_DAYS` | 暂存事件过期天数 | 90 |
| `BATCH_MAX_PER_PERSON` | 批量构图时每人最多取事件数 | 20 |
| `BLACKLIST_REDIS_DB` | 黑名单使用的 Redis DB 编号 | 1 |
| `BLACKLIST_EVENT_SIMILARITY_THRESHOLD` | 事件相似度阈值 | 0.5 |
| `BLACKLIST_PERSON_MIN_HITS` | 人员命中次数阈值 | 1 |

LLM / Embedder / Reranker 三组凭证独立，可分别配置不同的 API 地址和密钥。
