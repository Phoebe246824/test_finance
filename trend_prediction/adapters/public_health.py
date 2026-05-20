"""公共卫生领域适配器"""

from trend_prediction.adapters.base import BaseAdapter


class PublicHealthAdapter(BaseAdapter):
    """公共卫生领域适配器"""

    @property
    def category(self) -> str:
        return "public_health"

    @property
    def category_name(self) -> str:
        return "公共卫生"

    @property
    def intent_analysis_prompt(self) -> str:
        return """# 公共卫生意图分析报告

## 表面意图
[分析事件直接表达的公共卫生目标或防控目标]

## 深层动机
[分析疫情防控、政治考量、经济稳定、科学决策等深层因素]

## 治理体系影响分析
- 公共卫生防控能力
- 医疗资源分配
- 社会治理模式

## 利益相关方
- [机构/群体1]：[立场和态度]
- [机构/群体2]：[立场和态度]

## 潜在影响
- 短期影响：[对疫情防控、医疗系统的直接影响]
- 长期影响：[对公共卫生体系、全球健康治理的深远影响]

## 信号强度
[高/中/低] - [理由]
"""

    @property
    def trend_prediction_prompt(self) -> str:
        return """# 公共卫生趋势预测报告

## 短期趋势（{short_term}）
[疫情态势、疫苗研发、医疗资源]

## 中期趋势（{medium_term}）
[防控政策调整、医疗体系建设、全球卫生合作]

## 长期趋势（{long_term}）
[全球卫生治理体系重塑、公共卫生范式转变]

## 关键转折点
- [转折点1]：[描述]
- [转折点2]：[描述]

## 概率评估
- 路径A（疫情控制）：[概率]
- 路径B（疫情反复）：[概率]
- 路径C（常态化防控）：[概率]

## 风险预警
- [风险1]：[描述]
- [风险2]：[描述]
"""
