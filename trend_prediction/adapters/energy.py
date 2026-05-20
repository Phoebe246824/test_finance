"""能源与环保领域适配器"""

from trend_prediction.adapters.base import BaseAdapter


class EnergyAdapter(BaseAdapter):
    """能源与环保领域适配器"""

    @property
    def category(self) -> str:
        return "energy"

    @property
    def category_name(self) -> str:
        return "能源"

    @property
    def intent_analysis_prompt(self) -> str:
        return """# 能源意图分析报告

## 表面意图
[分析事件直接表达的能源目标或环保目标]

## 深层动机
[分析能源安全、经济利益、环境考量、地缘政治等深层因素]

## 能源结构影响分析
- 能源供需变化
- 能源价格波动
- 能源转型进程

## 利益相关方
- [国家/企业1]：[立场和态度]
- [国家/企业2]：[立场和态度]

## 潜在影响
- 短期影响：[对能源市场、价格的直接影响]
- 长期影响：[对能源结构、全球能源秩序的深远影响]

## 信号强度
[高/中/低] - [理由]
"""

    @property
    def trend_prediction_prompt(self) -> str:
        return """# 能源趋势预测报告

## 短期趋势（{short_term}）
[能源价格、供应风险、政策调整]

## 中期趋势（{medium_term}）
[能源结构调整、新能源发展、全球能源合作]

## 长期趋势（{long_term}）
[全球能源秩序重塑、能源转型完成、新能源主导]

## 关键转折点
- [转折点1]：[描述]
- [转折点2]：[描述]

## 概率评估
- 路径A（能源转型加速）：[概率]
- 路径B（传统能源回归）：[概率]
- 路径C（能源格局重组）：[概率]

## 风险预警
- [风险1]：[描述]
- [风险2]：[描述]
"""
