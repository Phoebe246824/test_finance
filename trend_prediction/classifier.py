"""
Sentinel Edge 金融风控 — 风险类型与处置严重度评估模块

基于 Jina Rerank API 的事件分类器，支持：
- 银行零售风控风险类型分类
- 4 级处置严重度评估（轻微、一般、严重、重大）
- 严重度到案件级观察时间范围的动态映射
- 关键词匹配回退方案
"""

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════
# 金融风控风险类型分类（risk type classification）
# ══════════════════════════════════════════════════════════════════

CATEGORY_DESCRIPTIONS: dict[str, str] = {
    "aml_structuring": "这条银行零售风控事件属于反洗钱/分拆交易风险，涉及多账户分散转账、资金归集、规避监测、可疑出入金或冻结复核。",  # noqa: E501
    "fraud_transfer": "这条银行零售风控事件属于涉诈转账风险，涉及诱导投资、保证金、高收益返利、拒绝提现、投诉线索或疑似诈骗收款方。",  # noqa: E501
    "mule_account": "这条银行零售风控事件属于跑分/资金归集账户风险，涉及新账户、多人转入、快速出金、空备注、收款网络或资金中转。",  # noqa: E501
    "crypto_merchant_risk": "这条银行零售风控事件属于虚拟币商户风险，涉及虚拟币平台商户、币商、入金出金、保证金或虚拟资产相关交易。",  # noqa: E501
    "account_takeover": "这条银行零售风控事件属于账户盗用/异地新设备风险，涉及陌生设备、境外或异地 IP、验证码异常、回访失败或非常用登录。",  # noqa: E501
    "loan_fraud": "这条银行零售风控事件属于贷款欺诈/包装流水风险，涉及经营贷、资料造假、流水包装、纳税凭证异常或贷前欺诈。",  # noqa: E501
    "blacklist_hit": "这条银行零售风控事件属于黑名单命中风险，涉及黑名单客户、涉诈账户、高风险商户、敏感关键词或已知风险主体。",  # noqa: E501
    "normal_baseline": "这条银行零售风控事件属于低风险/正常行为基线，涉及工资入账、日常消费、常用设备、稳定频率或历史行为一致。",  # noqa: E501
}

CATEGORY_NAMES: dict[str, str] = {
    "aml_structuring": "反洗钱/分拆交易",
    "fraud_transfer": "涉诈转账",
    "mule_account": "跑分/资金归集账户",
    "crypto_merchant_risk": "虚拟币商户风险",
    "account_takeover": "账户盗用/异地新设备",
    "loan_fraud": "贷款欺诈/包装流水",
    "blacklist_hit": "黑名单命中",
    "normal_baseline": "低风险/正常行为基线",
    "finance": "金融风控",
    "general": "综合",
}

FINANCIAL_RISK_CATEGORIES = frozenset(CATEGORY_DESCRIPTIONS)

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "aml_structuring": [
        "反洗钱",
        "洗钱",
        "分拆交易",
        "分拆",
        "分散转出",
        "分散转账",
        "多账户",
        "新开户账户",
        "开户时间不足",
        "资金归集",
        "归集",
        "规避监测",
        "可疑交易",
        "冻结",
        "出金",
        "立即复核",
    ],
    "fraud_transfer": [
        "涉诈",
        "诈骗",
        "诱导投资",
        "保证金",
        "高收益",
        "返利",
        "拒绝提现",
        "投诉",
        "客服话术",
        "投资平台",
        "收款账户",
        "被骗",
    ],
    "mule_account": [
        "跑分",
        "资金归集",
        "多人转入",
        "多客户",
        "集中转入",
        "立即向外部支付通道出金",
        "快速出金",
        "空备注",
        "新账户",
        "开户不足24小时",
        "批量清算",
    ],
    "crypto_merchant_risk": [
        "虚拟币",
        "币商",
        "虚拟资产",
        "平台商户",
        "虚拟币平台",
        "入金",
        "出金",
        "币流",
        "交易所",
    ],
    "account_takeover": [
        "账户盗用",
        "异地",
        "境外",
        "IP",
        "新设备",
        "首次登录",
        "非常用设备",
        "短信验证码",
        "验证码",
        "多次失败",
        "回访电话无人接听",
        "无人接听",
        "常驻",
    ],
    "loan_fraud": [
        "经营贷",
        "贷款",
        "贷前",
        "小微贷款",
        "资料造假",
        "包装流水",
        "流水突然放大",
        "纳税凭证",
        "银行流水",
        "同设备登录",
        "贷款欺诈",
    ],
    "blacklist_hit": [
        "黑名单",
        "命中",
        "涉诈账户",
        "高风险账户",
        "高风险商户",
        "敏感词",
        "风险关键词",
        "曾被多名客户投诉",
    ],
    "normal_baseline": [
        "工资入账",
        "刷卡消费",
        "日常消费",
        "常用手机",
        "常用设备",
        "交易频率稳定",
        "历史行为一致",
        "正常行为",
        "低风险",
        "消费地点",
    ],
}

