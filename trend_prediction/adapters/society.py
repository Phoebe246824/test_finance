"""社会与文化领域适配器"""

from trend_prediction.adapters.base import BaseAdapter


class SocietyAdapter(BaseAdapter):
    """社会与文化领域适配器"""

    @property
    def category(self) -> str:
        return "society"

    @property
    def category_name(self) -> str:
        return "社会/文化"

    @property
    def intent_analysis_prompt(self) -> str:
        return """# 社会意图分析报告

## 表面意图
[分析事件直接表达的社会诉求或文化目标]

## 深层动机
[分析社会公平、文化认同、政治诉求、经济考量等深层因素]

## 社会结构影响分析
- 社会情绪与民意走向
- 群体关系与冲突
- 制度与政策响应

## 利益相关方
- [群体/组织1]：[立场和态度]
- [群体/组织2]：[立场和态度]

## 潜在影响
- 短期影响：[对社会秩序、公众情绪的直接影响]
- 长期影响：[对社会结构、文化认同的深远影响]

## 信号强度
[高/中/低] - [理由]
"""

    @property
    def trend_prediction_prompt(self) -> str:
        return """# 社会趋势预测报告

## 短期趋势（{short_term}）
[社会情绪、政策响应、社会运动]

## 中期趋势（{medium_term}）
[文化冲突、制度变革、社会结构调整]

## 长期趋势（{long_term}）
[社会范式转变、文化认同重塑、制度性变革]

## 关键转折点
- [转折点1]：[描述]
- [转折点2]：[描述]

## 概率评估
- 路径A（社会和解）：[概率]
- 路径B（冲突升级）：[概率]
- 路径C（渐进改革）：[概率]

## 风险预警
- [风险1]：[描述]
- [风险2]：[描述]
"""
