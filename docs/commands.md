> 所属项目：[AGENTS.md](../AGENTS.md)

## 常用命令

### 安装依赖

```bash
uv sync --dev
```

### 启动原 Flow Pipeline

```bash
# 终端交互式 Pipeline（分析输入消息）
uv run python main.py

# 可选参数：指定日志目录
uv run python main.py --log-dir /path/to/logs
```

### 启动 FastAPI 后端

```bash
uv run uvicorn backend.app.main:app --reload --port 8000
```

接口文档：`http://127.0.0.1:8000/docs`。

### 启动 Vue 前端

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

浏览器访问：`http://localhost:5173`。

### 旧版 Dashboard

```bash
uv run uvicorn dashboard:create_dashboard_app --factory --reload --port 8001
```

`dashboard.py` 是旧版 Jinja2 看板入口。当前完整 Web 体验以 `backend.app.main` + `frontend/` 为准。若需要临时运行旧版看板，建议避开 FastAPI 默认的 `8000`。

### Docker 相关

```bash
# 启动所有依赖服务（Neo4j + RabbitMQ + Milvus + etcd + MinIO + Attu + Redis）
docker compose up -d

# 仅启动特定服务
docker compose up -d neo4j
docker compose up -d rabbitmq
docker compose up -d redis

# 停止并清理
docker compose down -v

# 查看服务状态
docker compose ps

# 查看日志
docker compose logs -f neo4j

# 检查 .env.example 与 Compose 插值后的端口/凭证
docker compose --env-file .env.example config
```

### Redis 调试

```bash
# 查看所有人员 KV key
docker exec redis redis-cli KEYS "person:*"

# 查看黑名单人员及命中次数
docker exec redis redis-cli ZRANGE person_blacklist 0 -1 WITHSCORES

# 查看敏感词库
docker exec redis redis-cli ZRANGE keyword_blacklist 0 -1 WITHSCORES

# 查看高危事件数量
docker exec redis redis-cli HLEN event_blacklist

# 清空所有数据
docker exec redis redis-cli FLUSHALL
```

### 测试

```bash
# 运行全部单元测试
uv run pytest tests/ -v

# 运行特定测试文件
uv run pytest tests/test_blacklist_filter.py -v

# 运行并生成覆盖率报告（需安装 pytest-cov）
uv run pytest tests/ --cov=blacklist --cov=kvstore --cov=utils
```

### Graphiti 测试

```bash
# 运行 Graphiti 功能测试（写入 + 检索）
uv run python graphiti/test.py
```

### 参赛 Demo

```bash
# 生成硬件画像和参赛演示报告
uv run python scripts/sentinel_competition_demo.py

# 依赖服务齐全时运行完整 pipeline 用例
uv run python scripts/sentinel_competition_demo.py --run-pipeline
```

### PPT 证据采集

```bash
# 不运行真实 pipeline，只生成环境画像、sidecar 合并结果、CSV 和 PNG 图表
uv run python scripts/collect_ppt_evidence.py \
  --sidecar docs/competition/evidence_sidecar.example.yaml \
  --output-dir output/competition/evidence/smoke

# 运行单条金融用例，适合先验证 finance_04 回捞链路
uv run python scripts/collect_ppt_evidence.py \
  --run-pipeline \
  --case finance_04_aml_high_risk_recall

# 在 AMD 实测环境运行完整 10 条金融用例
uv run python scripts/collect_ppt_evidence.py \
  --run-pipeline \
  --sidecar docs/competition/evidence_sidecar.example.yaml
```

### 代码质量

```bash
# Ruff 格式化
uv run ruff format .

# Ruff Lint 检查 + 自动修复
uv run ruff check --fix .

# MyPy 类型检查
uv run mypy . --ignore-missing-imports
```

注意：项目根目录已有 `pyproject.toml`，依赖通过 `uv sync --dev` 管理。ruff 规则在 `pyproject.toml` 中配置，mypy 缓存目录 `.mypy_cache` 已存在，说明之前运行过类型检查。
