# 日志系统分离 — 功能实现报告

## 目标

解决终端输出混乱问题：print/logger 共用 stdout 导致 CrewAI 动态面板与普通日志竞争输出，
同时文件日志被终端 handler 稀释，难以定位问题。

## 方案

将终端输出与文件日志完全解耦，互不干扰：

| | 终端 (stdout) | 文件 (logs/) |
|---|---|---|
| 函数 | `print_info / print_warn / print_error / print_banner` | `logger.info / logger.warning / logger.error / logger.debug` |
| 格式 | Rich Console 彩色输出 | `[时间] [级别] [模块名] 消息` |
| 阅读者 | 终端用户 | 开发者事后回溯 |
| 信息量 | 简洁 | 完整 |

## 变更

### 新增文件

- `log_utils.py` — 封装 print_* 与 logger.* 两套输出

### 修改文件

- `main.py` — 删除 TeeOutput，替换 134 处裸 print() 为 print_*/logger.*
- `consumer.py` — 删除控制台 handler，添加 RabbitMQ 连接失败的 print_error
- `graphiti/graphiti_workflow.py` — 替换裸 print()
- `graphiti_core/cross_encoder/jina_reranker_client.py` — 替换裸 print()

### 噪音压制

文件日志中抑制以下模块的 DEBUG 级别：

`neo4j`, `httpx`, `urllib3`, `httpcore`, `crewai`, `asyncio`

### 伴随修复

- 删除 Flow 中各 `simulate_*` 函数冗余的阶段 banner（避免重复输出）
- `classify_event` 返回 None 时 `simulate_classification` 不再崩溃
- `simulate_search` 返回值标注修正为 `-> dict`

## 设计决策

1. **Rich Console > raw print** — 避免与 CrewAI 面板竞争光标位置
2. **Logger 不输出到终端** — 文件专用，确保文件日志干净完整
3. **No custom logging levels** — 直接使用 Python logging 标准级别
4. **RotatingFileHandler** — 单文件 5MB，保留 3 个备份，防止日志无限增长
