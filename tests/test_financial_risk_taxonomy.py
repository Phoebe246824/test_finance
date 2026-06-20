import asyncio

from crewai import Agent

from trend_prediction.classifier import EventClassifier
from trend_prediction.task_templates import (
    get_intent_analysis_task,
    get_trend_prediction_task,
)


AML_EVENT = (
    "2026年6月14日 23:48，【P102# 客户B】再次通过手机银行向4个新开户账户分散转出 "
    "196000 元，随后其中两个收款账户在10分钟内继续转入同一虚拟币平台商户。"
    "交易行为疑似分拆交易与洗钱资金归集，反洗钱系统要求立即复核并冻结后续出金。"
)


ACCOUNT_TAKEOVER_EVENT = (
    "2026年6月16日 08:45，【P107# 客户G】常驻上海，但账户在境外 IP 和新设备上登录后，"
    "5分钟内向【P307# 新收款人】转账 120000 元，短信验证码多次失败后才通过，"
    "客服回访电话无人接听。"
)

LOAN_FRAUD_EVENT = (
    "2026年6月15日 15:20，【P106# 个体工商户F】提交经营贷申请 80 万元，系统发现其近7日流水突然放大，"
    "多个交易对手与申请人存在同设备登录记录，纳税凭证与银行流水时间不一致，疑似包装流水和贷款欺诈。"
)

MULE_ACCOUNT_EVENT = (
    "2026年6月16日 12:30，【P108# 客户H】、【P109# 客户I】、【P110# 客户J】分别向"
    "【P308# 新收款账户】转入 30000 元、28000 元、35000 元，随后【P308# 新收款账户】"
    "立即向外部支付通道出金。该账户开户不足24小时。"
)


def classify_without_rerank(text: str) -> tuple[str, float, str, float]:
    classifier = EventClassifier(use_rerank=False)
    return asyncio.run(classifier.classify_with_severity(text))


def test_aml_structuring_event_is_classified_as_financial_risk_type():
    category, confidence, severity, severity_confidence = classify_without_rerank(AML_EVENT)
    classifier = EventClassifier(use_rerank=False)

    assert category == "aml_structuring"
    assert classifier.get_category_name(category) == "反洗钱/分拆交易"
    assert confidence > 0
    assert severity == "critical"
    assert classifier.get_severity_name(severity) == "重大"
    assert severity_confidence > 0


def test_account_takeover_event_is_classified_as_account_takeover():
    category, confidence, severity, _ = classify_without_rerank(ACCOUNT_TAKEOVER_EVENT)
    classifier = EventClassifier(use_rerank=False)

    assert category == "account_takeover"
    assert classifier.get_category_name(category) == "账户盗用/异地新设备"
    assert confidence > 0
    assert severity in {"severe", "critical"}


def test_loan_fraud_event_has_high_handling_severity():
    category, _, severity, severity_confidence = classify_without_rerank(LOAN_FRAUD_EVENT)

    assert category == "loan_fraud"
    assert severity in {"severe", "critical"}
    assert severity_confidence > 0


def test_mule_account_event_has_high_handling_severity():
    category, _, severity, severity_confidence = classify_without_rerank(MULE_ACCOUNT_EVENT)

    assert category == "mule_account"
    assert severity in {"severe", "critical"}
    assert severity_confidence > 0


def test_financial_risk_type_uses_case_level_prompt():
    classifier = EventClassifier(use_rerank=False)
    agent = Agent(role="r", goal="g", backstory="b", allow_delegation=False, verbose=False)
    intent_task = get_intent_analysis_task(
        event_text=AML_EVENT,
        classifier=classifier,
        category="aml_structuring",
        confidence=0.8,
        agent=agent,
    )
    trend_task = get_trend_prediction_task(
        event_text=AML_EVENT,
        intent_task=intent_task,
        classifier=classifier,
        category="aml_structuring",
        confidence=0.8,
        agent=agent,
        severity="critical",
        severity_confidence=0.7,
    )

    assert "反洗钱风险演化与处置建议报告" in trend_task.description
    assert "分拆交易" in trend_task.description
    assert "冻结" in trend_task.description
    assert "人工复核" in trend_task.description
    assert "市场恐慌" not in trend_task.description
    assert "金融危机" not in trend_task.description
    assert "金融体系重塑" not in trend_task.description
