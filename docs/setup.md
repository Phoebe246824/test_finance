> 所属项目：[AGENTS.md](../AGENTS.md)

## 开发环境搭建

### 前置依赖

- **Python**: 3.13+
- **uv**: 0.11+（依赖管理与脚本运行器，安装方式见 https://docs.astral.sh/uv/）
- **Docker** + Docker Compose（默认启动 Milvus + Neo4j）
- **Git**
- **Node.js**: 20+（用于 Vue3 前端）

### 初始化步骤

```bash
# 1. 克隆仓库
git clone <repo-url> && cd test_finance

# 2. 创建虚拟环境
uv venv

# 3. 安装 Python 依赖
uv sync --dev

# 4. 配置环境变量
cp .env.example .env
# 编辑 .env，至少填入 LLM_API_KEY 和对应 API 地址

# 5. 启动默认依赖服务（Milvus + Neo4j）
docker compose up -d

# 6. 验证各服务连接（浏览器访问）
# http://localhost:7474 — Neo4j Browser (neo4j/pa55w0rd)

# 7. 启动 FastAPI 后端
uv run uvicorn backend.app.main:app --reload --port 8000
```

可选：启动 Attu 管理界面。

```bash
docker compose --profile vector up -d attu
```

新开终端启动前端：

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

可选：运行原 CrewAI Flow 终端 pipeline。

```bash
uv run python main.py
```
