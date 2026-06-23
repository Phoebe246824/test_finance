# Milvus 存储统一化设计

日期：2026-06-23

## 概述

将系统存储从多后端（SQLite + Redis + Milvus）统一为单一 Milvus 存储，同时删除 Redis 和 RabbitMQ 依赖，简化系统架构。

## 目标

1. 移除 SQLite 依赖，全量数据存储到 Milvus
2. 移除 Redis 依赖，黑名单存储迁移到 Milvus
3. 移除 RabbitMQ 依赖（保留代码标记废弃）
4. 保持语义召回能力完整
5. 减少服务依赖（7 容器 → 4 容器）

## 存储架构

### 变更前

```
┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐
│ SQLite  │  │  Redis  │  │ Milvus  │  │  Neo4j  │
│ 事件结果 │  │ 黑名单   │  │ 事件暂存 │  │ 知识图谱 │
└─────────┘  └─────────┘  └─────────┘  └─────────┘
```

### 变更后

```
┌──────────────────────────────────┐  ┌─────────┐
│             Milvus               │  │  Neo4j  │
│ ┌────────────┐ ┌───────────────┐ │  │ 知识图谱 │
│ │ 事件全量    │ │ 黑名单        │ │  └─────────┘
│ │ events     │ │ - persons     │ │
│ │            │ │ - keywords    │ │
│ │ 审核日志    │ │ - samples     │ │
│ │ reviews    │ └───────────────┘ │
│ └────────────┘                   │
└──────────────────────────────────┘
```

### 服务依赖变更

| 服务 | 变更前 | 变更后 |
|-----|-------|-------|
| Neo4j | 必选 | 必选（不变） |
| Milvus | 必选 | 必选（不变） |
| SQLite | 必选 | 删除 |
| Redis | 必选 | 删除 |
| RabbitMQ | 必选 | 删除 |

### Docker 容器

```
变更前: 7 容器
  Neo4j(1) + Milvus(4) + Redis(1) + RabbitMQ(1)

变更后: 4 容器
  Neo4j(1) + Milvus(3, Attu 可选)
```

## Milvus Collection 结构

### Collection 1: `events` — 全量事件存储

```python
{
    # 主键与标识
    "event_id": str,              # 主键
    "content_hash": str,          # 内容去重哈希
    
    # 原始数据
    "raw_content": str,           # 原始文本
    "title": str,                 # 事件标题
    "source": str,                # 来源 (news/social/report/...)
    "embedding": list[float],     # 文本向量 (1024维)
    
    # 关联数据
    "person_ids": list[str],      # 关联人员身份证号
    
    # 黑名单匹配结果
    "status": str,                # stashed/processed/blacklisted
    "blacklist_decision": str,    # hit/miss
    "matched_persons": str,       # JSON: 命中的人员
    "matched_keywords": str,      # JSON: 命中的关键词
    "event_similarity": str,      # JSON: 事件相似度匹配结果
    
    # 风险分析结果
    "risk_level": str,            # high/medium/low
    "risk_score": float,          # 0.0-1.0
    "event_type": str,            # 分类结果
    "reasoning": str,             # 风险评估理由
    "dimension_scores": str,      # JSON: 各维度评分
    "trend_report": str,          # JSON: 趋势预测报告
    
    # 图谱状态
    "is_graph_built": bool,       # 是否已构图
    
    # 时间戳
    "created_at": str,            # ISO 格式
    "updated_at": str,
    "expire_at": str,             # TTL 过期时间（可选）
}
```

### Collection 2: `review_actions` — 审核日志

```python
{
    "action_id": str,             # 主键 (UUID)
    "event_id": str,              # 关联事件
    "action_type": str,           # approve/reject/escalate/comment
    "comment": str,               # 审核备注
    "created_at": str,
}
```

### Collection 3: `blacklist_persons` — 人员黑名单

```python
{
    "person_id": str,             # 主键 (身份证号，大写)
    "summary": str,               # 简述
    "description": str,           # 详细描述
    "hit_count": int,             # 命中次数统计
    "enabled": bool,              # 是否启用
    "created_at": str,
    "updated_at": str,
}
```

### Collection 4: `blacklist_keywords` — 关键词黑名单

