# 事件分类与自适应提示词 — 重构报告

## 问题描述

1. **Dashboard 意图分析与趋势预测使用固定提示词**：无论事件属于国际政治、科技、经济还是公共卫生领域，都使用同一套分析模板，输出维度与领域不匹配
2. **缺乏严重度评估**：无法判断事件影响的严重程度，趋势预测的时间范围固定，无法区分「局部小事件」与「全球大事件」
3. **事件分类缺失**：下游分析无法获知事件所属领域，无法针对性地调整分析策略

## 根因分析

1. **无分类器模块**：`simulate_dashboard()` 直接调用 CrewAI Agent，没有中间分类步骤
2. **提示词一刀切**：`prompts/intent_analysis.md` 和 `prompts/trend_prediction.md` 为通用模板，不包含领域特定的分析维度
3. **无严重度映射**：趋势预测的时间范围（短期/中期/长期）固定写死，未与事件影响程度关联

## 解决方案

新增 `trend_prediction` 模块，实现事件分类、严重度评估、自适应提示词三件套。

### 架构

```
simulate_dashboard()
  ├─ EventClassifier.classify_with_severity()  → 类别 + 严重度（Jina Rerank API / 关键词回退）
  ├─ get_intent_analysis_task()                → 根据类别选择 adapter 提示词
  ├─ get_trend_prediction_task()               → 根据类别 + 严重度选择 adapter 提示词 + 时间范围
  └─ CrewAI Flow 执行
```

### 模块结构

```
trend_prediction/
├── __init__.py                 # 公共 API 导出（EventClassifier）
├── classifier.py               # 事件分类器：Jina Rerank + 关键词回退
├── task_templates.py           # 自适应任务模板工厂
├── adapters/
│   ├── __init__.py             # Adapter 注册表
│   ├── base.py                 # 抽象基类（DomainAdapter）
│   ├── economy.py              # 经济领域 adapter
│   ├── energy.py               # 能源领域 adapter
│   ├── finance.py              # 金融领域 adapter
│   ├── intl_politics.py        # 国际政治领域 adapter
│   ├── public_health.py        # 公共卫生领域 adapter
│   ├── society.py              # 社会/文化领域 adapter
│   └── tech.py                 # 科技领域 adapter
└── prompts/
    ├── intent_analysis.md      # 通用意图分析模板（兜底）
    └── trend_prediction.md     # 通用趋势预测模板（兜底）
```

### 数据流

```
事件文本
  │
  ▼
EventClassifier.classify_with_severity()
  ├─ Jina Rerank API（优先）→ 单次调用同时返回类别 + 严重度
  │   └─ _rerank_classify_combined() → 类别描述 + 严重度描述合并为 documents
  └─ 关键词匹配（回退）→ _keyword_classify() 分别匹配类别/严重度关键词
  │
  ▼
(category, confidence, severity, severity_confidence)
  │
  ▼
get_intent_analysis_task(category)
  └─ get_adapter(category) → DomainAdapter.get_intent_analysis_prompt()
  └─ 无 adapter → prompts/intent_analysis.md（兜底）
  │
  ▼
get_trend_prediction_task(category, severity)
  └─ get_adapter(category) → DomainAdapter.get_trend_prediction_prompt(severity)
  └─ 无 adapter → prompts/trend_prediction.md（兜底）
  └─ 严重度 → SEVERITY_TO_TIME_RANGES 映射动态时间范围
```

### 变更详情

| 环节 | 文件 | 变更内容 |
|---|---|---|
| 分类器核心 | `trend_prediction/classifier.py` | 新增 `EventClassifier` 类；`classify_with_severity()` async 方法；`_rerank_classify_combined()` 合并 API 调用；`_keyword_classify()` 关键词回退；7 类别 + 4 级严重度常量定义 |
| 适配器模式 | `trend_prediction/adapters/` | 8 个 adapter 文件（base + 7 领域）；注册表 `get_adapter()` 按类别标识返回对应 adapter |
| 任务模板 | `trend_prediction/task_templates.py` | `get_intent_analysis_task()` / `get_trend_prediction_task()` 工厂函数；`_get_adaptive_prompt()` 文件存在性检查 |
| Dashboard 集成 | `main.py:simulate_dashboard()` | `def` → `async def`；调用 `classify_with_severity()`；使用自适应任务模板替代固定提示词 |
| Flow 集成 | `main.py:SentinelPipelineFlow.dashboard()` | `def` → `async def`，`await simulate_dashboard()` |
| 公共导出 | `trend_prediction/__init__.py` | 新增 `EventClassifier` 导出 |
| 配置入口 | `main.py:load_config()` | 新增 `graphiti.dry_run` 配置项（`GRAPHITI_DRY_RUN` 环境变量） |
| 配置模板 | `.env.example` | 新增 `GRAPHITI_DRY_RUN` 配置项 |

### 涉及的文件

| 文件 | 变更行数 | 变更类型 |
|---|---|---|
| `trend_prediction/classifier.py` | +553 | 新增：分类器核心 |
| `trend_prediction/adapters/` (8 files) | +536 | 新增：适配器模式 |
| `trend_prediction/task_templates.py` | +134 | 新增：任务模板工厂 |
| `trend_prediction/prompts/` (2 files) | +41 | 新增：兜底提示词 |
| `trend_prediction/__init__.py` | +5 | 新增：公共导出 |
| `main.py` | +47 / -117 | 修改：Dashboard async 化 + 自适应集成 |
| `.env.example` | +2 | 新增：`GRAPHITI_DRY_RUN` 配置 |

### 不修改的范围

- `graphiti_core/` — 第三方库，未修改
- `consumer.py` — RabbitMQ 消费者，未改动
- Stage 1–4（分类、图谱构建、风险评估、搜索）— 流程不变
- Stage 5 搜索的 `min_score` 阈值 — 已在之前 PR 中独立实现

## 关键修复

| 问题 | 修复 |
|---|---|
| `classify_with_severity` 在 async 上下文中崩溃 | `def` + `loop.run_until_complete()` → `async def`，调用链同步改异步 |
| 异常捕获过窄 | `except (RuntimeError, ValueError)` → `except Exception as e` + 日志警告 |
| `_rerank_classify_combined` 忽略传入参数 | 使用 `category_descriptions` / `severity_descriptions` 参数替代模块级全局变量 |
| `_get_adaptive_prompt` 文件不存在崩溃 | 添加 `prompt_path.exists()` 检查，返回兜底字符串 |

## 配置说明

```env
# 调试模式：设为 true 跳过 Neo4j 写入（反复调试同一事件时不产生重复数据）
GRAPHITI_DRY_RUN=false
```

事件分类器无需额外配置，自动读取已有的 `RERANKER_API_KEY` / `RERANKER_BASE_URL` / `RERANKER_MODEL` 环境变量。未配置 API Key 时自动回退到关键词匹配。

## 影响范围

- **Stage 7（Dashboard）**：`simulate_dashboard()` 从同步改为异步，增加分类 + 自适应提示词步骤
- **CrewAI Flow**：`dashboard()` step 从同步改为异步，与 `async def` 兼容
- **向后兼容**：`hybrid_search()` 等 Stage 4 函数签名不变，不受影响
- **关键词匹配**：7 类别 × 约 20 关键词 + 4 级严重度 × 约 12 关键词，覆盖主流事件类型
