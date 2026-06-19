# test_finance / Sentinel Edge 金融风控智能体

Sentinel Edge 是面向比赛场景改造的端侧金融风控智能体项目。系统围绕银行零售业务中的反欺诈、反洗钱、贷款欺诈和可疑交易复核展开，提供事件分析、黑名单过滤、风险评分、Neo4j 图谱展示、趋势预测报告和人工复核闭环。

GitHub 仓库：

```text
https://github.com/Phoebe246824/test_finance
```

## 1. 项目能做什么

- 输入一段金融风险事件文本，自动完成黑名单过滤、事件分类、风险评估和趋势预测。
- 未命中高危规则的事件按低风险展示，并暂存到 Milvus，后续可被高风险事件回捞。
- 命中黑名单或高危规则的事件进入完整 pipeline，写入 Neo4j 图谱并生成风险结果。
- 前端提供总览、风险分析、事件库、人物图谱、黑名单管理和系统状态页面。
- 所有图谱页面统一使用可拖拽、可缩放、可展开的 Neo4j 风格关系图组件，支持节点/边属性查看。
- 黑名单页面会自动初始化金融 Demo 所需的人员、关键词和高危事件样本。
- 事件详情页支持交互式图谱、趋势预测报告和人工复核动作。

## 2. 技术栈

后端：

- Python 3.13
- FastAPI
- CrewAI
- Redis
- Milvus
- Neo4j / Graphiti
- SQLite

前端：

- Vue 3
- Vite
- Pinia
- Vue Router
- Axios

## 3. 目录说明

```text
test_finance/
├── backend/                 # FastAPI 后端
│   └── app/api/             # analysis/events/graph/blacklist/dashboard/system API
├── frontend/                # Vue3 前端
├── blacklist/               # Redis 黑名单与 Milvus 暂存逻辑
├── graphiti/                # Neo4j/Graphiti 图谱工作流
├── trend_prediction/        # 意图分析与趋势预测提示词
├── scripts/                 # Demo case、初始化脚本、比赛报告脚本
├── tests/                   # 单元测试
├── docs/                    # 项目文档
├── main.py                  # 原 Sentinel pipeline 主入口
├── docker-compose.yaml      # Redis/Milvus/Neo4j/RabbitMQ
├── pyproject.toml           # Python 依赖
└── README.md
```

文档入口见 [docs/README.md](docs/README.md)。新增赛题资料已放入 `docs/`，其中 [docs/2026第二十一届研电赛赛题指南及清单_节选.md](docs/2026第二十一届研电赛赛题指南及清单_节选.md) 提取了 AMD 端侧 AI 智能体赛题要求、提交材料和评分标准。

项目当前对齐 AMD “基于 AMD 锐龙 AI MAX+ 平台的端侧 AI 智能体与垂直行业创新应用”赛题，金融风控是垂直行业场景。后续论文、PPT、演示脚本应围绕本地推理、隐私保护、GPU/NPU/CPU 异构利用、端到端应用闭环来组织。

## 4. 运行前准备

需要提前安装：

- Python 3.13
- Node.js 20+
- Docker Desktop
- uv

检查命令：

```bash
python3 --version
node --version
npm --version
docker --version
uv --version
```

## 5. 配置环境变量

进入项目目录：

```bash
git clone https://github.com/Phoebe246824/test_finance.git
cd test_finance
```

复制环境变量文件：

```bash
cp .env.example .env
```

重点检查 `.env` 里的这几项：

```text
LLM_MODEL=qwen3.5
LLM_API_KEY=ollama
LLM_BASE_URL=http://127.0.0.1:11434/v1

EMBEDDER_MODEL=BAAI/bge-m3
EMBEDDER_API_BASE=http://127.0.0.1:1234/v1

NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=pa55w0rd

REDIS_HOST=localhost
REDIS_PORT=6379

MILVUS_URI=http://127.0.0.1:19530
ATTU_PORT=8002

VITE_API_BASE_URL=http://127.0.0.1:8000
```

如果你本地 Neo4j 密码不是 `pa55w0rd`，需要同步修改 `.env`。

前端变量放在 `frontend/.env`，推荐内容：

```text
VITE_API_BASE_URL=http://127.0.0.1:8000
```

也可以直接复制前端示例：

```bash
cp frontend/.env.example frontend/.env
```

## 6. 安装 Python 依赖

```bash
uv sync --dev
```

如果你的电脑没有 `uv`，可以先安装：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## 7. 启动基础服务

启动 Redis、Milvus、Neo4j、RabbitMQ：

```bash
docker compose up -d
```

查看容器状态：

```bash
docker compose ps
```

常用控制台：

