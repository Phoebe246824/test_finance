# 3 分钟演示视频脚本

## 0:00-0:20 场景开场

展示标题：Sentinel Edge，基于 AMD Ryzen AI MAX+ 的端侧金融风险智能体。说明客户交易、账户关系和贷前资料在本地处理，不上传银行隐私数据。

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

输入 `finance_01_low_risk_salary_stash` 或一条正常工资入账/日常消费事件，展示未命中金融风险关键词后写入 Milvus events collection，形成客户正常行为基线。

## 1:40-2:30 高风险触发与历史回捞

输入 `finance_04_aml_high_risk_recall`。展示系统完成分类、单条构图、首次风险评估，然后从 Milvus events collection 回捞同一客户 P102 的历史分拆转账线索并批量补图。

## 2:30-2:50 二次研判与趋势分析

展示二次风险分、关联上下文和 Dashboard Agent 输出的反洗钱调查摘要、可疑证据点和处置建议。

## 2:50-3:00 收束

展示本地日志、JSON 报告、资源监控片段。强调金融隐私不出本机、GPU/NPU 可加速、本地交易知识库可持续沉淀。
