# 日志系统分离重构方案

## 现状问题

| 问题 | 说明 |
|------|------|
| 职责混杂 | `main.py` 用 `print()` 同时输出终端和文件（通过 `TeeOutput`），用户交互和调试日志不分 |
| 两套系统互不连接 | `main.py` 用 print+Tee，`consumer.py` 用 logging，无统一配置 |
| 用户反馈缺失 | 某些 `except` 块只记了 logger.error 但用户终端看不到任何提示（如 consumer.py 的 RabbitMQ 连接失败） |
| 文件日志冗余 | TeeOutput 把用户信息和控制台细节都写进同一个文件，不分层 |
| graphiti_core 日志无声 | vendor 代码用了 logging.getLogger 但根 logger 无配置 |

**本次重构不包括** `graphiti_core/`（vendor 代码），范围：`main.py`、`consumer.py`、`graphiti/graphiti_workflow.py`。

---

## 方案

### 1. 新建 `log_utils.py` — 集中式日志模块

```
repo-root/
├── log_utils.py              # ← 新增
├── main.py
├── consumer.py
└── graphiti/
    └── graphiti_workflow.py
```

#### `log_utils.py` 职责

```python
"""
两套独立的输出系统：

1. print: → 终端 stdout  only（简洁，面向用户）
   - print_info()    # 绿色 ✓ / 蓝色 ℹ
   - print_warn()    # 黄色 ⚠
   - print_error()   # 红色 ✗
   - print_banner()  # 分隔线和标题（Pipe 阶段名等）

2. logger: → 文件 only（详细，面向开发者）
   - get_logger(name) → logging.Logger
     格式: [2026-05-19 10:30:00] [INFO] [consumer.news] 消息已处理
     文件: logs/sentinel_<timestamp>.log  (由 main.py 统一创建)
     级别: DEBUG, 轮转 5MB×3
"""
```

**关键设计决策：**

- `print_info/warn/error` 是 thin wrapper，行为等同于 `print()`，但通过命名区分用途
- `get_logger(name)` 返回一个**只有文件 handler** 的 Logger，不附加控制台 handler
- 根 logger 由 `main.py` 在入口处初始化（`setup_file_logging()`），子模块只管 `get_logger(__name__)`
- `consumer.py` 的 `setup_logger()` 删除控制台 handler，改为调用 `get_logger()`

---

### 2. `main.py` 改动

#### 2a. 删除 `TeeOutput` 和 `setup_output_logging()`

```
删除: TeeOutput 类 (行 46-67)
删除: setup_output_logging() (行 69-83)
删除: ANSI_ESCAPE_RE (行 43)
```

#### 2b. 新增 `setup_file_logging()` 在 `main()` 入口

```python
def setup_file_logging(log_dir: str | None = None) -> str:
    """初始化文件日志系统，返回日志路径。"""
    ...
    # 创建 logs/ 目录
    # 设置 FileHandler (格式 [%(asctime)s] [%(levelname)s] [%(name)s] %(message)s)
    # 附加到根 logger，使所有 get_logger(__name__) 的子 logger 自动继承
```

#### 2c. print 分类替换

对现有 134 处 `print()` 按语义分类：

| 分类 | 当前 print 示例 | 替换为 |
|------|----------------|--------|
| **用户交互** | `"请输入消息内容:"`、结果输出、`"退出程序"`、Banner 标题 | `print()` 保持不变 |
| **流程分界** | Stage 分隔线、`[Flow] Stage X: XXX` | `print_banner()` |
| **进度反馈** | `"初始化完成 ✓"`、`"写入成功 ✓"`、`"搜索成功 ✓"` | `print_info()` |
| **操作详情** | 实体数量、消息大小、subject_id_numbers 等 | `logger.info()` |
| **错误/异常** | `"写入失败: {e}"`、`"搜索失败: ..."` | `print_error()`（用户可见）+ `logger.error()`（文件详情） |

**具体映射示例（search 部分）：**

```python
# 当前 (print 混用):
print("[search] 正在初始化 Graphiti 搜索客户端...")
print("[search] 初始化 Graphiti 搜索客户端 ✓")
# ...
except Exception as e:
    print(f"         搜索失败: {type(e).__name__}: {e}")
    print("         搜索异常堆栈如下:")
    traceback.print_exc()

# 改为:
from log_utils import print_info, print_error
logger = logging.getLogger("main.search")

print_info("正在初始化 Graphiti 搜索客户端...")
print_info("初始化完成")
# ...
except Exception as e:
    print_error("搜索失败，跳过检索")
    logger.error("搜索失败: %s: %s", type(e).__name__, e)
    logger.error("异常堆栈:\n%s", traceback.format_exc())
```