```python
{
    "keyword_id": str,            # 主键 (关键词本身或 hash)
    "keyword": str,               # 关键词文本
    "summary": str,
    "hit_count": int,
    "enabled": bool,
    "created_at": str,
    "updated_at": str,
}
```

### Collection 5: `blacklist_event_samples` — 事件样本黑名单

```python
{
    "sample_id": str,             # 主键
    "summary": str,               # 事件摘要
    "description": str,           # 详细描述
    "embedding": list[float],     # 文本向量（用于语义匹配）
    "enabled": bool,
    "created_at": str,
    "updated_at": str,
}
```

## 代码模块结构

### 目录结构

```
blacklist/
├── __init__.py                    # 更新导出
├── filter.py                      # 重构：调用各 store
├── milvus_client.py               # 新建：共享 Milvus 客户端工厂
├── stores/                        # 新建目录
│   ├── __init__.py
│   ├── base.py                    # 基类：共享连接和通用方法
│   ├── events_store.py            # 全量事件存储
│   ├── review_actions_store.py    # 审核日志存储
│   ├── persons_store.py           # 人员黑名单
│   ├── keywords_store.py          # 关键词黑名单
│   └── event_samples_store.py     # 事件样本黑名单

backend/app/
├── main.py                        # 重构：移除 db.session 初始化，改用 stores
├── db/                            # 删除整个目录（仅含 session.py）
├── repositories/
│   └── events.py                  # 重构：移除 db.session 依赖，改用 events_store
├── core/
│   └── config.py                  # 移除 SQLite 配置
└── api/
    ├── routes_blacklist.py        # 重构：调用 stores
    ├── routes_events.py           # 重构：调用 stores
    ├── routes_system.py           # 重构：Milvus 健康检查
    ├── routes_dashboard.py        # 重构：调用 stores
    └── routes_graph.py            # 重构：依赖的 EventRepository 改用 events_store（Neo4j 部分不变）

compose/
├── milvus.yaml                    # 移除 profile 限制
├── neo4j.yaml                     # 不变
├── redis.yaml                     # 保留文件（不在 docker-compose.yaml 中引用）
└── rabbitmq.yaml                  # 保留文件（不在 docker-compose.yaml 中引用）
```

### 模块职责

| 模块 | 职责 |
|------|------|
| `milvus_client.py` | 创建和管理 Milvus 客户端实例，连接配置 |
| `stores/base.py` | Store 基类，提供 collection 初始化、通用 CRUD |
| `stores/events_store.py` | 事件全量存储、语义检索、状态更新 |
| `stores/review_actions_store.py` | 审核日志 CRUD |
| `stores/persons_store.py` | 人员黑名单 CRUD、精确查询 |
| `stores/keywords_store.py` | 关键词黑名单 CRUD、全量查询 |
| `stores/event_samples_store.py` | 事件样本 CRUD、向量相似度匹配 |
| `filter.py` | 黑名单三合一 OR 匹配逻辑（调用各 store） |

> `backend/app/repositories/events.py` 的 `EventRepository` 当前封装 SQLite 查询，迁移后改为薄封装委托 `events_store`/`review_actions_store`（或直接由路由调用 stores 后删除该 repository）。`routes_graph.py` 经它读取事件，故二者需同批改造。

## 删除的文件

### SQLite 相关

删除：
- `backend/app/db/session.py`
- `backend/app/db/`（整个目录，仅含上面一个文件，无 `__init__.py`）

改写（不删除，但需移除 SQLite 依赖）：
- `backend/app/repositories/events.py` — 顶层 `from backend.app.db.session import get_connection` 改为调用 `events_store` / `review_actions_store`
- `backend/app/main.py` — 移除 db.session 的启动初始化逻辑

> ⚠️ db.session 依赖链：实际有 7 处 import `backend.app.db.session` —— 4 个 routes（blacklist/events/system/dashboard）、`repositories/events.py`、`backend/app/main.py`、`tests/test_default_sqlite_runtime.py`。删除 `session.py` 前必须先改完前 6 处（测试见下文删除），否则 import 即崩。`routes_graph.py` 本身不直接 import db.session，但依赖 `EventRepository`，故随 `repositories/events.py` 一并改造。

### Redis 相关

- `blacklist/store.py`

