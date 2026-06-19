# PPT 数据采集证据包设计

日期：2026-06-19

## 背景

`docs/competition_ppt_outline.md` 已经把决赛 PPT 需要替换为实测值的示例数据集中列出，尤其是 P8、P10、P11、P13 的硬件、性能、对比实验和 Demo 证据。当前仓库已有 `scripts/sentinel_competition_demo.py`，可以运行 10 条金融 Demo 用例并生成 JSON 报告；`sentinel_edge.metrics.BenchmarkRecorder` 能记录整条 case 的耗时；`sentinel_edge.hardware.collect_hardware_profile()` 能发现基础硬件环境。

缺口在于：现有报告还没有面向 PPT 的聚合指标、CSV、PNG 图表、运行时 GPU/显存/功耗采样，也没有把手工实测的 TTFT、tokens/s、llama.cpp offload 日志和截图路径纳入统一证据包。

本设计的首要目标是服务 PPT 静态数据与图表，不优先支持现场一键长时间复现实测。

## 已确认决策

- 交付目标：先满足 PPT 静态数据表和图表。
- 输出形态：生成 `JSON/CSV`，同时生成 PPT 可直接使用的 `PNG` 图表。
- 硬件与推理指标来源：脚本优先自动采集；自动采不到的字段允许由 sidecar 文件补齐。
- 数据真实性：每个关键字段必须带来源标记，区分 `measured`、`derived`、`sidecar`、`not_available`。
- 实现路线：采用模块化 evidence collector，不把业务 pipeline 改造成性能测试框架。

## 目标

1. 新增一个清晰的 PPT 证据采集边界，围绕现有 Demo case、pipeline 入口、硬件画像和 benchmark 记录做编排。
2. 为 PPT 产出一份 evidence pack，包含原始证据、聚合指标、CSV 明细和 PNG 图表。
3. 将自动采集值、派生计算值、手工补充值和不可用字段明确标注来源。
4. 在非 AMD 环境、ROCm 工具缺失或依赖服务未启动时仍能产出可审计报告，而不是静默失败或伪造数据。
5. 为后续实现详细阶段埋点预留接口，但第一版不做大范围业务流程改造。

## 非目标

- 不在第一版实现完整现场一键复现实测流程。
- 不承诺自动截取前端页面或终端截图；截图路径由 sidecar 记录。
- 不自动采集外部行业报告、监管数据或试点反馈；这些材料可由 sidecar 记录来源和引用。
- 不修改 `graphiti_core/`。
- 不把真实 Milvus、Neo4j、LLM、ROCm 依赖纳入默认测试链路。

## PPT 数据映射

| PPT 页 | 数据需求 | 采集方式 | 产物 |
|---|---|---|---|
| P5 系统总体架构 | 模块数、测试用例数、金融 Demo 用例数 | 静态仓库扫描 + `finance_demo_cases.py` | `ppt_metrics.json` |
| P8 AMD 硬件利用 | 硬件画像、GPU/NPU 可用性、GPU 利用率、VRAM、功耗、llama.cpp offload 日志路径 | `collect_hardware_profile()` + runtime sampler + sidecar | `hardware_samples.csv`、`ppt_metrics.json` |
| P10 本地推理性能 | 端到端延迟均值/P95、TTFT、tokens/s、批量补图耗时、GPU 峰值、VRAM 峰值、阶段耗时拆解图 | case runner + sampler + sidecar + 聚合 | `case_results.csv`、`stage_timings.csv`、`charts/stage_breakdown.png` |
| P11 精度/能效/稳定性对比 | 基线 vs 本地优化模型：通过率、风险等级一致率、平均延迟、平均功耗 | 自动聚合 + sidecar 基线数据 | `ppt_metrics.json`、`charts/baseline_comparison.png` |
| P12 隐私与安全 | 日志脱敏截图、隐私证据路径 | sidecar 记录素材路径和说明 | `evidence.json` |
| P13 Demo 演示 | 选中 case、event_id、日志路径、错误、截图素材路径 | case runner + sidecar | `evidence.json`、`case_results.csv` |
| P14 落地价值 | 研判时间对比、组合风险发现率、试点材料 | sidecar 记录人工确认值和来源 | `ppt_metrics.json` |

