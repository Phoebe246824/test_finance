# 基于端侧 AI 的银行零售反欺诈与反洗钱风险多智能体预警系统

> 本文件是论文总稿入口。每一章已拆分存放在 `docs/paper/chapters/` 下，后续补图、补表、补实验数据时优先修改对应章节文件。图表绘制说明见 [figure_table_guide.md](figure_table_guide.md)。

## 章节文件

1. [封面、摘要与关键词](chapters/00_front_matter.md)
2. [第 1 章 引言](chapters/01_introduction.md)
3. [第 2 章 行业背景与问题定义](chapters/02_problem_definition.md)
4. [第 3 章 系统总体架构](chapters/03_architecture.md)
5. [第 4 章 多智能体工作流与模型设计](chapters/04_multi_agent_design.md)
6. [第 5 章 关系图谱、向量召回与风险评分方法](chapters/05_methods.md)
7. [第 6 章 AMD 锐龙 AI MAX+ 平台适配与异构资源利用](chapters/06_amd_platform.md)
8. [第 7 章 系统功能实现与端到端 Demo](chapters/07_system_implementation.md)
9. [第 8 章 实验设计与结果分析](chapters/08_experiments.md)
10. [第 9 章 隐私安全、应用价值与未来工作](chapters/09_security_value_future.md)
11. [第 10 章 结论](chapters/10_conclusion.md)
12. [参考文献](chapters/references.md)

## 必要图表清单

### 必要图

| 图编号 | 图名 | 所在章节 | 图的用途 |
|---|---|---|---|
| 图 1 | Sentinel Edge 系统总体架构图 | 第 3 章 | 说明前端、后端、智能体、数据库、模型和 AMD 硬件的整体关系 |
| 图 2 | 端到端金融事件分析流程图 | 第 3 章 | 说明从事件输入到复核动作的完整流程 |
| 图 3 | 金融事件关系图谱数据模型 | 第 5 章 | 说明 RiskEvent、Customer、Account、Merchant、Device、RiskSignal 等节点和关系 |
| 图 4 | 事件详情与人物关系图谱交互示例 | 第 5 章 | 展示最终系统最有视觉冲击力的图谱效果 |
| 图 5 | 低风险暂存与高风险回捞流程图 | 第 5 章 | 说明本文的关键创新机制 |
| 图 6 | Sentinel Edge 风险分析与事件详情界面 | 第 7 章 | 展示系统已经完成端到端应用，而不是只跑模型 |
| 图 7 | 平均端到端延迟对比图 | 第 8 章 | 展示 CPU/GPU/NPU 或量化优化带来的性能变化 |
| 图 8 | CPU/GPU/NPU 资源使用率曲线图 | 第 8 章 | 展示 AMD 异构资源利用情况 |

### 必要表

| 表编号 | 表名 | 所在章节 | 表的用途 |
|---|---|---|---|
| 表 1 | 传统云端大模型方案与端侧 AI 风控方案对比 | 第 2 章 | 支撑端侧部署必要性 |
| 表 2 | 系统数据组件分工 | 第 3 章 | 说明 Redis、Milvus、Neo4j、SQLite 的职责 |
| 表 3 | 多智能体职责划分 | 第 4 章 | 说明 5 个 CrewAI Agent 与工具服务的边界 |
| 表 4 | 多维风险评分维度与权重 | 第 5 章 | 说明 risk_score 如何计算 |
| 表 5 | AMD 锐龙 AI MAX+ 平台硬件任务分工 | 第 6 章 | 对应比赛硬件利用要求 |
| 表 6 | 本地推理组件配置 | 第 6 章 | 说明 LLM、Embedding、Rerank、NPU 预筛部署 |
| 表 7 | 端到端 Demo 演示步骤 | 第 7 章 | 方便写论文和录制演示视频 |
| 表 8 | 金融 Demo case 功能正确性测试结果 | 第 8 章 | 展示系统功能覆盖情况 |
| 表 9 | 风险识别效果评估结果 | 第 8 章 | 展示识别准确性和可用性 |
| 表 10 | 不同硬件配置下的性能与能效对比 | 第 8 章 | 展示性能和功耗 |
| 表 11 | 模型量化前后效果与性能对比 | 第 8 章 | 对应比赛精度/性能权衡要求 |
| 表 12 | 消融实验结果 | 第 8 章 | 证明黑名单、向量回捞、图谱等模块的价值 |
