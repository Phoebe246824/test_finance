"""金融与资本市场领域适配器"""

from trend_prediction.adapters.base import BaseAdapter


class FinanceAdapter(BaseAdapter):
    """金融与资本市场领域适配器"""

    @property
    def category(self) -> str:
        return "finance"

    @property
    def category_name(self) -> str:
        return "金融"

    @property
    def intent_analysis_prompt(self) -> str:
        return """# 金融意图分析报告

## 表面意图
[分析事件直接表达的金融目标或市场行为]

## 深层动机
[分析风险管理、利润追求、监管套利、市场操纵等深层因素]

## 信用/流动性/系统性风险分析
- 信用风险变化
- 流动性状况
- 系统性风险传导

## 利益相关方
- [机构/市场1]：[立场和态度]
- [机构/市场2]：[立场和态度]

## 潜在影响
- 短期影响：[对金融市场、资产价格的直接影响]
- 长期影响：[对金融体系、监管框架的深远影响]

## 信号强度
[高/中/低] - [理由]
"""

    @property
    def trend_prediction_prompt(self) -> str:
        return """# 金融趋势预测报告

## 短期趋势（{short_term}）
[市场恐慌、资本流动、监管干预]

## 中期趋势（{medium_term}）
[金融市场调整、监管政策变化、金融创新]

## 长期趋势（{long_term}）
[金融体系重塑、监管框架变革、新金融范式建立]

## 关键转折点
- [转折点1]：[描述]
- [转折点2]：[描述]

## 概率评估
- 路径A（市场稳定）：[概率]
- 路径B（金融危机）：[概率]
- 路径C（监管强化）：[概率]

## 风险预警
- [风险1]：[描述]
- [风险2]：[描述]
"""
