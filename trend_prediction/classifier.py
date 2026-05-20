"""
Sentinel 舆情分析系统 — 事件分类与严重度评估模块

基于 Jina Rerank API 的事件分类器，支持：
- 7 种事件类别分类（国际政治、科技、经济、社会/文化、公共卫生、能源、金融）
- 4 级影响严重度评估（轻微、一般、严重、重大）
- 严重度到时间范围的动态映射
- 关键词匹配回退方案
"""

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════
# 事件类别分类（category classification）
# ══════════════════════════════════════════════════════════════════

CATEGORY_DESCRIPTIONS: dict[str, str] = {
    "intl_politics": "这条新闻属于国际政治与外交类事件，涉及国家间关系、地缘政治冲突、军事对抗、外交谈判、制裁禁令、联盟关系、领土争端等。",  # noqa: E501
    "tech": "这条新闻属于科技与技术创新类事件，涉及芯片、人工智能、半导体、量子计算、5G/6G、自动驾驶、云计算、大数据、物联网等前沿技术领域。",  # noqa: E501
    "economy": "这条新闻属于宏观经济类事件，涉及经济增长、GDP、通胀通缩、央行货币政策、利率汇率、国际贸易、供应链、经济衰退或复苏。",  # noqa: E501
    "society": "这条新闻属于社会与文化类事件，涉及性别平等、种族议题、宗教冲突、教育医疗、住房政策、贫富差距、社会福利、劳资纠纷等。",  # noqa: E501
    "public_health": "这条新闻属于公共卫生类事件，涉及传染病疫情、疫苗研发、医疗资源、医院ICU、死亡感染率、公共卫生防控、隔离封控等。",  # noqa: E501
    "energy": "这条新闻属于能源与环保类事件，涉及石油天然气、可再生能源、太阳能风能、核电、碳排放、碳中和、新能源、电网电力等。",  # noqa: E501
    "finance": "这条新闻属于金融与资本市场类事件，涉及银行保险、证券基金、并购IPO、债务信贷、金融风险、市场波动、金融监管等。",  # noqa: E501
}

CATEGORY_NAMES: dict[str, str] = {
    "intl_politics": "国际政治",
    "tech": "科技",
    "economy": "经济",
    "society": "社会/文化",
    "public_health": "公共卫生",
    "energy": "能源",
    "finance": "金融",
    "general": "综合",
}

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "intl_politics": [
        "制裁",
        "禁令",
        "出口",
        "关税",
        "贸易",
        "地缘",
        "冲突",
        "战争",
        "军事",
        "联盟",
        "联合国",
        "外交",
        "谈判",
        "核",
        "军备",
        "领土",
        "主权",
        "国界",
        "盟友",
        "敌对",
        "政变",
        "革命",
        "政权",
    ],
    "tech": [
        "芯片",
        "AI",
        "人工智能",
        "大模型",
        "算法",
        "算力",
        "GPU",
        "半导体",
        "光刻机",
        "EDA",
        "量子",
        "区块链",
        "5G",
        "6G",
        "自动驾驶",
        "机器人",
        "云计算",
        "大数据",
        "物联网",
    ],
    "economy": [
        "经济",
        "股市",
        "债券",
        "通胀",
        "通缩",
        "GDP",
        "央行",
        "利率",
        "汇率",
        "美元",
        "人民币",
        "外资",
        "投资",
        "IPO",
        "破产",
        "衰退",
        "增长",
        "复苏",
        "制裁",
        "贸易战",
        "供应链",
    ],
    "society": [
        "女权",
        "性别",
        "对立",
        "抗议",
        "示威",
        "游行",
        "罢工",
        "种族",
        "宗教",
        "民族",
        "文化",
        "教育",
        "医疗",
        "住房",
        "福利",
        "社保",
        "养老",
        "就业",
        "失业",
        "贫富",
        "公平",
    ],
    "public_health": [
        "疫情",
        "传染病",
        "疫苗",
        "病毒",
        "新冠",
        "SARS",
        "埃博拉",
        "流感",
        "公共卫生",
        "隔离",
        "封控",
        "口罩",
        "医疗资源",
        "医院",
        "ICU",
        "死亡",
        "感染率",
        "传播",
    ],
    "energy": [
        "能源",
        "石油",
        "天然气",
        "煤炭",
        "可再生能源",
        "太阳能",
        "风能",
        "核电",
        "碳",
        "碳排放",
        "碳中和",
        "碳达峰",
        "化石燃料",
        "新能源",
        "充电桩",
        "电动车",
        "电池",
        "电网",
        "停电",
        "OPEC",
        "减产",
        "油价",
        "上涨",
    ],
    "finance": [
        "银行",
        "保险",
        "证券",
        "基金",
        "信托",
        "理财",
        "P2P",
        "非法集资",
        "跑路",
        "兑付",
        "暴雷",
        "挤兑",
        "杠杆",
    ],
}

