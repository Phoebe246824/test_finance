"""宏观经济领域适配器"""

from trend_prediction.adapters.base import BaseAdapter


class EconomyAdapter(BaseAdapter):
    """宏观经济领域适配器"""

    @property
    def category(self) -> str:
        return "economy"

    @property
    def category_name(self) -> str:
        return "经济"

    @property
    def intent_analysis_prompt(self) -> str:
        return """# 经济意图分析报告

## 表面意图
[分析事件直接表达的经济目标或政策目标]

## 深层动机
[分析经济利益、产业布局、金融安全、地缘经济等战略考量]

## 贸易/产业/金融影响分析
- 贸易政策变化
- 产业结构调整
- 金融市场波动

## 利益相关方
- [国家/机构1]：[立场和态度]
- [国家/机构2]：[立场和态度]

## 潜在影响
- 短期影响：[对经济指标、市场信心的直接影响]
- 长期影响：[对全球经济格局、贸易体系的深远影响]

## 信号强度
[高/中/低] - [理由]
"""

    @property
    def trend_prediction_prompt(self) -> str:
        return """# 经济趋势预测报告

## 短期趋势（{short_term}）
[贸易政策、金融市场波动、供应链调整]

## 中期趋势（{medium_term}）
[产业结构变化、经济周期演变、区域经济整合]

## 长期趋势（{long_term}）
[全球经济格局重塑、新贸易体系建立、经济范式转变]

## 关键转折点
- [转折点1]：[描述]
- [转折点2]：[描述]

## 概率评估
- 路径A（经济复苏）：[概率]
- 路径B（经济衰退）：[概率]
- 路径C（结构性调整）：[概率]

## 风险预警
- [风险1]：[描述]
- [风险2]：[描述]
"""
