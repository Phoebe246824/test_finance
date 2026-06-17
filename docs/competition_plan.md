# Sentinel Edge 参赛方案

## 作品定位

**Sentinel Edge** 是面向金融机构、企业风控团队和园区安保运营方的端侧风险研判智能体。系统在本地 Mini AI 工作站上完成事件标准化、黑名单过滤、RAG/知识图谱检索、风险评估、历史事件回捞、二次研判和趋势分析，强调隐私数据不出内网、弱网可运行、低延迟处置。

对应赛题方向：金融/企业/政务服务垂直行业创新应用。

## 目标用户与痛点

- 目标用户：企业风控专员、银行/保险反欺诈分析员、园区安保值班人员、合规审查人员。
- 当前痛点：敏感事件信息分散在聊天、交易、安保记录和新闻文本中，人工串联历史线索慢；云端模型会带来隐私和合规风险；传统规则系统很难识别“低风险历史 + 高风险当前事件”的组合风险。
- 端侧必要性：人员编号、交易摘要、安保记录、企业内部事件属于敏感数据，适合在机构内网或本机部署；本地推理可以在断网、弱网、专网环境下保持可用。

## 端到端 Demo 流程

1. 输入一条原始事件文本。
2. Normalizer Agent 将文本标准化为 `NormalizedEvent`。
3. Redis 黑名单过滤器执行人员、关键词、相似事件三路匹配。
4. 未命中事件写入 Milvus 暂存池，作为后续历史上下文。
5. 命中事件进入本地 LLM 分类、Graphiti + Neo4j 构图、混合检索和风险评分。
6. 若首次风险分超过阈值，系统从 Milvus 回捞同人/语义相关历史事件，并批量补图。
7. 补图后执行二次检索与二次风险评估。
8. 高风险结果进入 Dashboard Agent，生成意图分析和趋势预测。

## AMD 硬件分工

- GPU / Radeon 8060S：承载本地 LLM 推理、Embedding 生成、Rerank 或向量检索相关高吞吐任务。建议通过 ROCm、LM Studio、Ollama、vLLM 或 llama.cpp 的 AMD 后端运行量化模型。
- NPU / Ryzen AI：承载低功耗持续任务，例如轻量事件分类、敏感内容预筛、语音转文本小模型或后台监控模型。当前代码提供 `sentinel_edge.hardware` 环境探测和报告字段，接入 Ryzen AI SDK 后可在报告中留下 NPU 后端证据。
- CPU：负责 CrewAI Flow 调度、Redis/Milvus/Neo4j 访问、规则过滤、JSON 解析、日志和报告生成。
- 统一内存：适合同时运行 LLM、Embedding、知识图谱和向量库工作负载，减少多模型并发时的显存瓶颈。

## 本地模型建议

- LLM：Qwen2.5-14B-Instruct、Qwen3-14B、DeepSeek-R1-Distill-Qwen-14B 的 INT4/INT8 量化版本。
- Embedding：BAAI/bge-m3 或 bge-large-zh，本地 OpenAI-compatible endpoint 优先。
- Rerank：BAAI/bge-reranker-v2-m3，可作为可选增强；未配置时系统会跳过非同人候选精排。

## 性能与精度实验设计

- 模型对比：FP16 或云端基线 vs INT4/INT8 本地量化模型。
- 指标：端到端延迟、首 token 延迟、每秒 token、单条事件处理耗时、批量补图耗时、CPU/GPU/NPU 占用、内存占用。
- 精度：Demo 用例通过率、风险等级一致率、历史回捞命中率、误召回过滤率。
- 能效：记录同一批用例在不同模型和后端下的平均功耗、峰值功耗和处理时长。

## 隐私与安全设计

- 默认推荐连接本地 OpenAI-compatible 推理服务，`.env.example` 已改为本地端点示例。
- 黑名单、暂存事件、图谱和日志均保存在本机或内网服务。
- 日志应避免写入真实姓名、身份证号、手机号等原始敏感字段；参赛 Demo 建议使用 P01/P02 这类脱敏人员编号。
- 外部 API 仅作为可选开发调试能力，若启用必须在技术报告中说明数据范围。

## 初赛提交材料清单

- 技术论文：可基于 [competition_paper_outline.md](competition_paper_outline.md) 扩写。
- 演示 PPT：建议使用 `output/ppt/` 下现有材料继续整理为 8-10 页。
- Demo 报告：运行 `uv run python scripts/sentinel_competition_demo.py` 生成硬件画像；在依赖服务齐全时加 `--run-pipeline` 生成完整用例结果。
