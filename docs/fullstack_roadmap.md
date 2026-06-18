# Sentinel Edge 全栈改造路线图

这份路线图按“先跑通，再变好看，再变稳定”的顺序来。不要一开始就追求大而全，先做一个能演示的闭环。

## 最终要做成什么

一个金融风控 Web 应用：

1. 用户在网页里输入一条交易/客户事件。
2. 后端调用 Sentinel pipeline 分析风险。
3. 页面展示风险等级、风险分数、命中原因、关联历史交易、知识图谱摘要和处置建议。
4. 管理员可以维护金融黑名单关键词、客户黑名单和高危事件样本。
5. 演示时能看到本地模型、Milvus、Neo4j、Redis 和 AMD 硬件画像。

## 第 1 阶段：先让后端稳定跑起来

目标：命令行 Demo 不报错。

需要做：

- 修好 Docker 服务：Redis、Milvus、Neo4j 必须是 `Up` 或 `healthy`。
- 重建 Python 3.13 环境，因为当前 Python 3.14 会让 CrewAI/ChromaDB 导入失败。
- 确认本地 LLM endpoint 可用，例如 Ollama 或 LM Studio 的 OpenAI-compatible API。
- 运行金融种子：

```bash
python scripts/reset_and_seed_blacklist.py
```

- 运行金融 Demo：

```bash
python scripts/sentinel_competition_demo.py --run-pipeline
```

完成标准：能得到一个 `output/competition/sentinel_edge_demo_report.json`，里面有金融用例结果。

## 第 2 阶段：把 pipeline 包成 API

目标：前端不用直接跑脚本，而是请求后端接口。

建议新增接口：

- `POST /api/analyze`
  - 输入：`text`
  - 输出：`event_id`、`risk_level`、`risk_score`、`reasoning`、`matched_keywords`、`related_events`
- `GET /api/events`
  - 查看最近分析记录
- `GET /api/events/{event_id}`
  - 查看单条事件详情
- `POST /api/blacklist/keywords`
  - 增加金融风险关键词
- `GET /api/system/health`
  - 查看 Redis、Milvus、Neo4j、本地 LLM 是否可用
- `GET /api/system/hardware`
  - 返回 AMD/GPU/NPU/模型配置画像

技术选择：

- 后端继续用 FastAPI。
- 先复用现在的 `dashboard.py`，不要另起一套复杂后端。
- 分析结果可以先存 JSON 文件或 SQLite，后面再换 PostgreSQL。

## 第 3 阶段：做一个简单清楚的前端

目标：评委打开网页就知道这个系统在干什么。

建议页面：

- **风险分析页**：一个输入框、一个“开始分析”按钮、结果面板。
- **事件列表页**：按时间查看历史分析记录。
- **事件详情页**：展示风险分、命中规则、关联历史、模型解释。
- **黑名单管理页**：维护关键词、客户编号、高危事件样本。
- **系统状态页**：展示 Milvus/Neo4j/Redis/LLM/硬件画像。

技术选择：

- 如果想快：用现有 FastAPI + Jinja2 模板。
- 如果想更像正式全栈项目：React/Vite + FastAPI。
- 先不要做登录注册，比赛 Demo 阶段可以用一个简单的管理口令。

## 第 4 阶段：做比赛展示增强

目标：让作品看起来“确实用到了端侧 AI 和 AMD 平台”。

需要补：

- 性能记录：每个阶段耗时，例如标准化、分类、构图、检索、风险评估。
- 硬件状态：GPU/NPU 是否检测到，当前模型名称，推理 endpoint。
- 资源监控截图：内存、GPU、CPU 占用。
- 对比实验：云端/CPU 基线 vs 本地 GPU 量化模型。
- 隐私说明：客户编号脱敏、日志脱敏、数据不出内网。

## 推荐开发顺序

1. 修 Docker + Python 环境。
2. 跑通 `finance_demo_cases.py` 三个默认用例。
3. 新增 `POST /api/analyze`。
4. 做一个最简单的网页输入框和结果展示。
5. 增加系统状态页。
6. 增加黑名单管理页。
7. 补性能统计和演示视频素材。

## 你现在最该做的三件事

1. 让 Milvus 变成 healthy。
2. 换到 Python 3.13 环境。
3. 用金融 Demo 跑出第一份完整 JSON 报告。