## 模块设计

新增包：`sentinel_edge/evidence/`。

`models.py`

- 定义 evidence pack 使用的数据结构。
- 核心概念包括 `MetricValue`、`CaseEvidence`、`HardwareSample`、`PptMetrics`。
- `MetricValue` 至少包含 `value`、`unit`、`source`、`note`，其中 `source` 取值为 `measured`、`derived`、`sidecar`、`not_available`。

`case_runner.py`

- 读取 `scripts.finance_demo_cases.FINANCE_CASES_BY_ID`。
- 运行选定 case，复用 `process_message_detailed()` 或现有 demo runner。
- 记录 `case_id`、`title`、`event_id`、`status`、`risk_level`、`risk_score`、`error`、`case_log_path`、`elapsed_ms`。
- 默认只记录整条 case 耗时；如果后续 pipeline 暴露更细 span，则按同一 schema 写入 `stage_timings.csv`。

`hardware_sampler.py`

- 复用 `collect_hardware_profile()` 生成启动时硬件画像。
- 在 pipeline 运行期间按固定间隔尝试采样 `rocm-smi`。
- 采集字段包括 GPU 利用率、显存占用、功耗；命令不存在或字段不可解析时写 `not_available`。
- NPU 默认只记录可用性和工具输出摘要，不虚报 NPU 推理负载。

`sidecar.py`

- 读取人工补充文件，用于合并自动采不到的数据。
- 支持记录 TTFT、tokens/s、平均功耗、基线模型结果、llama.cpp offload 日志路径、截图路径、外部引用来源。
- 与自动采集冲突时默认保留自动采集值；仅当 sidecar 字段显式允许覆盖时才替换，并在 `note` 中记录覆盖来源。

`aggregator.py`

- 计算端到端延迟均值、P95、成功数、失败数、通过率、风险等级一致率。
- 从硬件采样中计算 GPU 利用率峰值、VRAM 峰值、功耗均值。
- 按 PPT 页码组织 `ppt_metrics.json`，让 PPT 制作时可以直接查字段。

`charts.py`

- 生成 PPT 可直接使用的 PNG。
- 第一版图表包括阶段耗时拆解、case 延迟分布、基线 vs 本地优化对比。
- 缺少数据时生成可审计的空状态图，图中说明对应指标不可用，避免误导。

`writer.py`

- 写出 evidence pack 的目录结构和所有 JSON/CSV/PNG。
- 保证输出文件名稳定，便于 PPT 文档引用。

## CLI 设计

新增脚本：`scripts/collect_ppt_evidence.py`。

建议命令形态：

```bash
uv run python scripts/collect_ppt_evidence.py --run-pipeline
uv run python scripts/collect_ppt_evidence.py --run-pipeline --case finance_04_aml_high_risk_recall
uv run python scripts/collect_ppt_evidence.py --sidecar docs/competition/evidence_sidecar.yaml
uv run python scripts/collect_ppt_evidence.py --output-dir output/competition/evidence/manual_run
```

关键参数：

- `--run-pipeline`：执行真实 pipeline；未开启时只生成环境画像、sidecar 合并结果和可用图表。
- `--case`：可重复传入，默认使用 10 条金融 Demo 用例。
- `--sidecar`：读取人工补充数据。
- `--sample-interval`：硬件采样间隔，默认 1 秒。
- `--output-dir`：指定输出目录；未指定时使用时间戳目录。

## 输出结构

默认输出到 `output/competition/evidence/<timestamp>/`。

```text
output/competition/evidence/<timestamp>/
├── evidence.json
├── ppt_metrics.json
├── case_results.csv
├── stage_timings.csv
├── hardware_samples.csv
├── charts/
│   ├── stage_breakdown.png
│   ├── case_latency.png
│   └── baseline_comparison.png
└── logs/
    ├── 00_run.log
    └── <case>.log
```

`evidence.json` 保存完整原始证据和素材路径。

