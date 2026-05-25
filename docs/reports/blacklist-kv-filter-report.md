# 黑名单过滤 + KV 暂存 + 批量构图 — 实现报告

> 原设计文档：已归档至 `docs/plans/blacklist-kv-filter-design.md`（实现后删除，以下为本报告）

## 1. 实现概述

在 pipeline 标准化阶段之后插入黑名单过滤机制：低风险事件暂存到 Redis KV（不构图），只有命中黑名单的事件进入完整 pipeline，并在中/高风险触发时从 Redis 拉取同人员历史事件批量构图。

### 数据流（最终形态）

```
用户输入
  │
  ▼
标准化 (normalize_payload_to_event)
  │
  ▼
┌─────────────────────────────────────────────┐
│ 黑名单过滤器 (BlacklistFilter)                │
│  ├─ 人员 ID 比对  → person_blacklist (Redis) │
│  ├─ 敏感词比对    → keyword_blacklist (Redis)│
│  └─ 事件相似度比对 → event_blacklist (Redis)  │
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
     ▼      value=JSON event
  构图            │
     │           ▼
     ▼        流程结束
 风险评估    (不分类、不构图)
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

## 2. 模块结构（最终形态）

```
test_Sentinel/
├── blacklist/                       # 黑名单系统
│   ├── __init__.py                  # 导出 BlacklistStore, BlacklistFilter
│   ├── store.py                     # 统一存储：黑名单 CRUD + 事件暂存/回捞/删除
│   └── filter.py                    # 三合一 OR 匹配器
│
├── utils/
│   └── text.py                      # extract_subject_id_numbers() +
│                                    # extract_person_id_numbers()
│
├── graphiti/
│   └── graphiti_workflow.py         # 新增 batch_add_to_graph()
│
├── main.py                          # Flow 中插入黑名单过滤 + KV 暂存 + 批量触发
│
├── scripts/
│   ├── reset_and_seed_blacklist.py  # 重置并写入测试种子数据
│   └── run_blacklist_kv_demo.py     # 15 个测试用例自动回放
│
├── tests/
│   ├── test_blacklist_filter.py     # 三合一 OR 匹配（12 tests）
│   ├── test_blacklist_manager.py    # BlacklistStore CRUD（13 tests）
│   ├── test_kvstore.py              # 暂存/回捞/去重（12 tests）
│   └── test_extract_subject_id_numbers.py  # ID 提取（10 tests）
│
├── compose/
│   └── redis.yaml                   # Redis 7-alpine
│
└── docker-compose.yaml              # 引入 redis.yaml
```

## 3. 与设计方案的关键差异

| 设计项 | 原方案 | 最终实现 | 原因 |
|--------|--------|----------|------|
| 存储层 | `blacklist/manager.py` + `kvstore/redis_store.py` 两个模块 | 合并为 `blacklist/store.py` 单一 `BlacklistStore` 类 | 减少模块碎片化，两个 Redis DB 由同一类管理 |
| filter.check() 返回 | `tuple[bool, list[str]]` | `tuple[bool, list[str], list[str], bool]` | 增加 keywords 列表和 event_sim_hit 标志，供 main.py 显式积累 |
| 自动积累时机 | `filter.check()` 内部自动 ZINCRBY/HSET | move to `main.py`，在 PASS 后显式调用 `store.append_*()` | 分离检查与副作用，便于测试和调试 |
| 批量构图位置 | 新建 `graphiti/batch_builder.py` | 加到 `graphiti/graphiti_workflow.py` | 避免过度拆分 |
| ID 提取 | `extract_subject_id_numbers()` 提取所有主体 ID | 新增 `extract_person_id_numbers()` 仅提取 P 前缀 | blacklist/KV 只关注人员维度 |
| 回捞去重 | 无 | `fetch_stashed_events()` 按 event_id 去重 | 同一事件涉及多人时，防止重复构图 |

## 4. Redis 数据结构

### DB 0 — 事件暂存（stash）

```
KEY:   person:<id_number>          ← Redis List
VALUE: NormalizedEvent JSON        ← RPUSH 追加
TTL:   KV_TTL_DAYS × 86400 秒      ← 默认 90 天
```

一个事件涉及 N 个人 → 写入 N 条 key。

### DB 1 — 黑名单

```
person_blacklist:  SortedSet { "P05" → 2 }         ← ZINCRBY 计数
keyword_blacklist: SortedSet { "制裁" → 10, ... }   ← ZINCRBY 计数
event_blacklist:   Hash { "E-HIGH-RISK-001": "{...}", ... }
```

### 新增环境变量

```
# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0                        # KV 存储使用的 DB
BLACKLIST_REDIS_DB=1              # 黑名单使用的 Redis DB
BLACKLIST_EVENT_SIMILARITY_THRESHOLD=0.5
KV_TTL_DAYS=90
BATCH_MAX_PER_PERSON=20
```

## 5. 测试策略

### 单元测试（51 tests，全部通过）

| 测试文件 | 覆盖范围 | 数量 |
|----------|----------|------|
| `test_blacklist_filter.py` | 人员/敏感词/事件相似度匹配，三合一 OR 逻辑 | 12 |
| `test_blacklist_manager.py` | BlacklistStore CRUD（person/keyword/event） | 13 |
| `test_kvstore.py` | stash_event/fetch_stashed_events/remove_stashed_events，去重 | 12 |
| `test_extract_subject_id_numbers.py` | extract_subject_id_numbers() + extract_person_id_numbers() | 10 |

### 功能测试（15 个用例，通过 `run_blacklist_kv_demo.py` 自动回放）

| 用例 | 场景 | 预期结果 |
|------|------|----------|
| 1 | 无人员编号 → 不写 KV | STASH（0 keys） |
| 2-4 | 非黑名单人员 + 低风险 | STASH → 写入 person:PXX |
| 5 | 仅匹配敏感词（无人员） | PASS → 完整 pipeline |
| 6 | 人员黑名单命中 P05 | PASS → 完整 pipeline |
| 7A/7B | P06+P07 低风险事件 | STASH → 积累历史 |
| 7C | P06 高风险（关键词触发） | PASS → fetch P06 历史 → 批量构图 |
| 8A/8B | P08+P09 低风险事件 | STASH → 积累历史 |
| 8C | P08+P09 高风险（关键词触发） | PASS → fetch 历史 → 批量构图 |
| 9 | 事件相似度命中 | PASS（依赖 Jina Rerank） |
| 10 | 无人员但命中敏感词 | PASS |

### 种子数据设计要点

- `P05` 仅在黑名单中，用于测试人员命中路径（Case 6）
- `P06/P08/P09` **不在**黑名单中，确保低风险事件能正常暂存，为后续回捞提供历史数据
- 8 个敏感词种子覆盖各场景（制裁、爆炸、裁员、暴雷、洗钱、刀具、可燃液体、危险化学品）
- 2 个高危事件摘要供 Jina Rerank 相似度匹配

## 6. 已知问题与修复记录

| 问题 | 修复 | 状态 |
|------|------|------|
| `blacklist/filter.py → main.py` 循环导入 | 将 `extract_subject_id_numbers` 移至 `utils/text.py` | ✅ |
| Redis 连接泄漏（stash 后未 close） | 在 `run_flow` 中加 `try/finally` | ✅ |
| KV 在批量构图前被过早删除 | 改为仅当 `all_success` 时才删除 | ✅ |
| CrewAI Flow `kickoff()` 在 async 上下文报 "Event loop is closed" | 全局替换为 `kickoff_async()` | ✅ |
| `uv run python main.py` 违反项目规范 | demo 脚本改为 `uv run main.py` | 待修复 |
| P06/P08/P09 在黑名单中导致 demo 回捞失败 | 从种子数据移除，加注释说明 | ✅ |
| `crew.kickoff_async()` 调用错误 | 修正为 `await crew.kickoff_async()` | ✅ |
| `_check_keywords()` 返回 `bool` 导致多关键词丢失 | 改为返回 `list[str]` | ✅ |

## 7. 验证方式

```bash
# 1. 启动所有依赖
docker compose up -d

# 2. 重置测试数据
uv run scripts/reset_and_seed_blacklist.py

# 3. 运行 demo 自动回放
uv run scripts/run_blacklist_kv_demo.py

# 4. 验证 Redis
docker exec redis redis-cli -n 0 KEYS "person:*"
docker exec redis redis-cli -n 1 ZRANGE person_blacklist 0 -1 WITHSCORES

# 5. 运行单元测试
uv run pytest tests/ -v

# 6. 手动测试
uv run main.py
```