# ══════════════════════════════════════════════════════════════════
# 处置严重度分类（case handling severity classification）
# ══════════════════════════════════════════════════════════════════

SEVERITY_DESCRIPTIONS: dict[str, str] = {
    "minor": "这条银行风控事件属于轻微处置优先级，交易行为大体正常或风险信号较弱，通常适合暂存、观察或作为正常行为基线。",  # noqa: E501
    "moderate": "这条银行风控事件属于一般处置优先级，存在局部异常或信息缺口，需要持续观察、补充核验或进入规则复核。",  # noqa: E501
    "severe": "这条银行风控事件属于严重处置优先级，存在明显异常交易、可疑主体或账户风险，需要人工复核、关联排查或临时拦截。",  # noqa: E501
    "critical": "这条银行风控事件属于重大处置优先级，存在反洗钱、涉诈、冻结止付、黑名单命中或快速资金转移等强风险信号，需要立即复核并控制后续出入金。",  # noqa: E501
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
        "正常",
        "稳定",
        "一致",
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
        "观察",
        "核验",
        "信息不足",
    ],
    "severe": [
        "严重",
        "系统性",
        "广泛",
        "持续",
        "大规模",
        "严重影响",
        "系统性影响",
        "深度影响",
        "长期影响",
        "广泛影响",
        "异常转账",
        "涉诈账户",
        "首次登录",
        "新设备",
        "境外",
        "短信验证码",
        "回访电话无人接听",
        "经营贷",
        "流水突然放大",
        "纳税凭证",
        "包装流水",
        "同设备登录",
        "新收款账户",
        "开户不足24小时",
        "快速出金",
    ],
    "critical": [
        "重大",
        "反洗钱",
        "洗钱",
        "分拆交易",
        "资金归集",
        "立即复核",
        "冻结",
        "止付",
        "黑名单",
        "贷款欺诈",
        "立即向外部支付通道出金",
        "多个交易对手",
        "虚拟币",
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
        "short_term": "当前至24小时",
        "medium_term": "1-7天",
        "long_term": "7-30天（观察沉淀）",
    },
    "moderate": {
        "short_term": "当前至24小时",
        "medium_term": "1-7天",
        "long_term": "7-30天（复盘优化）",
    },
    "severe": {
        "short_term": "当前至24小时",
        "medium_term": "1-7天",
        "long_term": "7-30天（持续监测）",
    },
    "critical": {
        "short_term": "当前至24小时",
        "medium_term": "1-7天",
        "long_term": "7-30天（案件复盘与规则沉淀）",
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
    使用 Jina Rerank 模型同时分类金融风控风险类型和处置严重度。

    将类别和严重度描述合并到一个documents列表，通过前缀区分，
    实现单次API调用完成两种分类。

    Returns:
        tuple: ((风险类型结果, 类型置信度, 类型得分字典), (严重度结果, 严重度置信度, 严重度得分字典))
    """
    categories = list(category_descriptions.keys())
    severities = list(severity_descriptions.keys())

    documents: list[str] = [f"{CATEGORY_DOC_PREFIX}{category_descriptions[cat]}" for cat in categories] + [
        f"{SEVERITY_DOC_PREFIX}{severity_descriptions[sev]}" for sev in severities
    ]

    url = base_url.rstrip("/") + "/rerank"

    query = (
        f"这条银行零售风控事件「{event_text}」属于哪一种风险类型？"
        "同时评估该案件的处置严重度（轻微/一般/严重/重大）。"
    )

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
    """金融风控事件分类器：根据事件描述判断风险类型和处置严重度"""

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
        同时分类风险类型和处置严重度，在 rerank 模式下仅调用一次 API。

        Args:
            event_text: 事件描述文本

        Returns:
            tuple: (风险类型结果, 类型置信度, 严重度结果, 严重度置信度)
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
        """获取风险类型的中文名称"""
        return CATEGORY_NAMES.get(category, category)

    def get_severity_name(self, severity: str) -> str:
        """获取严重度的中文名称"""
        return SEVERITY_NAMES.get(severity, severity)

    def get_time_ranges(self, severity: str) -> dict[str, str]:
        """
        根据处置严重度获取对应的案件观察时间范围。

        Args:
            severity: 严重度标签

        Returns:
            dict: 时间范围字典，包含short_term, medium_term, long_term
        """
        return SEVERITY_TO_TIME_RANGES.get(severity, SEVERITY_TO_TIME_RANGES["moderate"])