---

### 3. `consumer.py` 改动

#### 3a. 修改 `setup_logger()`

```diff
- # 控制台 handler
- console_handler = logging.StreamHandler()
- console_handler.setLevel(logging.INFO)
- console_handler.setFormatter(formatter)
- logger.addHandler(console_handler)
+ # 不再附加控制台 handler，用户反馈通过 log_utils.print_error() 从调用方处理
```

#### 3b. 补充用户反馈

`consumer.py` 中有多处 `logger.error()` 但用户看不到：

| 位置 | 当前 | 改为增加 |
|------|------|---------|
| `start_consumers()` RabbitMQ 连接失败 | `logger.error("RabbitMQ 连接失败: {e}")` | 抛异常到上层（已在做），入口 `main.py` 的 caller 要补 `print_error()` |
| 消息处理异常 (callback) | `logger.error(...)` | `logger.error + exc_info` 已有，不需额外用户反馈（消费者静默处理是合理行为） |
| 发送消息失败 | `logger.error(f"发送消息失败: {e}")` | caller 补 `print_error()`（但目前调用方在 consumer.py 内部 API 里，可以保持现状） |

关键缺失点：**`start_consumers()` 中 `raise` 后，`main.py` 的 `start_service()`/`run_flow()` 要捕获并 `print_error()`。**

---

### 4. `graphiti/graphiti_workflow.py` 改动

仅有 1 处 print：

```python
# line 421
print(f"[hybrid_search] 相关性过滤: {before} -> {after} (min_score={min_score})")
```

→ 改为 `logger.info(...)`

---

### 5. 错误处理 — 补充用户反馈清单

| 场景 | 现有 | 用户可见？ | 改动 |
|------|------|-----------|------|
| RabbitMQ 连接失败 | `logger.error` + `raise` | ❌ | `main.py` 的 `run_flow()` 外层捕获并 `print_error()` |
| 消息发送失败 | `logger.error` | ❌ | 保持（内部 retry 逻辑，不应打扰用户） |
| 图写入失败 (graph_build) | `print(f"写入失败: {e}")` | ✅ | 改为 `print_error()` + `logger.error (含 exc_info)` |
| 搜索超时 | `print("搜索超时...")` | ✅ | 改为 `print_warn()` + `logger.warning` |
| 搜索失败 | `print("搜索失败...")` + `traceback.print_exc()` | ✅ | 改为 `print_error()` + `logger.error(traceback)` |
| classification 解析失败 | `print(f"解析分类结果失败: {e}")` | ✅ | 改为 `print_error()` + `logger.error` |
| risk evaluation 失败 | `print(f"解析风险评估失败: {e}")` | ✅ | 改为 `print_error()` + `logger.error` |
| 标准化 Agent 调用异常 | 无 try/except 包裹 | ❌ | 加 try/except + `print_error()` + `logger.error` |

---

### 6. 总结 `print_*` / `logger` 职责划分

```
print_info / print_warn / print_error
├── 仅终端 stdout
├── 简单文本，无需时间戳前缀
├── 面向用户的进度与错误提示
└── 不应包含内部技术细节

logger.info / logger.warning / logger.error
├── 仅文件
├── 格式化 [时间] [级别] [模块名] 消息
├── 面向开发者
└── 包含完整上下文（trace_id、堆栈、参数值）
```

---

## 实施步骤

### Step 1: 创建 `log_utils.py`

实现 `get_logger()`, `print_info()`, `print_warn()`, `print_error()`, `print_banner()`。

### Step 2: 修改 `main.py`

- 删除 `TeeOutput` 类及相关变量
- 删除 `setup_output_logging()`，替换为 `setup_file_logging()`
- 把所有 `print()` 按语义替换为 `print_info/warn/error/banner` 或 `logger.*`
- 在 `run_flow()` 的外层 try 中补充 RabbitMQ 连接失败的 `print_error()`
- 补上 `normalize_payload_to_event()` 缺少的 try/except

### Step 3: 修改 `consumer.py`

- `setup_logger()` 删除 console_handler
- `start_consumers()` 中 `raise` 前加一行 `print_error()`（快速反馈不需要等到调用方）

### Step 4: 修改 `graphiti/graphiti_workflow.py`

- 替换 1 处 `print()` 为 `logger.info()`

### Step 5: 验证

```bash
uv run python main.py
# 确认终端只显示简洁的用户信息
# 确认 logs/ 目录下的文件包含完整结构化日志
# 确认异常场景下用户能看到错误提示
```
