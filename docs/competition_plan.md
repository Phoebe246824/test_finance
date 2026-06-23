# Sentinel Edge 参赛方案

## 作品定位

**Sentinel Edge** 是面向银行零售业务的端侧反欺诈与反洗钱预警智能体。系统在本地 Mini AI 工作站上完成客户交易事件标准化、黑名单过滤、RAG/知识图谱检索、风险评估、历史交易回捞、二次研判和调查摘要生成，强调客户隐私数据不出内网、弱网可运行、低延迟处置。

对应赛题方向：AMD “基于 AMD 锐龙 AI MAX+ 平台的端侧 AI 智能体与垂直行业创新应用”中的金融垂直行业创新应用。官方资料见 [2026第二十一届研电赛赛题指南及清单_节选.md](2026第二十一届研电赛赛题指南及清单_节选.md)。

## 目标用户与痛点

- 目标用户：银行反欺诈分析员、反洗钱调查员、贷前风控专员、网点/远程银行运营人员。
- 当前痛点：交易流水、账户关系、设备信息、客户资料和投诉线索分散在不同系统；人工串联历史线索慢；传统规则容易漏掉“多笔低风险历史 + 当前异常交易”的组合风险。
- 端侧必要性：客户身份、交易流水、账户关系、设备指纹和贷前材料都是高敏感金融数据，适合在银行内网、本地工作站或专网环境中部署；本地推理可以降低合规风险并提升弱网可用性。

## 端到端 Demo 流程

1. 输入一条原始事件文本。
2. Normalizer Agent 将文本标准化为 `NormalizedEvent`。
3. Milvus 黑名单 stores 执行人员、关键词、事件样本三路匹配。
4. 未命中事件写入 Milvus events collection，作为后续客户画像和历史交易上下文。
5. 命中事件进入本地 LLM 分类、Graphiti + Neo4j 构图、混合检索和风险评分。
6. 若首次风险分超过阈值，系统从 Milvus events collection 回捞同客户/同账户/语义相关历史交易，并批量补图。
7. 补图后执行二次检索与二次风险评估。
8. 高风险结果进入 Dashboard Agent，生成意图分析和趋势预测。

链路概览：`输入 → 标准化 → Milvus 黑名单三路过滤 → events collection 暂存/全量入库 → 本地 LLM 分类 → Graphiti+Neo4j 构图 → 混合检索 → 多维风险评分 → 超阈值则从 Milvus events 同人员+语义召回 → 批量补图 → 二次研判 → Dashboard Agent 摘要`。

## AMD 硬件分工

- GPU / Radeon 8060S：承载本地 LLM 推理、Embedding 生成、Rerank 或向量检索相关高吞吐任务。建议通过 ROCm、LM Studio、Ollama、vLLM 或 llama.cpp 的 AMD 后端运行量化模型。
- NPU / Ryzen AI：承载低功耗持续任务，例如轻量交易风险预筛、关键词/设备异常预警、网点语音转写小模型或后台监控模型。当前代码提供 `sentinel_edge.hardware` 环境探测和报告字段，接入 Ryzen AI SDK 后可在报告中留下 NPU 后端证据。
- CPU：负责 CrewAI Flow 调度、Milvus/Neo4j 访问、规则过滤、JSON 解析、日志和报告生成。
- 统一内存：适合同时运行 LLM、Embedding、知识图谱和向量库工作负载，减少多模型并发时的显存瓶颈。

## 本地模型建议

- LLM：Qwen2.5-14B-Instruct、Qwen3-14B、DeepSeek-R1-Distill-Qwen-14B 的 INT4/INT8 量化版本。
- Embedding：BAAI/bge-m3 或 bge-large-zh，本地 OpenAI-compatible endpoint 优先。
- Rerank：BAAI/bge-reranker-v2-m3，可作为可选增强；未配置时系统会跳过非同人候选精排。

## 性能与精度实验设计

- 模型对比：FP16 或云端基线 vs INT4/INT8 本地量化模型。
- 指标：端到端延迟、首 token 延迟、每秒 token、单条事件处理耗时、批量补图耗时、CPU/GPU/NPU 占用、内存占用。
- 精度：金融 Demo 用例通过率、风险等级一致率、历史回捞命中率、误召回过滤率、调查摘要证据覆盖率。
- 能效：记录同一批用例在不同模型和后端下的平均功耗、峰值功耗和处理时长。

## 隐私与安全设计

- 默认推荐连接本地 OpenAI-compatible 推理服务，`.env.example` 已改为本地端点示例。
- 黑名单、暂存交易、图谱和日志均保存在本机或银行内网服务。
- 日志应避免写入真实姓名、身份证号、银行卡号、手机号等原始敏感字段；参赛 Demo 使用 P101/P102 这类脱敏客户编号。
- 外部 API 仅作为可选开发调试能力，若启用必须在技术报告中说明数据范围。

## 初赛提交材料清单

- 技术论文：可基于 [competition_paper_outline.md](competition_paper_outline.md) 扩写。
- 演示 PPT：建议使用 `output/ppt/` 下现有材料继续整理为 8-10 页。
- Demo 报告：运行 `uv run python scripts/sentinel_competition_demo.py` 生成硬件画像；在依赖服务齐全时加 `--run-pipeline` 生成完整用例结果。
