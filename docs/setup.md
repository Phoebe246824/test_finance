> 所属项目：[AGENTS.md](../AGENTS.md)

## 开发环境搭建

### 前置依赖

- **Python**: 3.13+
- **uv**: 0.11+（依赖管理与脚本运行器，安装方式见 https://docs.astral.sh/uv/）
- **Docker** + Docker Compose（用于启动 Neo4j、RabbitMQ、Milvus）
- **Git**

### 初始化步骤

```bash
# 1. 克隆仓库
git clone <repo-url> && cd test_Sentinel

# 2. 创建虚拟环境
uv venv

# 3. 安装 Python 依赖
uv pip install -r requirements.txt

# 4. 配置环境变量
cp .env.example .env
# 编辑 .env，至少填入 LLM_API_KEY 和对应 API 地址

# 5. 启动依赖服务（Neo4j + RabbitMQ + Milvus）
docker compose up -d

# 6. 验证各服务连接（浏览器访问）
# http://localhost:7474 — Neo4j Browser (neo4j/pa55w0rd)
# http://localhost:15672 — RabbitMQ Management (root/pa55w0rd)
# http://localhost:9091/webui/ — Milvus WebUI

# 7. 运行系统
uv run python main.py
```
