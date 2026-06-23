# 测试规范

> 所属项目：[AGENTS.md](../AGENTS.md)

## 测试分层

当前项目测试分为三类：

1. **纯函数/单元测试**：文本抽取、风险评分、黑名单匹配、脚本参数等，不依赖 Docker 服务。
2. **集成测试**：默认 Web 测试使用 Milvus store fake；连接真实 Milvus/Neo4j/LLM 的测试需显式启动依赖服务。
3. **演示验证**：面向参赛 Demo，验证硬件画像、金融样例和端到端报告生成。

## 常用命令

```bash
# 全量测试
uv run pytest tests/ -v

# 快速单元测试
uv run pytest tests/test_extract_subject_id_numbers.py tests/test_risk_scoring.py -q

# Milvus 默认存储相关测试
uv run pytest tests/test_milvus_store_base.py tests/test_events_store.py tests/test_blacklist_milvus_stores.py tests/test_blacklist_filter.py tests/test_default_milvus_api.py tests/test_default_milvus_runtime.py -q

# 重置脚本测试
uv run pytest tests/test_reset_and_seed_blacklist.py -q
```

## 依赖服务测试

涉及真实 Milvus、Neo4j 的测试会读取 `.env` 或 `.env.example` 中的连接配置。运行前按需启动：

```bash
docker compose up -d
docker compose --profile vector up -d attu
docker compose ps
```

默认端口：

```text
Milvus: 19530 / 9091
Neo4j: 7474 / 7687
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
