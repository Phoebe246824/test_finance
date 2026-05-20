"""Sentinel 舆情分析 — 事件分类与自适应提示词模块"""

from pathlib import Path

from trend_prediction.classifier import EventClassifier

PROMPTS_DIR = Path(__file__).parent / "prompts"

__all__ = ["EventClassifier", "PROMPTS_DIR"]
