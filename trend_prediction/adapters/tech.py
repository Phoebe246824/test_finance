"""科技与技术创新领域适配器"""

from trend_prediction.adapters.base import BaseAdapter


class TechAdapter(BaseAdapter):
    """科技与技术创新领域适配器"""

    @property
    def category(self) -> str:
        return "tech"

    @property
    def category_name(self) -> str:
        return "科技"

    @property
    def intent_analysis_prompt(self) -> str:
        return """# 科技意图分析报告

## 表面意图
[分析事件直接表达的技术目标或商业目标]

## 深层动机
[分析技术主导权、供应链安全、市场准入、标准制定等战略考量]

## 技术生态分析
- 技术路线竞争格局
- 产业链上下游影响
- 技术壁垒与突破点

## 利益相关方
- [企业/机构1]：[立场和态度]
- [企业/机构2]：[立场和态度]

## 潜在影响
- 短期影响：[对技术研发、产品发布的直接影响]
- 长期影响：[对产业格局、技术标准的深远影响]

## 信号强度
[高/中/低] - [理由]
"""

    @property
    def trend_prediction_prompt(self) -> str:
        return """# 科技趋势预测报告

## 短期趋势（{short_term}）
[技术竞争、产品发布、标准博弈]

## 中期趋势（{medium_term}）
[生态重构、产业链调整、创新范式转变]

## 长期趋势（{long_term}）
[技术路线确立、产业格局重塑、新范式建立]

## 关键转折点
- [转折点1]：[描述]
- [转折点2]：[描述]

## 概率评估
- 路径A（技术突破）：[概率]
- 路径B（技术封锁）：[概率]
- 路径C（开放合作）：[概率]

## 风险预警
- [风险1]：[描述]
- [风险2]：[描述]
"""
