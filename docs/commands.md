> 所属项目：[AGENTS.md](../AGENTS.md)

## 常用命令

### 安装依赖

```bash
uv pip install -r requirements.txt
```

### 启动系统

```bash
# 终端交互式 Pipeline（分析输入消息）
uv run python main.py

# 可选参数：指定日志目录
uv run python main.py --log-dir /path/to/logs
```

### 启动 Web 看板

```bash
# 使用 factory 模式启动 FastAPI 看板
uv run uvicorn dashboard:create_dashboard_app --factory --reload --port 8000
```

### Docker 相关

```bash
# 启动所有依赖服务（Neo4j + RabbitMQ + Milvus + etcd + MinIO + Attu + Redis）
docker compose up -d

# 仅启动特定服务
docker compose -f compose/neo4j.yaml up -d
docker compose -f compose/rabbitmq.yaml up -d
docker compose -f compose/redis.yaml up -d

# 停止并清理
docker compose down -v

# 查看服务状态
docker compose ps

# 查看日志
docker compose logs -f neo4j
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

### 代码质量

```bash
# Ruff 格式化
uv run ruff format .

# Ruff Lint 检查 + 自动修复
uv run ruff check --fix .

# MyPy 类型检查
uv run mypy . --ignore-missing-imports
```

注意：项目根目录没有 `pyproject.toml` 或 `ruff.toml` 配置文件，lint/format 使用 ruff 默认规则。mypy 缓存目录 `.mypy_cache` 已存在，说明之前运行过类型检查。