### PR 新增的 SQLite 实现

- `blacklist/sqlite_store.py`
- `blacklist/sqlite_stash.py`
- `blacklist/runtime_storage.py`

### 旧的 Milvus stash

- `blacklist/milvus_stash.py`（合并到 events_store）
  - `stash_event()` → `events_store.upsert_event()`
  - `fetch_related_events()` → `events_store.fetch_related_events()`（保留语义召回逻辑）
  - `mark_events_graph_built()` → `events_store.mark_graph_built()`

### 测试文件

- `tests/test_sqlite_blacklist_store.py`
- `tests/test_sqlite_stash_store.py`
- `tests/test_default_sqlite_api.py`
- `tests/test_default_sqlite_runtime.py`

### RabbitMQ 相关

保留代码但标记废弃：
- `consumer.py` — 添加 DEPRECATED 注释
- `classifier.py` — RabbitMQ 入口函数标记废弃
- `graph_service.py` — RabbitMQ 入口函数标记废弃

## Docker Compose 变更

### docker-compose.yaml

```yaml
include:
  - compose/milvus.yaml
  - compose/neo4j.yaml
  # redis.yaml 和 rabbitmq.yaml 移除引用

networks:
  devopsnetwork:
    driver: bridge
```

### compose/milvus.yaml

当前 `etcd`、`minio`、`milvus`、`attu` 四个服务**都**带 `profiles: ["vector"]`。变更方式：

- `etcd` / `minio` / `milvus`：**移除** `profiles: ["vector"]`，默认随 `docker compose up -d` 启动。
- `attu`：**保留** `profiles: ["vector"]`，维持可选（仅 `--profile vector` 时启动）。

这样默认起 3 个 Milvus 容器（etcd + minio + milvus），Attu 按需启动，与"4 容器（Neo4j + Milvus 3）"一致。

### compose/redis.yaml 和 compose/rabbitmq.yaml

保留文件，但不在 docker-compose.yaml 中引用。

## 依赖变更

### pyproject.toml

```toml
dependencies = [
    # "redis>=5.0.0",          # 移除
    # ...其他依赖保持不变
]

[project.optional-dependencies]
legacy = [
    "redis>=5.0.0",
    "pika>=1.3.0",
]
```

## 环境变量变更

### 删除的变量

```bash
REDIS_HOST
REDIS_PORT
REDIS_PASSWORD
BLACKLIST_REDIS_DB
RABBITMQ_HOST
RABBITMQ_PORT
RABBITMQ_USER
RABBITMQ_PASSWORD
RABBITMQ_MANAGEMENT_PORT
DATABASE_URL
BLACKLIST_BACKEND
STASH_BACKEND
```

### 保留的 Milvus 变量

```bash
MILVUS_URI=http://127.0.0.1:19530
MILVUS_TOKEN=
MILVUS_STASH_COLLECTION=events
# 其他 Milvus 相关变量
```

### Collection 改名迁移：`stashed_events` → `events`

当前默认 collection 名为 `stashed_events`（`MILVUS_STASH_COLLECTION` 默认值），新设计统一为 `events`。涉及改名的引用点：

- `main.py`：默认值 `stashed_events` → `events`
- `scripts/`：`reset_and_seed_blacklist.py`、`run_blacklist_kv_demo.py`、`cleanup_milvus_duplicates.py`、`blacklist_demo_assertions.py` 中的 `os.getenv("MILVUS_STASH_COLLECTION", "stashed_events")` 默认值同步更新
- `.env.example` / 部署环境的 `MILVUS_STASH_COLLECTION`

数据迁移策略（二选一，需在实施时确认）：

1. **重建（推荐，开发/测试环境）**：events collection schema 与旧 `stashed_events` 不同（新增 raw_content、status、risk_* 等字段），直接新建 `events` collection，旧数据按需丢弃或重跑入库。
2. **迁移（生产环境）**：编写一次性脚本读取旧 `stashed_events`，按新 schema 补默认值后 upsert 到 `events`，验证后删除旧 collection。

> 由于 schema 字段变化较大，默认采用方案 1；若需保留历史数据再走方案 2。

## API 变更

### 健康检查响应

```python
{
    "api": True,
    "milvus": True,
    "neo4j": True
}
```

