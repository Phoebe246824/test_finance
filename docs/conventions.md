> 所属项目：[AGENTS.md](../AGENTS.md)

## 代码规范

### 命名约定

| 类型 | 约定 | 示例 |
|------|------|------|
| 文件名 | snake_case | `log_utils.py`, `graph_service.py` |
| 类名 | PascalCase | `SentinelPipelineFlow`, `EventClassifier` |
| 函数名 | snake_case | `normalize_event()`, `add_event_to_graph()` |
| 变量名 | snake_case | `normalized_event`, `risk_threshold` |
| 常量 | UPPER_SNAKE_CASE | `MAX_QUERY_LENGTH`, `PIKA_AVAILABLE` |
| 私有模块级变量 | `_` 前缀 | `_ACTIVE_LLMS`, `_PROCESSED_EVENTS` |
| 枚举值 | UPPER_SNAKE_CASE | `EventSource.NEWS`, `RiskLevel.HIGH` |

### 代码格式化

- 使用 **ruff** 进行格式化和 lint 检查
- 缩进：4 空格（Python 标准）
- 字符串：单引号优先，docstring 使用三重双引号
- 行尾：LF

### 注释和文档字符串

- 模块级 docstring：每个 `.py` 文件以模块说明开头，描述该模块在整个系统中的角色
- 函数 docstring：使用 Google 风格（Args / Returns / 作用），中文描述
- 类属性 docstring：Pydantic 模型字段使用 `Field(description="...")` 标注
- 行内注释：使用中文解释业务逻辑（如 `# 实例化 TypeClassifier + RiskEvaluator 两个 Agent`）
- 日志记录使用 f-string 或 `%s` 占位符

### 提交信息格式

从 `git log` 记录来看，项目使用类似 Conventional Commits 的格式：

```
<type>: <中文描述>
```

type 包括：`feat`(新功能)、`fix`(修复)、`refactor`(重构)、`docs`(文档)、`chore`(杂项)

示例：
- `feat(graph): add GRAPHITI_DRY_RUN env var to skip Neo4j writes (#7)`
- `fix: remove unused import and redundant global in providers`
- `refactor(logging): 日志系统分离 — print 与 logging 职责拆分`
