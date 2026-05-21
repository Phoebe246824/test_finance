# 黑名单过滤 + KV 暂存 + 批量构图 — 设计方案

> 所属项目：[AGENTS.md](../../AGENTS.md)

## 1. 背景与目标

### 问题

当前 pipeline 每个事件都走完整的「标准化 → 分类 → 构图(Graphiti 实体/关系提取 + Neo4j 写入) → 风险评估 → 检索 → Dashboard」流程。构图阶段涉及 LLM 实体/关系提取和 Neo4j 写入，是性能瓶颈。

### 目标

引入黑名单过滤机制，低风险事件暂存到 Redis KV，不触发构图。只有命中黑名单的事件才进入后续 pipeline，并在中/高风险触发时从 Redis 拉取同人员的历史事件进行批量构图，从而减少 Graphiti 调用次数。

---

## 2. 改造后的 Pipeline

```
用户输入
  │
  ▼
标准化 (normalize_payload_to_event)
  │
  ▼
┌─────────────────────────────────────────────┐
│ 黑名单过滤器 (新增)                           │
│  ├─ 人员 ID 比对  → person_blacklist (Redis)  │
│  ├─ 敏感词比对    → keyword_blacklist (Redis) │
│  └─ 事件相似度比对 → event_blacklist (Redis)   │
│                                               │
│  OR 逻辑：任一命中 → PASS，全未命中 → STASH   │
└──────────┬──────────────────────────────────┘
           │
     ┌─────┴─────┐
     │           │
  PASS         STASH
     │           │
     ▼           ▼
  分类       存入 Redis KV
     │      key=person:<id_number>
     │      value=JSON event
     │           │
     ▼           ▼
  构图        流程结束
     │      (不分类、不构图)
     ▼
  风险评估
     │
     ├─ 低风险 → 结束
     │
     └─ 中/高风险
          │
          ▼
     查询 Redis KV
     取同 person 的历史事件
          │
          ▼
     批量构图 (当前事件 + 历史事件)
          │
          ▼
     从 Redis 删除已构图的 KV
          │
          ▼
     检索 → Dashboard
```

---

## 3. 新增模块

| 模块 | 位置 | 职责 |
|------|------|------|
| 黑名单管理器 | `blacklist/manager.py` | 加载/查询/追加黑名单（人员库、敏感词库、高危事件库） |
| 黑名单过滤器 | `blacklist/filter.py` | 对 NormalizedEvent 执行三合一 OR 匹配 |
| Redis KV 存储 | `kvstore/redis_store.py` | 人员→事件列表的 CRUD + TTL 管理 |
| 事件批量构图器 | `graphiti/batch_builder.py` | 从 Redis 取历史事件 → 批量写入图谱 |

### 3.1 项目结构变更

```
test_Sentinel/
├── blacklist/                       # 新增：黑名单系统
│   ├── __init__.py
│   ├── manager.py                   # 黑名单 CRUD (load/query/append)
│   └── filter.py                    # 三合一 OR 匹配器
│
├── kvstore/                         # 新增：Redis KV 暂存
│   ├── __init__.py
│   └── redis_store.py              # person → events 的 CRUD
│
├── graphiti/
│   ├── graphiti_workflow.py         # 修改：新增 batch_add_to_graph()
│   └── test.py
│
├── main.py                          # 修改：Flow 中插入黑名单过滤 + KV 暂存 + 批量触发
├── models.py                        # 修改：NormalizedEvent 可能新增 persons 字段
├── consumer.py                      # 修改：标准化后提取人员 ID
│
├── compose/
│   └── redis.yaml                   # 新增：Redis 7-alpine
│
├── docker-compose.yaml              # 修改：引入 redis.yaml
├── .env.example                     # 修改：新增 6 个环境变量
└── docs/
    └── plans/
        └── blacklist-kv-filter-design.md  # 本文档
```

### 3.2 核心接口

```python
# blacklist/filter.py
class BlacklistFilter:
    def __init__(self, redis_client: Redis): ...
    async def check(self, event: NormalizedEvent) -> tuple[bool, list[str]]:
        """返回 (是否放行PASS, 命中的人员id_number列表)"""
    async def append_person(self, id_number: str): ...
    async def append_keyword(self, keyword: str): ...
    async def append_event(self, event_id: str, summary: str): ...

# kvstore/redis_store.py
class EventKVStore:
    def __init__(self, redis_client: Redis, ttl_days: int = 90): ...
    async def stash(self, event: NormalizedEvent, id_numbers: list[str]): ...
    async def fetch(self, id_numbers: list[str], max_per: int, max_age_days: int) -> list[dict]: ...
    async def remove(self, id_numbers: list[str]): ...

# graphiti/graphiti_workflow.py (新增函数)
async def batch_add_to_graph(
    graphiti: Graphiti,
    events: list[dict],  # [{"text": ..., "reference_time": ..., ...}, ...]
    group_id: str,
    dry_run: bool = False,
) -> list[dict]:  # 每个事件的写入结果
```