### 路由变更

| 路由文件 | 变更内容 |
|---------|---------|
| `routes_blacklist.py` | 改用 `persons_store`、`keywords_store`、`event_samples_store` |
| `routes_events.py` | 改用 `events_store`、`review_actions_store` |
| `routes_system.py` | 健康检查改为检测 Milvus 连接状态 |
| `routes_dashboard.py` | 改用 `events_store`、`review_actions_store` 查询统计数据 |
| `routes_graph.py` | 依赖的 `EventRepository` 改用 `events_store`；Neo4j 图谱逻辑不变 |
| `routes_analysis.py` | 不变（调用 main.process_message_detailed） |

## 核心流程

### main.py process_message_detailed

```python
async def process_message_detailed(...):
    # 1. 创建各 store（共享 Milvus 客户端）
    events_store = EventsStore.from_config(config)
    persons_store = PersonsStore.from_config(config)
    keywords_store = KeywordsStore.from_config(config)
    samples_store = EventSamplesStore.from_config(config)
    
    # 2. 黑名单过滤器
    bl_filter = BlacklistFilter(persons_store, keywords_store, samples_store)
    
    # 3. 所有事件写入 events_store
    await events_store.upsert_event(event, status="pending")
    
    # 4. 黑名单匹配
    result = await bl_filter.check(event)
    
    # 5. 更新事件状态和分析结果
    await events_store.update_event(event_id, {
        "status": "blacklisted" if result.hit else "processed",
        "blacklist_decision": ...,
        "risk_score": ...,
        ...
    })
```

### BlacklistFilter 签名

```python
class BlacklistFilter:
    def __init__(
        self,
        persons_store: PersonsStore,
        keywords_store: KeywordsStore,
        samples_store: EventSamplesStore,
    ):
        self._persons = persons_store
        self._keywords = keywords_store
        self._samples = samples_store
```

### 实施顺序（避免中间态 import 崩溃）

被删模块 `blacklist/store.py`、`blacklist/sqlite_store.py`、`blacklist/sqlite_stash.py`、`blacklist/runtime_storage.py`、`backend/app/db/session.py` 均被**顶层 import**（如 `filter.py:20` import `BlacklistStore`、根 `main.py` import `runtime_storage`、6 处 import `db.session`）。必须按以下顺序改，否则任一中间提交都会 import 失败：

1. 新建 `blacklist/milvus_client.py` 和 `blacklist/stores/*`（不依赖旧模块，可独立提交）
2. 改写 `filter.py`、`repositories/events.py`、各 `routes_*`、`backend/app/main.py`、根 `main.py` 的顶层 import，全部指向新 stores
3. 同步改写/删除对应测试（删除 4 个 `test_*sqlite*`/`test_default_*`，改 `test_milvus_stash_*` 等）
4. 确认无任何模块 import 旧文件后，最后再删除旧模块与 `backend/app/db/` 目录
5. 移除 `pyproject.toml` 主依赖中的 `redis`/`pika`（移入 optional `legacy`）

每步后跑一次 `uv run pytest` 与 `python -c "import main; import backend.app.main"` 验证 import 链完整。

## 文档更新

| 文件 | 变更内容 |
|------|---------|
| `README.md` | 移除 Redis/RabbitMQ 依赖说明，更新启动命令 |
| `docs/architecture.md` | 更新存储架构图，说明 Milvus 承担全量存储 |
| `docs/setup.md` | 简化启动步骤，移除 Redis/RabbitMQ |
| `docs/env-vars.md` | 移除 Redis/RabbitMQ 环境变量，更新 Milvus 变量说明 |
| `docs/commands.md` | 移除 Redis 调试命令，更新 docker compose 命令 |
| `docs/testing.md` | 更新测试依赖说明 |
| `docs/pitfalls.md` | 移除 Redis/RabbitMQ 相关问题，更新 Milvus 资源要求 |
| `.env.example` | 移除 Redis/RabbitMQ/SQLite 变量 |

## 启动命令

```bash
# 启动依赖服务（仅 Neo4j + Milvus）
docker compose up -d

# 可选：启动 Milvus Web UI
docker compose --profile vector up -d attu

# 启动后端
uv run uvicorn backend.app.main:app --reload --port 8000
```