# ══════════════════════════════════════════════════════════════════
# 事件影响严重度分类（impact severity classification）
# ══════════════════════════════════════════════════════════════════

SEVERITY_DESCRIPTIONS: dict[str, str] = {
    "minor": "这条新闻属于轻微影响事件，事件影响有限，可能在几天到几周内消退，不会对整体格局产生持续影响，影响范围主要集中在局部或特定领域。",  # noqa: E501
    "moderate": "这条新闻属于一般影响事件，事件有一定影响，可能持续几周到几个月，会引发局部调整或短期波动，但不会改变整体格局。",  # noqa: E501
    "severe": "这条新闻属于严重影响事件，事件影响较大，可能持续几个月到几年，会改变局部格局或引发系统性调整，影响范围较广。",  # noqa: E501
    "critical": "这条新闻属于重大影响事件，事件影响深远，可能持续几年到几十年，可能重塑全球或行业格局，影响范围广泛且持久。",  # noqa: E501
}

SEVERITY_NAMES: dict[str, str] = {
    "minor": "轻微",
    "moderate": "一般",
    "severe": "严重",
    "critical": "重大",
}

SEVERITY_KEYWORDS: dict[str, list[str]] = {
    "minor": [
        "轻微",
        "有限",
        "局部",
        "短期",
        "个别",
        "零星",
        "轻微影响",
        "小规模",
        "少量",
        "局部影响",
        "暂时性",
        "轻微波动",
        "发布",
        "新产品",
    ],
    "moderate": [
        "一般",
        "中等",
        "一定",
        "中期",
        "区域",
        "部分",
        "中等影响",
        "中等规模",
        "阶段性",
        "短期波动",
        "一定影响",
        "地震",
        "局部影响",
        "挤兑",
        "风险",
    ],
    "severe": [
        "严重",
        "重大",
        "系统性",
        "广泛",
        "持续",
        "大规模",
        "严重影响",
        "系统性影响",
        "深度影响",
        "长期影响",
        "广泛影响",
    ],
    "critical": [
        "重大",
        "灾难性",
        "历史性",
        "革命性",
        "颠覆性",
        "全球性",
        "历史性影响",
        "革命性影响",
        "颠覆性影响",
        "全球性影响",
        "百年一遇",
        "前所未有的",
        "历史性转折",
        "政变",
        "国际社会",
    ],
}

# ══════════════════════════════════════════════════════════════════
# 严重度到时间范围的映射
# ══════════════════════════════════════════════════════════════════

SEVERITY_TO_TIME_RANGES: dict[str, dict[str, str]] = {
    "minor": {
        "short_term": "几天到几周",
        "medium_term": "几周（无显著持续影响）",
        "long_term": "无显著长期影响",
    },
    "moderate": {
        "short_term": "1-3个月",
        "medium_term": "3-12个月",
        "long_term": "1-2年（有限长期影响）",
    },
    "severe": {
        "short_term": "1-3个月",
        "medium_term": "3-12个月",
        "long_term": "1-5年（显著长期影响）",
    },
    "critical": {
        "short_term": "1-3个月",
        "medium_term": "3-12个月",
        "long_term": "5年以上（深远长期影响）",
    },
}