---

## 4. 黑名单系统

### 4.1 数据结构（Redis）

```
# 人员库 — Sorted Set，score=命中次数（用于统计）
person_blacklist: SortedSet { "P001" -> 5, "P002" -> 3, ... }

# 敏感词库 — Sorted Set，score=命中次数
keyword_blacklist: SortedSet { "制裁" -> 10, "疫情" -> 8, ... }

# 高危事件库 — Hash，存事件摘要供相似度比对
event_blacklist: Hash {
    "<event_id_1>": "<摘要JSON>",
    "<event_id_2>": "<摘要JSON>",
}
```

### 4.2 匹配逻辑（OR 逻辑）

| 维度 | 数据来源 | 匹配方式 | 判定 |
|------|----------|----------|------|
| 人员 | 从 `raw_content` 提取身份证号（P01/A001 等模式） | `ZSCORE person_blacklist <id>` 非 nil 即命中 | 命中后 ZINCRBY +1 |
| 敏感词 | `raw_content` 全文 | 遍历 `keyword_blacklist`，子串匹配 | 任一命中 → PASS，命中后 ZINCRBY +1 |
| 事件相似度 | `raw_content` + `summary` | Jina Rerank API 打分（与 event_blacklist 中所有摘要），最高分 > 阈值 | PASS，存入 event_blacklist |

OR 逻辑：任一维度命中 → PASS；全未命中 → STASH。

### 4.3 命中后的自动积累

```python
# PASS 后自动追加
if person_hit:
    ZINCRBY person_blacklist 1 <id_number>
if keyword_hit:
    ZINCRBY keyword_blacklist 1 <keyword>
if event_hit:
    HSET event_blacklist <event_id> <summary_json>
```

### 4.4 新增环境变量

```
BLACKLIST_EVENT_SIMILARITY_THRESHOLD=0.5   # 事件相似度阈值
BLACKLIST_PERSON_MIN_HITS=1                # 人员命中次数阈值
BLACKLIST_REDIS_DB=1                       # 黑名单使用的 Redis DB 编号
```

---

## 5. Redis KV 暂存

### 5.1 KV 存储方案

**当前采用方案 A**，方案 B/C 保留供后续对比测试。

#### 方案 A：一人一链表（当前采用）

```
KEY:   person:<id_number>
VALUE: JSON 数组 [{event1}, {event2}, ...]
TTL:   可配置，默认 90 天
```

- 一个事件涉及 N 个人 → 写入 N 条 key
- 实现最简单，直接 `RPUSH` + `EXPIRE`

```python
async def stash_event(event: NormalizedEvent, id_numbers: list[str]):
    for pid in id_numbers:
        key = f"person:{pid}"
        await redis.rpush(key, event.model_dump_json())
        await redis.expire(key, ttl_seconds)

async def fetch_person_events(id_numbers: list[str], max_per_person: int) -> list[dict]:
    events = []
    for pid in id_numbers:
        raw = await redis.lrange(f"person:{pid}", -max_per_person, -1)
        events.extend(json.loads(r) for r in raw)
    return events
```

**缺点**：一个人关联多个事件时，JSON 数组会膨胀，但实际场景中单个人员的暂存事件量有限（通常 < 100 条）。

#### 方案 B：事件级存储 + 人员索引

```
KEY:   event:<event_id>          → JSON 事件体
INDEX: person:<id_number>        → Set { event_id, event_id, ... }
```

- 查询时先查 person Set 获取 event_id 列表，再逐个 MGET
- 优点：事件体不重复存储（如果多个人关联同一事件）
- 缺点：需要维护索引 + 事件两套 key，复杂度更高

#### 方案 C：事件为主键，人员字段内嵌

```
KEY:   event:<event_id>  → JSON { ..., "persons": ["P01", "P02"] }
```

- 查询时用 `SCAN event:*` + JSON 过滤筛选含指定人员的记录
- 优点：结构简单
- 缺点：`SCAN` 性能差，不适合频繁查询

### 5.2 新增环境变量

```
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0                    # KV 存储使用的 DB
KV_TTL_DAYS=90               # 暂存事件过期天数
BATCH_MAX_PER_PERSON=20      # 批量构图时每人最多取 N 条
```

### 5.3 Docker Compose 新增

```yaml
# compose/redis.yaml
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
```

---

## 6. 批量构图

