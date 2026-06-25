# Sentinel Edge 竞赛 Slide TODO

这份文件只给制作者使用，不应把其中任何“待办、占位、替换、采集路径、最终提交前检查”等文字写进观众可见的 slide。

## 当前 demo 到最终提交的必做事项

| 状态 | 任务 | 产物 | 答辩 slide 运用方式 | 注意事项 |
|---|---|---|---|---|
| [ ] | 截取 Dashboard 总览页真实画面 | Dashboard PNG | 用于 P1 封面右侧主视觉，作为“这是当前 Web 主线真实系统”的第一眼证据 | 必须来自当前 Web 主线 `backend/app/main.py` + `frontend/`，不要使用旧工作汇报图 |
| [ ] | 截取 Analyze 风险分析结果 | Analyze PNG | 用于 P10 端到端 Demo 页的“二次研判/复核建议”画面，展示风险等级、维度分与趋势报告如何进入人工复核 | 建议用 `finance_04`，展示风险等级、维度分、趋势报告 |
| [ ] | 截取 EventDetail / PersonGraph 图谱 | Graph PNG | 用于 P6 核心创新页或 P10 Demo 页，替换纯文字图谱说明，证明 P102 历史线索能被回捞并形成关系证据 | 展示 P102 与账户、设备、历史事件关系，需要 Neo4j 数据准备完毕 |
| [ ] | 在 AMD 机采集 `rocm-smi` 运行截图 | GPU resource PNG | 用于 P8 AMD 硬件利用页右侧证据区，证明推理时 Radeon GPU 有真实资源占用 | 推理过程中截 GPU 利用率、显存、功耗/温度，保留命令与时间戳 |
| [ ] | 在 AMD 机采集 llama.cpp ROCm offload 日志 | Offload log PNG | 用于 P8 AMD 硬件利用页，与 `rocm-smi` 并列，证明核心 LLM 推理实际 offload 到 ROCm/HIP GPU 后端 | 需要包含 `--n-gpu-layers`、ROCm/HIP 后端、模型量化格式、tokens/s 或 TTFT |
| [ ] | 生成阶段耗时拆解图 | Stage breakdown PNG | 用于 P9 性能、能效与证据页，替换当前示意条形图，说明瓶颈来自标准化、过滤、分类、构图还是二次研判 | 用真实 evidence collector / Plotly 数据替换 demo 中的示意条形图 |
| [ ] | 生成原始模型 vs 本地量化模型对比图 | Baseline comparison PNG | 用于 P9 性能页或其拆分页，展示 INT4/Q4_K_M 在精度、延迟、吞吐、功耗之间的取舍 | 包含延迟、吞吐、功耗、风险等级一致率 |
| [ ] | 准备脱敏前后日志或字段对比截图 | Privacy PNG | 用于 P11 隐私与安全页，作为“脱敏 + 最小权限访问”的可视化证据，支撑 P101/P102 脱敏编号叙事 | 不暴露真实身份证、卡号、手机号；可使用 P101/P102 等脱敏编号 |
| [ ] | 准备落地价值指标图表 | Value metrics PNG | 用于 P12 落地价值页左侧“价值指标图表区”，集中展示研判耗时、历史线索召回、风险等级一致性、人工复核命中等指标 | 没有真实业务数值前只保留图表区域，不要编造百分比、分钟数或用户反馈 |
| [ ] | 准备业务验证或合作意向材料 | Validation evidence PNG / text | 用于 P12 底部“证据形态”口径或最终答辩补充页，支撑可落地性与试点验证/用户反馈/合作意向分项 | 只有拿到真实材料才写进观众 slide；没有材料时只在 TODO 中保留这项 |
| [ ] | 截取 3 分钟演示视频关键帧 | Video keyframes | 用于 P10 Demo 页四段流程缩略图，也可在最终视频脚本中与 slide 顺序对齐，保证现场讲解和视频画面一致 | 至少包含系统状态、低风险暂存、高风险回捞、二次研判、资源监控 |
| [ ] | 用 AMD 本机报告替换样例性能数据 | JSON / CSV / chart | 用于 P8-P9 的指标表、图表和讲者证据口径，正式稿只展示提炼后的关键数值，完整报告作为备查材料 | 当前 `output/competition/sentinel_edge_demo_report.json` 是样例格式证明，不可作为正式硬件性能证据 |
| [ ] | 明确 NPU 口径 | slide 文案 | 用于 P8 硬件分工页，决定 NPU 卡片写成“已落地低功耗预筛”还是“下一阶段扩展方向”，避免硬件利用表述失真 | 若 NPU 未落地，只能写规划方向，不能暗示已完成 |
| [ ] | 全文清理制作者提醒 | HTML / PPTX | 用于最终导出前的全 deck 内容闸门，确保观众页只出现结论、方法、证据和价值，不出现制作过程语言 | 搜索并移除：占位、待补、待测、TODO、替换、采集、not-detected、样例报告等观众不应看到的词 |
| [ ] | 导出 PPTX / PDF 前做视觉检查 | PNG snapshots | 用于最终交付前的版面验收记录，重点检查 P1、P8、P9、P10、P11、P12、P13 等证据密集页 | 检查 16:9、文字不溢出、图不遮挡、每页逻辑清楚 |

## 当前样例报告说明

`output/competition/sentinel_edge_demo_report.json` 只能证明报告结构和金融用例链路格式已经跑通。该报告显示 `gpu_backend=not-detected` 且 endpoint 为外部 API，因此不能作为正式答辩中的 AMD 本机性能或硬件利用证据。正式提交前必须在 AMD Ryzen AI MAX+ 环境重跑并替换相关图表与数值。

## 当前预期数据图说明

当前 `index.html` 中 P8-P12 已先用预期/目标数据绘制了图表与演示缩略画面，用于汇报时说明预期证据形态和最终版画面布局：

- P8：llama.cpp 启动示例已换成实际 `llama-server` ROCm 日志；GPU 资源曲线后续仍需用 AMD 本机 `rocm-smi` 截图覆盖。
- P9：阶段耗时拆解与原始模型 vs INT4/Q4_K_M 对比图，后续用 evidence collector 或 Plotly 的实测 CSV/JSON 覆盖。
- P10：四段演示缩略画面，后续用真实 Dashboard / Analyze / Graph / System Status 截图覆盖。
- P11：脱敏字段对比图，后续用真实日志或接口字段截图覆盖，但必须继续保持 P101/P102 等脱敏编号。
- P12：业务价值预期指标图，后续只有拿到真实测量、用户验证或合作意向材料后，才能改为实测值或正式价值结论。

## Slide 内容边界

- Slide 给评委和观众看，只呈现已经可以公开讲述的结论、方法、指标框架和系统价值。
- TODO 给制作者看，记录缺图、缺数据、替换计划、采集路径和风险提醒。
- 最终导出前必须用文本搜索确认观众版 slide 不包含制作过程提示。