`ppt_metrics.json` 面向 PPT 使用，按页码组织关键值，例如 `p10.end_to_end_latency_mean_ms`、`p10.end_to_end_latency_p95_ms`、`p10.gpu_peak_util_percent`、`p11.optimized.pass_rate`。

CSV 文件用于图表复核和人工二次整理。

## Sidecar 规则

sidecar 是自动采集的补充，不是默认事实来源。

支持内容：

- 本地 llama.cpp 实测的 TTFT、tokens/s、offload 日志路径。
- 基线模型与本地优化模型对比数据。
- 功耗计或外部监控工具记录的平均功耗。
- PPT 截图素材路径。
- P12/P14 所需的人工确认材料来源。

合并规则：

1. 自动采集字段优先。
2. sidecar 可补齐自动采集为 `not_available` 的字段。
3. sidecar 只有显式允许覆盖时才能替换自动采集字段。
4. 所有 sidecar 值的 `source` 必须写为 `sidecar`。
5. 报告保留 sidecar 文件路径和读取时间，保证可追溯。

## 错误处理

- `--run-pipeline` 未开启：`pipeline_executed=false`，不生成 case 成功率结论。
- 单个 case 失败：该 case 写入 `error`，聚合延迟时排除失败 case，同时在通过率和失败数中体现。
- 依赖服务不可用：记录失败 case 和异常摘要，证据包仍写出。
- `rocm-smi` 不存在：硬件采样字段写 `not_available`，硬件画像保留已有 notes。
- `rocm-smi` 输出格式不兼容：保存原始命令摘要，解析字段写 `not_available`。
- sidecar 格式错误：CLI 失败并指出文件路径和字段位置，避免生成混合了错误人工数据的报告。
- 图表数据不足：生成空状态 PNG，并在 `ppt_metrics.json` 写清不可用原因。

## 测试策略

默认测试只覆盖纯逻辑和可控 I/O。

单元测试：

- `MetricValue` 来源标记序列化。
- sidecar 合并规则，包括补齐、冲突保留、显式覆盖。
- 均值、P95、通过率、风险等级一致率计算。
- `rocm-smi` 样例输出解析。
- 缺失硬件工具时的 `not_available` 行为。

文件输出测试：

- 使用临时目录生成 `evidence.json`、`ppt_metrics.json`、CSV 和 PNG。
- 验证 PNG 文件存在且非空。
- 验证 `ppt_metrics.json` 包含 P5、P8、P10、P11、P12、P13、P14 的顶层键。

手动验证命令：

- `uv run python scripts/collect_ppt_evidence.py`
- `uv run python scripts/collect_ppt_evidence.py --run-pipeline --case finance_04_aml_high_risk_recall`
- 在 AMD 环境中运行带 `--run-pipeline` 的完整 10 case 采集，并检查 `hardware_samples.csv` 是否有 GPU/VRAM 数据。

## 验收标准

1. 运行默认 CLI 能生成 evidence pack 目录。
2. `ppt_metrics.json` 按 PPT 页码组织关键指标，并为缺失字段写明 `not_available`。
3. `case_results.csv` 能列出每个 case 的状态、耗时、风险等级和错误。
4. `charts/` 至少生成阶段耗时、case 延迟、基线对比三类 PNG。
5. sidecar 能补齐 TTFT、tokens/s、功耗、截图路径和基线对比数据。
6. 无 ROCm 工具的机器上脚本仍可生成报告，且不会虚报 GPU/NPU 实测。
7. 默认测试不依赖真实 Milvus、Neo4j、LLM 或 AMD 硬件。

## 后续实施顺序

1. 建立 `sentinel_edge/evidence/` 的数据模型、聚合器和 writer。
2. 增加 sidecar 读取与合并。
3. 增加硬件采样器和 `rocm-smi` 解析。
4. 增加 CLI 脚本和输出目录结构。
5. 增加 PNG 图表生成。
6. 为纯逻辑与文件输出补测试。
7. 根据实测报告再决定是否给 `main.py` 增加更细粒度阶段 span。