### 6.1 触发时机

在 `SentinelPipelineFlow.risk_evaluation()` 中，当首次评估 `risk_score > RISK_THRESHOLD` 且事件包含可识别的人员 ID 时触发。

### 6.2 批次范围

- 从 Redis 取同一身份证号的历史事件
- 每人最多取 `BATCH_MAX_PER_PERSON` 条（默认 20）
- 暂存超过 `KV_TTL_DAYS` 天的事件已自然过期

### 6.3 流程

```python
# risk_evaluation() 中，risk_score > threshold 时
id_numbers = extract_subject_id_numbers(event.raw_content)
if id_numbers:
    historical_events = await kvstore.fetch(
        id_numbers,
        max_per_person=int(os.getenv("BATCH_MAX_PER_PERSON", "20")),
    )
    if historical_events:
        batch_texts = [event.raw_content] + [e["raw_content"] for e in historical_events]
        await batch_add_to_graph(graphiti, batch_texts, group_id, dry_run)
        # 构图成功后删除 Redis 中已处理的 KV
        for pid in id_numbers:
            await redis.delete(f"person:{pid}")
        await close_graph_client(graphiti)
```

### 6.4 构图后清理

- 已构图的 KV 直接从 Redis 删除（`DEL person:<id_number>`）
- 如果批量构图失败，KV 保留不删除，下次触发时重新取（依赖 Graphiti 去重 + `LRANGE` 从尾部取相同的 N 条）

---

## 7. Pipeline 变更详情

### 7.1 标准化后 → 黑名单过滤（run_flow 中新增）

```python
# run_flow() 中，normalize_payload_to_event() 之后:
filter = BlacklistFilter(redis_client)
kvstore = EventKVStore(redis_client)
id_numbers = extract_subject_id_numbers(normalized_event.raw_content)
should_proceed, matched_persons = await filter.check(normalized_event)

if not should_proceed:
    await kvstore.stash(normalized_event, id_numbers or [])
    print_info("事件未命中黑名单，已暂存到 Redis")
    # 流程结束，不进行后续分类/构图
    return

# PASS: 自动积累到黑名单
if matched_persons:
    for pid in matched_persons:
        await filter.append_person(pid)
```

### 7.2 风险评估 → 批量构图触发（risk_evaluation 中修改）

在第一次评估 risk_score > threshold 时，插入 Redis KV 查询 + 批量构图逻辑。位置在 `simulate_search()` 调用之前。

### 7.3 配置加载新增 Redis 段

```python
# main.py load_config() 中新增
"redis": {
    "host": os.getenv("REDIS_HOST") or "localhost",
    "port": int(os.getenv("REDIS_PORT") or "6379"),
    "password": os.getenv("REDIS_PASSWORD") or "",
    "db": int(os.getenv("REDIS_DB") or "0"),
    "blacklist_db": int(os.getenv("BLACKLIST_REDIS_DB") or "1"),
},
```

---

## 8. 新增文件清单

| 文件 | 操作 | 预估行数 |
|------|------|----------|
| `blacklist/__init__.py` | 新增 | ~15 |
| `blacklist/manager.py` | 新增 | ~80 |
| `blacklist/filter.py` | 新增 | ~120 |
| `kvstore/__init__.py` | 新增 | ~15 |
| `kvstore/redis_store.py` | 新增 | ~80 |
| `graphiti/graphiti_workflow.py` | 修改 | +~50 (batch_add_to_graph) |
| `main.py` | 修改 | +~60 (过滤 + 批量触发) |
| `consumer.py` | 修改 | +~20 (提取人员 ID) |
| `models.py` | 修改 | +~10 (新增 persons 字段可选) |
| `compose/redis.yaml` | 新增 | ~8 |
| `docker-compose.yaml` | 修改 | +~3 (include redis.yaml) |
| `.env.example` | 修改 | +~10 (新增 6+ 环境变量) |
| `docs/plans/blacklist-kv-filter-design.md` | 新增 | 本文档 |

---

## 9. 验证方式

1. 启动 Redis：`docker compose up -d redis`
2. 运行 `uv run python main.py`
3. 输入一条不涉及黑名单的普通事件 → 应看到 "已暂存到 Redis" 且不到达分类/构图
4. 输入一条包含黑名单人员/敏感词的事件 → 应看到 PASS 并正常走完整 pipeline
5. 连续输入多条同一人员的事件，其中一条为高风险 → 应看到从 KV 取回历史事件并批量构图
6. 用 `redis-cli KEYS "person:*"` 验证 KV 写入和删除
7. 用 `redis-cli ZRANGE person_blacklist 0 -1 WITHSCORES` 验证黑名单命中计数
