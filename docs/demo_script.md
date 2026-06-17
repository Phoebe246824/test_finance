# 3 分钟演示视频脚本

## 0:00-0:20 场景开场

展示标题：Sentinel Edge，基于 AMD Ryzen AI MAX+ 的端侧企业风险智能体。说明数据在本地处理，不上传内部事件记录。

## 0:20-0:50 环境与硬件

运行：

```bash
uv run python scripts/sentinel_competition_demo.py
```

展示生成的 `output/competition/sentinel_edge_demo_report.json`，重点标出目标平台、GPU/NPU 后端、本地 LLM endpoint 和模型名称。

## 0:50-1:40 低风险暂存

运行主程序：

```bash
uv run python main.py
```

输入低风险历史事件，展示未命中黑名单后写入 Milvus 暂存池，不进入高成本构图流程。

## 1:40-2:30 高风险触发与历史回捞

输入高风险事件，例如 `case_07c_p06_high_risk`。展示系统完成分类、单条构图、首次风险评估，然后从 Milvus 回捞同一人员历史事件并批量补图。

## 2:30-2:50 二次研判与趋势分析

展示二次风险分、关联上下文和 Dashboard Agent 输出的意图分析/趋势预测。

## 2:50-3:00 收束

展示本地日志、JSON 报告、资源监控片段。强调隐私不出本机、GPU/NPU 可加速、本地知识库可持续沉淀。
