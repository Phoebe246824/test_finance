# Sentinel Edge 文档导览

> 所属项目：[AGENTS.md](../AGENTS.md)

本目录同时服务两类读者：人类开发者和编码智能体。阅读顺序建议先看当前事实入口，再看专题文档，最后查看历史报告。

## 当前事实入口

| 目标 | 文档 |
|---|---|
| 快速了解项目、启动前后端 | [../README.md](../README.md) |
| 开发环境搭建 | [setup.md](setup.md) |
| 常用命令 | [commands.md](commands.md) |
| 架构边界与模块职责 | [architecture.md](architecture.md) |
| 环境变量、端口和默认凭证 | [env-vars.md](env-vars.md) |
| 测试规范 | [testing.md](testing.md) |
| 已知陷阱 | [pitfalls.md](pitfalls.md) |
| 禁止事项 | [restrictions.md](restrictions.md) |

## 赛题与参赛材料

新增赛题资料位于本目录根部：

| 材料 | 用途 |
|---|---|
| [2026第二十一届研电赛赛题指南及清单.pdf](2026第二十一届研电赛赛题指南及清单.pdf) | 官方完整赛题指南 |
| [2026第二十一届研电赛赛题指南及清单_节选.md](2026第二十一届研电赛赛题指南及清单_节选.md) | 已抽取的 AMD 相关赛题和关键评分要求 |
| [2026第二十一届研电赛赛题指南及清单_节选.pdf](2026第二十一届研电赛赛题指南及清单_节选.pdf) | AMD 相关节选 PDF |
| [competition_plan.md](competition_plan.md) | Sentinel Edge 对 AMD 端侧 AI 智能体赛题的参赛定位 |
| [competition_paper_outline.md](competition_paper_outline.md) | 技术论文大纲 |
| [competition_ppt_outline.md](competition_ppt_outline.md) | 演示 PPT 大纲 |
| [demo_script.md](demo_script.md) | 演示讲稿和流程 |

当前项目对齐的赛题是 AMD “基于 AMD 锐龙 AI MAX+ 平台的端侧 AI 智能体与垂直行业创新应用”，行业方向为金融风控。文档和代码说明应围绕本地推理、隐私保护、GPU/NPU/CPU 异构利用、端到端应用闭环展开。

## 当前运行主线

1. `docker compose up -d` 启动 Milvus、Neo4j、etcd、MinIO 等默认依赖。
2. `uv run uvicorn backend.app.main:app --reload --port 8000` 启动 FastAPI 后端。
3. `cd frontend && npm run dev` 启动 Vue3 前端。
4. 可选运行 `uv run python main.py` 使用原 CrewAI Flow 终端 pipeline。
5. 可选运行 `uv run python scripts/sentinel_competition_demo.py` 生成参赛演示报告。

默认端口和凭证以 [.env.example](../.env.example) 与 [env-vars.md](env-vars.md) 为准。Attu 默认使用 `8002`，FastAPI 默认使用 `8000`。

## 历史规划与报告

`docs/reports/`、`*_report.md`、`fullstack_roadmap.md`、`fullstack_fastapi_vue3_plan.md` 记录开发过程和阶段性计划。它们可以解释“为什么这样做”，但不一定代表最新启动方式。最新启动命令以 README、setup、commands 为准。