```text
Neo4j Browser: http://localhost:7474
Milvus Attu:   http://localhost:8002
RabbitMQ UI:   http://localhost:15672
```

注意：FastAPI 使用 `127.0.0.1:8000`，Attu 默认使用 `localhost:8002`，两者不要映射到同一个宿主机端口。

## 8. 初始化黑名单种子数据

```bash
uv run python scripts/reset_and_seed_blacklist.py
```

这个脚本会重置 Neo4j/Milvus 相关状态并写入金融 Demo 用到的人员黑名单、关键词和高危事件样本。

如果只打开前端黑名单页面，后端也会自动补齐默认黑名单种子数据，不需要手动新增。

Demo case 在：

```text
scripts/finance_demo_cases.py
```

## 9. 启动后端

```bash
uv run uvicorn backend.app.main:app --reload --port 8000
```

后端接口文档：

```text
http://127.0.0.1:8000/docs
```

健康检查：

```text
http://127.0.0.1:8000/api/system/health
```

## 10. 启动前端

打开新终端：

```bash
cd frontend
npm install
npm run dev
```

浏览器打开：

```text
http://localhost:5173
```

如果 Vite 自动切到 `5174`，后端 CORS 已放行 `localhost/127.0.0.1:5173` 和 `5174`。

如果 npm 因为本机缓存权限失败，可以使用项目内缓存：

```bash
npm_config_cache=./.npm-cache npm install
npm_config_cache=./.npm-cache npm run dev
```

## 11. 前端页面

```text
/dashboard       风控总览
/analysis        风险分析
/events          事件库
/events/:id      事件详情
/graph/person    人物图谱
/blacklist       黑名单管理
/system          系统状态
```

推荐演示顺序：

1. 打开 `/dashboard` 看整体状态。
2. 打开 `/blacklist` 确认黑名单种子存在。
3. 打开 `/analysis` 粘贴金融 Demo case。
4. 分析完成后查看风险等级、命中详情、图谱和趋势报告。
5. 打开 `/events` 进入事件详情。
6. 在详情页点击图谱节点、扩展节点，并添加人工复核动作。
7. 打开 `/graph/person` 搜索 `客户E` 或 `P105`，查看人物关系图谱。

## 12. 风险展示规则

当前前端和总览页统一使用：

```text
高风险：risk_score >= 0.70
中风险：0.35 <= risk_score < 0.70
低风险：risk_score < 0.35
未命中高危规则的 STASH 事件：按低风险展示
```

也就是说，未命中高危规则不会显示“待评估”。

图谱展示规则：

```text
节点：显示 Neo4j labels、elementId、uuid 和 properties
边：显示 Neo4j relationship type、elementId、uuid、start/end elementId 和 properties
交互：支持缩放、画布拖拽、节点拖拽、节点扩展、全屏
```

## 13. 常用命令

运行比赛 Demo：

```bash
uv run python scripts/sentinel_competition_demo.py
```

运行真实 pipeline Demo：

```bash
uv run python scripts/sentinel_competition_demo.py --run-pipeline
```

运行终端交互：

```bash
uv run python main.py
```

运行测试：

```bash
uv run pytest -q
```

前端构建：

```bash
cd frontend
npm run build
```

## 14. 常见问题

### Milvus 连接失败

报错类似：

```text
Fail connecting to server on localhost:19530
```

处理：

```bash
docker compose ps
docker compose up -d milvus
```

确认 `MILVUS_URI=http://127.0.0.1:19530`。

如果浏览器或 Python 客户端遇到 `localhost` 解析到其他服务，可改成：

```text
MILVUS_URI=http://127.0.0.1:19530
```

### Neo4j 图谱为空

先确认 Neo4j 正常：

```text
http://localhost:7474
```

再确认 `.env`：

```text
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=pa55w0rd
```

如果密码不一致，改 `.env` 后重启后端。

### 前端访问不到后端

确认后端在运行：

```text
http://127.0.0.1:8000/docs
```

如需指定后端地址，在 `frontend/.env` 写：

```text
VITE_API_BASE_URL=http://127.0.0.1:8000
```

### npm install 权限错误

使用项目内缓存：

```bash
cd frontend
npm_config_cache=./.npm-cache npm install
```

## 15. 给队友的最短启动步骤

```bash
git clone https://github.com/Phoebe246824/test_finance.git
cd test_finance
cp .env.example .env
uv sync --dev
docker compose up -d
uv run python scripts/reset_and_seed_blacklist.py
uv run uvicorn backend.app.main:app --reload --port 8000
```

新开一个终端：

```bash
cd test_finance/frontend
cp .env.example .env
npm_config_cache=./.npm-cache npm install
npm_config_cache=./.npm-cache npm run dev
```

打开：

```text
http://localhost:5173
```
