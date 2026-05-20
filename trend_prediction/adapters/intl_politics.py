"""国际政治与外交领域适配器"""

from trend_prediction.adapters.base import BaseAdapter


class IntlPoliticsAdapter(BaseAdapter):
    """国际政治与外交领域适配器"""

    @property
    def category(self) -> str:
        return "intl_politics"

    @property
    def category_name(self) -> str:
        return "国际政治"

    @property
    def intent_analysis_prompt(self) -> str:
        return """# 国际政治意图分析报告

## 表面意图
[分析事件直接表达的政治或外交目标]

## 深层动机
[分析事件背后隐藏的地缘政治动机、权力博弈、战略考量]

## 权力结构分析
- 主要参与方及其立场
- 联盟关系与对抗格局
- 权力平衡变化

## 利益相关方
- [国家/组织1]：[立场和态度]
- [国家/组织2]：[立场和态度]

## 潜在影响
- 短期影响：[对国际关系、地区安全的直接影响]
- 长期影响：[对全球格局、国际秩序的深远影响]

## 信号强度
[高/中/低] - [理由]
"""

    @property
    def trend_prediction_prompt(self) -> str:
        return """# 国际政治趋势预测报告

## 短期趋势（{short_term}）
[外交互动、冲突升级或缓和、制裁与反制裁]

## 中期趋势（{medium_term}）
[联盟重组、地缘格局调整、国际秩序演变]

## 长期趋势（{long_term}）
[全球权力结构变化、国际体系重塑、新秩序建立]

## 关键转折点
- [转折点1]：[描述]
- [转折点2]：[描述]

## 概率评估
- 路径A（冲突升级）：[概率]
- 路径B（外交缓和）：[概率]
- 路径C（僵持对峙）：[概率]

## 风险预警
- [风险1]：[描述]
- [风险2]：[描述]
"""
