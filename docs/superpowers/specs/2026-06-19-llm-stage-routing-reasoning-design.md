# 设计：工作流 LLM 按 stage 解耦路由 + 研判档 crewai 原生 reasoning（省内存版）

- 日期：2026-06-19
- 状态：已通过设计评审，待写实现计划
- 范围：后端推理编排层（`providers/`、`main.py`、`graphiti/`、`.env`），不含前端、不含 embedding/reranker 改动

## 1. 背景与目标

当前所有智能体调用都经 `get_llm()` 指向**同一个** `LLM_MODEL`，Graphiti 内部抽取也用它。
任务画像（来自代码）显示工作流分两类负载：

- **高频结构化 JSON 抽取**：标准化(normalize)、分类(classify)、Graphiti 实体/关系抽取——要 JSON 干净 + 吞吐。
- **低频高价值研判**：首/二次风险评估、意图+趋势报告——要推理质量。

目标：在不破坏当前云端测试配置的前提下，

1. 把不同 stage 的 LLM 调用**按档位解耦**到独立端点（为将来用 llama.cpp 同机常驻多模型铺好骨架）；
2. 给**研判档**接入 **crewai 原生 `Agent(reasoning=True)`**（计划-反思-执行的多步推理），且**当前云端即可生效**。

本期为「省内存版」：实际仍可只跑一个 LLM 端点（extract/reason 留空即回退单一 `LLM_*`），多端点是骨架预留。

## 2. 关键决策（已与用户确认）

- **思考机制 = crewai 原生 `Agent(reasoning=True)`**（机制①），不用 Qwen token 级 `<think>`（机制②）。
  - 理由：①模型无关、当前云端 `diffusiongemma` 即生效；②在当前云端是 no-op，须等本地 Qwen3.6。
- **明确放弃**：`<think>` 剥离、`enable_thinking`/`extra_body`、`reasoning_effort` 注入——选①后均用不上。`parse_llm_json_object` 不改。
- **stage 分档**：
  - `extract`（不推理）：`normalize`、`classify`、`graphiti`
  - `reason`（推理）：`risk_first`、`risk_second`、`dashboard`
- **路由位置**：集中在 `providers/llm_provider.py`（方式 A），call site 只声明 stage 语义。
- `REASON_MAX_ATTEMPTS` 默认 **2**，封顶 reasoning 多轮 refine，控演示延迟。

## 3. 组件与文件改动

### 3.1 `providers/llm_provider.py`（新增路由职责）

- `STAGE_TIERS: dict[str, str]`
  ```python
  STAGE_TIERS = {
      "normalize": "extract",
      "classify": "extract",
      "graphiti": "extract",
      "risk_first": "reason",
      "risk_second": "reason",
      "dashboard": "reason",
  }
  ```
- `get_llm_for(stage: str, temperature: float | None = None) -> LLM`
  - 校验 `stage` 在 `STAGE_TIERS`，否则 `ValueError`（fail fast，避免静默路由错）。
  - 按档解析端点（见 §3.4 解析规则）。
  - 复用现有 `get_siliconflow_llm(model, temperature, api_key, base_url)` 构建 crewai `LLM`，沿用其 `max_completion_tokens=8192`、`top_p=0.85`、`provider="openai"`。
  - 仍把实例登记进 `_ACTIVE_LLMS`，不破坏 `close_all_llms()`。
  - `temperature` 为 None 时沿用调用方原值（normalize/classify/dashboard=0.3，risk=0.1）。
  - **只管 endpoint，不设置 reasoning**（reasoning 是 Agent 属性，不是 LLM 属性）。
- `reasoning_kwargs_for(stage: str) -> dict`
  - `reason` 档返回 `{"reasoning": True, "max_reasoning_attempts": REASON_MAX_ATTEMPTS}`。
  - `extract` 档返回 `{}`（Agent 的 `reasoning` 默认 False）。
  - `REASON_MAX_ATTEMPTS = int(os.getenv("REASON_MAX_ATTEMPTS") or "2")`。
- `get_llm(...)` **保持不变**（向后兼容）。

### 3.2 `main.py`（call site 替换 + 研判档加 reasoning）

5 处 `get_llm(...)` → `get_llm_for("<stage>", <temp>)`：

| 行 | stage | 改为 |
|---|---|---|
| 1160 | normalize | `get_llm_for("normalize", 0.3)` |
| 355 | classify | `get_llm_for("classify", 0.3)`（不再手传 config 的 model/url，由 provider 按档解析） |
| 440 | risk_first | `get_llm_for("risk_first", 0.1)` |
| 511 | risk_second | `get_llm_for("risk_second", 0.1)` |
| 1003 | dashboard | `get_llm_for("dashboard", 0.3)`（intent_analyzer 与 trend_predictor 共用） |

研判档 Agent 加 reasoning（解包 `reasoning_kwargs_for`）：

- `risk_evaluator`（440 附近）：`Agent(..., **reasoning_kwargs_for("risk_first"))`
- `risk_evaluator`（511 附近）：`Agent(..., **reasoning_kwargs_for("risk_second"))`
- `intent_analyzer`（1047）：`Agent(..., **reasoning_kwargs_for("dashboard"))`
- `trend_predictor`（1059）：`Agent(..., **reasoning_kwargs_for("dashboard"))`

