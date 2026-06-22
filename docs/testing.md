# 测试规范

> 所属项目：[AGENTS.md](../AGENTS.md)

## 测试分层

当前项目测试分为三类：

1. **纯函数/单元测试**：文本抽取、风险评分、黑名单匹配、脚本参数等，不依赖 Docker 服务。
2. **集成测试**：默认 Web/SQLite 测试不需要 Redis/Milvus；涉及 Neo4j、Milvus、Redis 的 legacy/enhanced 测试需显式启动对应 profile。
3. **演示验证**：面向参赛 Demo，验证硬件画像、金融样例和端到端报告生成。

## 常用命令

```bash
# 全量测试
uv run pytest tests/ -v

# 快速单元测试
uv run pytest tests/test_extract_subject_id_numbers.py tests/test_risk_scoring.py -q

# 黑名单和默认 SQLite 暂存相关测试
uv run pytest tests/test_blacklist_filter.py tests/test_blacklist_manager.py tests/test_sqlite_blacklist_store.py tests/test_sqlite_stash_store.py -q

# 重置脚本测试
uv run pytest tests/test_reset_and_seed_blacklist.py -q
```

## 依赖服务测试

涉及 Milvus、Neo4j、Redis 的测试会读取 `.env` 或 `.env.example` 中的连接配置。运行前按需启动：

```bash
docker compose up -d
docker compose --profile legacy-flow up -d redis rabbitmq
docker compose --profile vector up -d milvus attu
docker compose ps
```

默认端口：

```text
Redis: 6379
Milvus: 19530 / 9091
Neo4j: 7474 / 7687
RabbitMQ: 5672 / 15672
Attu: 8002
FastAPI: 8000
```

若测试直接连接 `localhost:19530` 失败，通常是 Milvus 未启动或还未健康。先检查 `docker compose ps` 和 `docker compose logs -f milvus`。

## 参赛演示验证

```bash
# 仅生成硬件画像和报告
uv run python scripts/sentinel_competition_demo.py

# 依赖服务齐全时运行完整 pipeline
uv run python scripts/sentinel_competition_demo.py --run-pipeline
```

参赛验证结果会写入 `output/competition/` 或 `logs/`。不要提交运行日志、缓存和真实敏感数据。