# ══════════════════════════════════════════════════════════════════
# 合并分类的documents前缀
# ══════════════════════════════════════════════════════════════════

CATEGORY_DOC_PREFIX = "CATEGORY:"
SEVERITY_DOC_PREFIX = "SEVERITY:"


# ══════════════════════════════════════════════════════════════════
# Rerank 分类函数
# ══════════════════════════════════════════════════════════════════


async def _rerank_classify_combined(
    event_text: str,
    category_descriptions: dict[str, str],
    severity_descriptions: dict[str, str],
    base_url: str,
    api_key: str,
    model: str,
) -> tuple[
    tuple[str, float, dict[str, float]],
    tuple[str, float, dict[str, float]],
]:
    """
    使用 Jina Rerank 模型同时分类事件类别和严重度。

    将类别和严重度描述合并到一个documents列表，通过前缀区分，
    实现单次API调用完成两种分类。

    Returns:
        tuple: ((类别结果, 类别置信度, 类别得分字典), (严重度结果, 严重度置信度, 严重度得分字典))
    """
    categories = list(category_descriptions.keys())
    severities = list(severity_descriptions.keys())

    documents: list[str] = [f"{CATEGORY_DOC_PREFIX}{category_descriptions[cat]}" for cat in categories] + [
        f"{SEVERITY_DOC_PREFIX}{severity_descriptions[sev]}" for sev in severities
    ]

    url = base_url.rstrip("/") + "/rerank"

    query = f"这条新闻「{event_text}」属于什么类别的事件？同时评估该事件的严重度（轻微/一般/严重/重大）。"

    MAX_QUERY_LENGTH = 24000  # noqa: N806
    if len(query) > MAX_QUERY_LENGTH:
        logger.warning(
            f"Combined query length {len(query)} exceeds {MAX_QUERY_LENGTH}, falling back to keyword classification"
        )
        raise ValueError("Query length exceeds API limit")

    payload: dict[str, Any] = {
        "model": model,
        "query": query,
        "documents": documents,
        "top_n": len(documents),
    }

    logger.debug(f"Calling Jina Rerank API (combined): url={url}, model={model}")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()

    results = data.get("results", [])
    if not results:
        logger.warning("Jina Rerank API returned empty results, falling back to keyword classification")
        raise ValueError("Empty rerank results")

    category_scores: dict[str, float] = {}
    severity_scores: dict[str, float] = {}

    for item in results:
        idx = item.get("index", 0)
        score = item.get("relevance_score", item.get("score", 0.0))
        if idx < len(categories):
            category_scores[categories[idx]] = score
        elif idx >= len(categories) and (idx - len(categories)) < len(severities):
            severity_scores[severities[idx - len(categories)]] = score
        else:
            logger.warning(
                f"Jina Rerank returned unexpected index {idx}, "
                f"expected range [0, {len(categories) + len(severities) - 1}]"
            )

    if not category_scores:
        logger.warning("No category scores returned from Jina Rerank, falling back to keyword classification")
        raise ValueError("No valid category scores from rerank")

    max_category = max(category_scores, key=category_scores.__getitem__)
    max_category_score = category_scores[max_category]
    category_total = sum(category_scores.values())
    category_confidence = max_category_score / category_total if category_total > 0 else 0.0

    if not severity_scores:
        logger.warning("No severity scores returned from Jina Rerank, falling back to keyword classification")
        raise ValueError("No valid severity scores from rerank")

    max_severity = max(severity_scores, key=severity_scores.__getitem__)
    max_severity_score = severity_scores[max_severity]
    severity_total = sum(severity_scores.values())
    severity_confidence = max_severity_score / severity_total if severity_total > 0 else 0.0

    logger.info(
        f"Rerank classification (combined): category={max_category}, "
        f"cat_conf={category_confidence:.4f}, severity={max_severity}, "
        f"sev_conf={severity_confidence:.4f}"
    )

    return (
        (max_category, category_confidence, category_scores),
        (max_severity, severity_confidence, severity_scores),
    )