`parse_llm_json_object`（205）**不改**。

### 3.3 `graphiti/graphiti_workflow.py`（内部抽取走 extract 端点）

模块级 `LLM_*` 读取处改为优先 `LLM_EXTRACT_*`、回退 `LLM_*`：

```python
LLM_BASE_URL = os.environ.get("LLM_EXTRACT_BASE_URL") or os.environ.get("LLM_BASE_URL")
LLM_MODEL    = os.environ.get("LLM_EXTRACT_MODEL")    or os.environ.get("LLM_MODEL")
LLM_API_KEY  = os.environ.get("LLM_EXTRACT_API_KEY")  or os.environ.get("LLM_API_KEY")
```

不加 reasoning（Graphiti 用自己的 `OpenAIGenericClient`，且属抽取档）。

### 3.4 `.env` + `.env.example`（端点骨架）

新增（留空即回退现有 `LLM_*`，当前云端零改动）：

```bash
# 抽取档（高频 JSON：normalize/classify/Graphiti）；留空回退 LLM_*
LLM_EXTRACT_BASE_URL=
LLM_EXTRACT_MODEL=
LLM_EXTRACT_API_KEY=
# 研判档（reasoning：风险评估/报告）；留空回退 LLM_*
LLM_REASON_BASE_URL=
LLM_REASON_MODEL=
LLM_REASON_API_KEY=
# 研判档 reasoning 多轮上限（控演示延迟）
REASON_MAX_ATTEMPTS=2
```

解析规则（在 provider 与 graphiti 一致）：
> 某档某项 = `getenv(LLM_{档}_X) or getenv(LLM_X)`

- 省内存版：extract/reason 全留空 → 全部指向单一 `LLM_*`。
- 多模型版：填 `LLM_EXTRACT_*` 指向快模型端点、`LLM_REASON_*` 指向研判模型端点（各自一个 llama-server 实例/端口）。

## 4. 数据流

```
事件 → normalize(extract端点, 无reasoning)
     → classify(extract端点, 无reasoning)
     → Graphiti 抽取(extract端点)
     → risk_first(reason端点, reasoning=True)
     → 回捞/补图 → Graphiti 抽取(extract端点)
     → risk_second(reason端点, reasoning=True)
     → dashboard 意图+趋势报告(reason端点, reasoning=True ×2 agent)
```

每个研判 agent 执行任务前，crewai 先做一次（至多 `REASON_MAX_ATTEMPTS` 次）规划生成，再把计划注入任务描述执行；最终任务输出格式不变（risk 仍出 JSON，报告仍出中文长文）。

## 5. 错误处理与降级

- **端点未单配** → 回退 `LLM_*`，当前云端配置照常工作。
- **reasoning 规划出错** → crewai 官方行为：自动降级为「不带计划执行」，不会因规划失败而崩（见 https://docs.crewai.com/en/concepts/reasoning）。
- **未知 stage 传入 `get_llm_for`** → `ValueError`，fail fast。
- **抽取档**行为与现状完全一致（无新增分支）。
- 现有 risk 评估解析失败兜底（返回 medium）与 classify 失败兜底（返回 None）保持不变。

## 6. 测试

单元测试（`tests/`，monkeypatch env，不需真实 LLM）：

1. `get_llm_for`：
   - 仅设 `LLM_*` 时，extract 与 reason 两档都解析到 `LLM_*`。
   - 设 `LLM_EXTRACT_*`/`LLM_REASON_*` 后，各档解析到各自端点。
   - 未知 stage 抛 `ValueError`。
   - 返回实例登记进 `_ACTIVE_LLMS`。
2. `reasoning_kwargs_for`：
   - 研判档返回 `{"reasoning": True, "max_reasoning_attempts": N}`，extract 档返回 `{}`。
   - `REASON_MAX_ATTEMPTS` 环境变量被正确读取。
3. 回归：现有 `tests/` 全绿（无破坏性改动）。

人工验证（当前云端，运行 `finance_01` / `finance_04`）：

- 研判档 agent 触发 reasoning 规划步（crewai reasoning 事件可见）。
- pipeline 仍产出风险 JSON 与中文研判报告；分档评分/回捞链路不变。
- 抽取档（normalize/classify/Graphiti）行为不变。

## 7. 显式不做（YAGNI / 留待后续）

- Qwen token 级 `<think>` 与剥离逻辑、`enable_thinking`、`reasoning_effort` 注入。
- embedding / reranker 端点改动（已是独立端点，本期不动）。
- 真正启动第二个 llama-server / 多模型常驻部署（本期只留 `.env` 骨架；部署属运维步骤，单独处理）。
- `load_config()` 的结构性重构（不在 provider 路由方案内）。

## 8. 与赛题/PPT 的衔接

本改动是「异构多模型在统一内存同机常驻协同」叙事的代码骨架，对应评分 1.2（有效利用统一内存/异构）与 1.1（系统设计创新）。落地多端点后可写入 PPT P8 与论文硬件章节。
