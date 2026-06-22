"""
Sentinel 舆情分析系统 — 自适应任务模板

根据事件类别和影响严重度动态选择提示词，实现：
- 类别自适应：不同领域使用不同的分析维度和输出模板
- 严重度自适应：根据影响程度动态调整时间范围
"""

from crewai import Agent, Task

from trend_prediction.adapters import get_adapter
from trend_prediction.classifier import (
    EventClassifier,
    FINANCIAL_RISK_CATEGORIES,
    SEVERITY_TO_TIME_RANGES,
)
from trend_prediction import PROMPTS_DIR

_FALLBACK_PROMPTS = {
    "intent_analysis": "请分析该事件的意图和动机。",
    "trend_prediction": "请分析该事件的发展趋势。",
}


def _replace_time_ranges(prompt: str, severity: str | None) -> str:
    if severity is None:
        return prompt

    time_ranges = SEVERITY_TO_TIME_RANGES.get(severity, SEVERITY_TO_TIME_RANGES["moderate"])
    return (
        prompt.replace("{short_term}", time_ranges["short_term"])
        .replace("{medium_term}", time_ranges["medium_term"])
        .replace("{long_term}", time_ranges["long_term"])
    )


def _get_adaptive_prompt(category: str, prompt_type: str, severity: str | None = None) -> str:
    """
    获取自适应提示词。

    Args:
        category: 事件类别标识
        prompt_type: 提示词类型 ("intent_analysis" 或 "trend_prediction")
        severity: 事件严重度（仅 trend_prediction 需要）

    Returns:
        str: 提示词内容
    """
    prompt_category = "finance" if category in FINANCIAL_RISK_CATEGORIES else "general"

    if prompt_category != "general":
        try:
            adapter = get_adapter(prompt_category)
            if prompt_type == "intent_analysis":
                return adapter.get_intent_analysis_prompt()
            if prompt_type == "trend_prediction":
                return adapter.get_trend_prediction_prompt(severity=severity)
        except ValueError:
            pass

    prompt_path = PROMPTS_DIR / f"{prompt_type}.md"
    if not prompt_path.exists():
        prompt = _FALLBACK_PROMPTS.get(prompt_type, "请分析该事件。")
    else:
        prompt = prompt_path.read_text(encoding="utf-8")

    if prompt_type == "trend_prediction":
        return _replace_time_ranges(prompt, severity)
    return prompt


def get_intent_analysis_task(
    event_text: str,
    classifier: EventClassifier,
    category: str,
    confidence: float,
    agent: Agent,
) -> Task:
    """
    创建意图分析任务，使用类别自适应提示词。

    Args:
        event_text: 事件文本
        classifier: 事件分类器实例
        category: 事件类别
        confidence: 分类置信度
        agent: CrewAI Agent（由调用方创建）

    Returns:
        Task: CrewAI 意图分析任务
    """
    category_name = classifier.get_category_name(category)

    prompt = _get_adaptive_prompt(category, "intent_analysis")

    description = (
        f"你是一位专业的事件分析专家。\n\n"
        f"当前事件分类：{category_name}\n"
        f"分类置信度：{confidence:.0%}\n\n"
        f"事件内容：{event_text}\n\n"
        f"请按照以下模板进行分析：\n\n{prompt}"
    )

    return Task(
        name="意图分析",
        description=description,
        agent=agent,
        expected_output="一个完整的意图分析报告，包含上述所有维度的分析结果。",
    )


def get_trend_prediction_task(
    event_text: str,
    intent_task: Task,
    classifier: EventClassifier,
    category: str,
    confidence: float,
    agent: Agent,
    severity: str | None = None,
    severity_confidence: float = 0.0,
) -> Task:
    """
    创建趋势预测任务，使用类别自适应和严重度自适应提示词。

    Args:
        event_text: 事件文本
        intent_task: 意图分析任务（作为上下文）
        classifier: 事件分类器实例
        category: 事件类别
        confidence: 分类置信度
        agent: CrewAI Agent（由调用方创建）
        severity: 事件严重度
        severity_confidence: 严重度置信度

    Returns:
        Task: CrewAI 趋势预测任务
    """
    category_name = classifier.get_category_name(category)
    severity_name = classifier.get_severity_name(severity) if severity else "未知"

    prompt = _get_adaptive_prompt(category, "trend_prediction", severity=severity)
    output_guardrails = (
        "输出要求：只输出报告正文，不要输出审查过程、检查清单、思考过程、执行说明或完成声明。"
        "不要声称读取或写入任何文件，不要提及任何文件路径。"
        "不要使用自我叙述、最终回复标签、审查结论包装或修改状态声明等包装性表述。"
        "如果需要表达合规性，请写在报告的“不确定性”或“处置建议”章节内。"
    )

    description = (
        f"你是一位专业的事件分析专家。\n\n"
        f"当前事件分类：{category_name}\n"
        f"分类置信度：{confidence:.0%}\n"
        f"事件影响严重度：{severity_name}\n"
        f"严重度置信度：{severity_confidence:.0%}\n\n"
        f"事件内容：{event_text}\n\n"
        f"{output_guardrails}\n\n"
        f"请按照以下模板进行趋势预测：\n\n{prompt}"
    )

    return Task(
        name="趋势预测",
        description=description,
        agent=agent,
        expected_output="完整的报告正文，只包含报告章节内容，不包含审查过程、文件读写说明或最终回复包装。",
        context=[intent_task],
    )
