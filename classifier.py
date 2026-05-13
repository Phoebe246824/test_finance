"""
Sentinel 舆情分析系统 — 分类评级服务 (Classification)
=====================================================
使用 CrewAI Agent 对标准化事件进行类型分类和风险评级。

Agent 设计:
  - TypeClassifier Agent: 识别事件类型，提取关键实体（使用快速模型）
  - RiskEvaluator Agent: 评估风险等级，输出 0-1 风险分数（使用推理模型）
  - 两个 Agent 按 sequential 顺序执行，分类结果作为评级输入
"""
from crewai import Agent, Task, Crew, Process
from pydantic import BaseModel


# ============================================================
#  领域模型
# ============================================================

class RiskLevel:
    """
    风险等级枚举

    属性:
        HIGH   = "high"      # risk_score >= 0.7
        MEDIUM = "medium"    # risk_score >= 0.4
        LOW    = "low"       # risk_score < 0.4
    """
    ...


class ClassifiedEvent(BaseModel):
    """
    分类评级结果的输出模型

    属性:
        event_id: str           — 原始事件 ID
        event_type: str         — 事件类型（突发事件/负面舆情/正面舆情/信息传播/商业动态）
        risk_level: str         — 风险等级 (high/medium/low)
        risk_score: float       — 风险分数 (0.0 ~ 1.0)
        key_entities: list      — 提取的关键实体列表 [{"name": "xxx", "type": "PERSON"}, ...]
        summary: str            — 事件摘要
        reasoning: str          — 评级推理过程
        trace_id: str           — 链路追踪 ID
    """
    ...


# ============================================================
#  CrewAI Agent 定义
# ============================================================

def create_type_classifier(llm) -> Agent:
    """
    创建事件类型分类 Agent

    Args:
        llm: CrewAI LLM 实例（使用快速模型，如 DeepSeek-V3）

    Returns:
        Agent: TypeClassifier Agent

    作用:
        角色定义: 资深舆情分析师，擅长从文本中快速判断事件性质
        目标: 准确识别事件类型并提取关键实体
        输出: 结构化 JSON，包含 event_type, key_entities, preliminary_summary
    """
    ...


def create_risk_evaluator(llm) -> Agent:
    """
    创建风险评估 Agent

    Args:
        llm: CrewAI LLM 实例（使用推理模型，保证评级质量）

    Returns:
        Agent: RiskEvaluator Agent

    作用:
        角色定义: 风险评估专家，综合考虑影响范围、传播速度、严重程度
        目标: 输出 0-1 的风险分数和评级理由
        输出: 结构化 JSON，包含 risk_level, risk_score, reasoning
    """
    ...


# ============================================================
#  CrewAI Task 定义
# ============================================================

def create_classification_tasks(type_classifier: Agent, risk_evaluator: Agent) -> list:
    """
    创建分类和评级任务

    Args:
        type_classifier: TypeClassifier Agent 实例
        risk_evaluator: RiskEvaluator Agent 实例

    Returns:
        list[Task]: 两个顺序执行的任务

    任务 1 — 事件分类:
        描述: 分析事件内容 {event_content}，识别事件类型并提取关键实体
        期望输出: JSON {"event_type": "...", "key_entities": [...], "preliminary_summary": "..."}

    任务 2 — 风险评级:
        描述: 基于事件类型 {event_type} 和上下文，评估风险等级
        期望输出: JSON {"risk_level": "...", "risk_score": 0.85, "reasoning": "..."}
        上下文: 自动接收任务 1 的输出
    """
    ...


# ============================================================
#  Crew 编排
# ============================================================

def create_classification_crew(config: dict) -> Crew:
    """
    创建分类评级 Crew

    Args:
        config: 配置字典，包含 LLM 配置

    Returns:
        Crew: 配置好的 Classification Crew

    作用:
        实例化 TypeClassifier + RiskEvaluator 两个 Agent
        创建两个顺序任务（分类 → 评级）
        配置 process=Process.sequential
        设置 verbose=True 用于调试日志
    """
    ...


def classify_event(normalized_event: dict, crew: Crew) -> ClassifiedEvent:
    """
    执行事件分类评级

    Args:
        normalized_event: 标准化事件字典（来自 Ingestion 服务）
        crew: 分类评级 Crew 实例

    Returns:
        ClassifiedEvent: 分类评级结果

    作用:
        调用 crew.kickoff(inputs={"event_content": ..., "source": ...})
        解析 Agent 输出的 JSON 字符串
        校验输出格式，异常时调用 fallback_classify()
        封装为 ClassifiedEvent 返回
        超时兜底: 设置 30s 超时，超时降级为规则引擎
    """
    ...


# ============================================================
#  规则降级（LLM 不可用时的兜底方案）
# ============================================================

def fallback_classify(normalized_event: dict) -> ClassifiedEvent:
    """
    LLM 不可用时的规则分类降级

    Args:
        normalized_event: 标准化事件字典

    Returns:
        ClassifiedEvent: 基于规则生成的分类结果

    作用:
        使用关键词匹配进行简单分类:
            - 负面关键词列表 → 负面舆情 + high risk
            - 正面关键词列表 → 正面舆情 + low risk
            - 默认 → 信息传播 + medium risk
        风险分数固定为 0.5（保守策略）
        记录降级日志，便于后续人工复核
    """
    ...


# ============================================================
#  消费者
# ============================================================

def start_classification_consumer(config: dict) -> None:
    """
    启动分类服务的 RabbitMQ 消费者（阻塞运行）

    Args:
        config: 全局配置字典

    作用:
        监听 sentinel.internal.normalized 队列
        消费标准化事件 → 调用 classify_event() 分类评级
        将 ClassifiedEvent 发布到:
            sentinel.internal.classified     → 全量分类结果（供 Graph 服务消费）
            sentinel.internal.high_risk      → 高评级事件（risk_score >= 0.7，Phase 2 使用）
        手动 ACK，异常进入 DLQ
    """
    ...