def _keyword_classify(
    event_text: str,
    keywords: dict[str, list[str]],
) -> tuple[str, float, dict[str, float]]:
    """
    使用关键词匹配进行分类（回退方案）。

    Returns:
        tuple: (分类结果, 置信度, 各类别得分字典)
    """
    event_lower = event_text.lower()
    scores: dict[str, float] = {}

    for category, kws in keywords.items():
        score = sum(1 for kw in kws if kw in event_lower)
        scores[category] = float(score)

    if not any(scores.values()):
        return "general", 0.0, scores

    max_score = max(scores.values())
    max_category = max(scores, key=scores.__getitem__)

    total_score = sum(scores.values())
    confidence = max_score / total_score if total_score > 0 else 0.0

    return max_category, confidence, scores


# ══════════════════════════════════════════════════════════════════
# 分类器类
# ══════════════════════════════════════════════════════════════════


class EventClassifier:
    """事件分类器：根据事件描述判断事件性质"""

    def __init__(
        self,
        use_rerank: bool = True,
        rerank_base_url: str | None = None,
        rerank_api_key: str | None = None,
        rerank_model: str | None = None,
    ) -> None:
        """
        初始化事件分类器。

        Args:
            use_rerank: 是否使用rerank模型进行分类
            rerank_base_url: Rerank API 地址
            rerank_api_key: Rerank API Key
            rerank_model: Rerank 模型名称
        """
        self.use_rerank = use_rerank
        self.rerank_base_url = rerank_base_url or os.environ.get("RERANKER_BASE_URL", "https://api.jina.ai/v1")
        self.rerank_api_key = rerank_api_key or os.environ.get("RERANKER_API_KEY", "")
        self.rerank_model = rerank_model or os.environ.get("RERANKER_MODEL", "jina-reranker-v1-base-en")

        if self.use_rerank and not self.rerank_api_key:
            logger.warning(
                "Jina Rerank is enabled (use_rerank=True) but no API key is "
                "configured. Falling back to keyword classification."
            )

    async def classify_with_severity(self, event_text: str) -> tuple[str, float, str, float]:
        """
        同时分类事件类别和严重度，在 rerank 模式下仅调用一次 API。

        Args:
            event_text: 事件描述文本

        Returns:
            tuple: (类别结果, 类别置信度, 严重度结果, 严重度置信度)
        """
        try:
            if self.use_rerank and self.rerank_api_key:
                (
                    (category, cat_conf, _),
                    (severity, sev_conf, _),
                ) = await _rerank_classify_combined(
                    event_text,
                    CATEGORY_DESCRIPTIONS,
                    SEVERITY_DESCRIPTIONS,
                    self.rerank_base_url,
                    self.rerank_api_key,
                    self.rerank_model,
                )
                return category, cat_conf, severity, sev_conf
        except Exception as e:
            logger.warning("Rerank classification failed (%s), falling back to keyword classification", e)

        cat_result = _keyword_classify(event_text, CATEGORY_KEYWORDS)
        sev_result = _keyword_classify(event_text, SEVERITY_KEYWORDS)
        return (
            cat_result[0],
            cat_result[1],
            sev_result[0],
            sev_result[1],
        )

    def get_category_name(self, category: str) -> str:
        """获取类别的中文名称"""
        return CATEGORY_NAMES.get(category, category)

    def get_severity_name(self, severity: str) -> str:
        """获取严重度的中文名称"""
        return SEVERITY_NAMES.get(severity, severity)

    def get_time_ranges(self, severity: str) -> dict[str, str]:
        """
        根据严重度获取对应的时间范围。

        Args:
            severity: 严重度标签

        Returns:
            dict: 时间范围字典，包含short_term, medium_term, long_term
        """
        return SEVERITY_TO_TIME_RANGES.get(severity, SEVERITY_TO_TIME_RANGES["moderate"])
