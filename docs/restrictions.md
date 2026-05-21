> 所属项目：[AGENTS.md](../AGENTS.md)

## 禁止事项

以下操作**绝对禁止**：

### 文件与目录

> ⚠️ **禁止修改 `graphiti_core/` 目录中的任何文件**，除非你明确知道这是项目定制的 Graphiti 分支且理解全部影响

> ⚠️ **禁止删除 `docs/` 目录中的报告文档**，它们记录了开发过程中的关键决策

> ⚠️ **禁止修改 `.env` 文件并提交**，该文件已在 `.gitignore` 中

> ⚠️ **禁止提交 `logs/`、`__pycache__/`、`.mypy_cache/`、`.ruff_cache/` 目录中的文件**

### 环境与配置

> ⚠️ **禁止硬编码 API 密钥或密码**，所有敏感信息必须通过环境变量读取

> ⚠️ **禁止直接操作生产环境的 Neo4j / RabbitMQ**，仅操作本地 Docker Compose 服务

> ⚠️ **禁止在没有 `GRAPHITI_DRY_RUN=true` 保护的情况下，对生产 Neo4j 执行写入测试**

### 代码与架构

> ⚠️ **禁止绕过 `uv run ruff check` lint 检查强行提交**

> ⚠️ **禁止在 Flow 的 Stage 方法中直接调用外部 API**，必须通过 providers 或对应的 service 模块

> ⚠️ **禁止在 `main.py` 中新增业务逻辑**，业务逻辑应放在对应的 service 模块中

### 数据库

> ⚠️ **禁止删除 Neo4j 中的已有数据或索引**，除非通过 Graphiti 提供的 API

> ⚠️ **禁止手动修改 `compose/volumes/` 下的持久化数据文件**
