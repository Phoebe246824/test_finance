"""领域适配器基类"""

from abc import ABC, abstractmethod
from pathlib import Path

from trend_prediction.classifier import SEVERITY_TO_TIME_RANGES
from trend_prediction import PROMPTS_DIR


class BaseAdapter(ABC):
    """领域适配器基类"""

    @property
    @abstractmethod
    def category(self) -> str:
        """适配器对应的分类"""

    @property
    @abstractmethod
    def category_name(self) -> str:
        """适配器的中文名称"""

    @property
    @abstractmethod
    def intent_analysis_prompt(self) -> str:
        """意图分析提示词"""

    @property
    @abstractmethod
    def trend_prediction_prompt(self) -> str:
        """趋势预测提示词（不含时间范围占位符）"""

    @property
    def intent_analysis_prompt_path(self) -> Path:
        """意图分析提示词文件路径"""
        return PROMPTS_DIR / f"intent_analysis_{self.category}.md"

    @property
    def trend_prediction_prompt_path(self) -> Path:
        """趋势预测提示词文件路径"""
        return PROMPTS_DIR / f"trend_prediction_{self.category}.md"

    def get_intent_analysis_prompt(self) -> str:
        """获取意图分析提示词内容"""
        prompt_path = self.intent_analysis_prompt_path
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        return self.intent_analysis_prompt

    def get_trend_prediction_prompt(self, severity: str | None = None) -> str:
        """
        获取趋势预测提示词内容。

        Args:
            severity: 事件影响严重度，用于替换时间范围占位符

        Returns:
            str: 提示词内容
        """
        prompt_path = self.trend_prediction_prompt_path
        if prompt_path.exists():  # noqa: SIM108
            prompt = prompt_path.read_text(encoding="utf-8")
        else:
            prompt = self.trend_prediction_prompt

        if severity is not None:
            time_ranges = SEVERITY_TO_TIME_RANGES.get(severity, SEVERITY_TO_TIME_RANGES["moderate"])
            prompt = prompt.replace("{short_term}", time_ranges["short_term"])
            prompt = prompt.replace("{medium_term}", time_ranges["medium_term"])
            prompt = prompt.replace("{long_term}", time_ranges["long_term"])

        return prompt
