import pytest

import trend_prediction.classifier as classifier_module
from trend_prediction.classifier import (
    CATEGORY_DESCRIPTIONS,
    CATEGORY_KEYWORDS,
    SEVERITY_DESCRIPTIONS,
    EventClassifier,
    FINANCIAL_RISK_CATEGORIES,
    _rerank_classify_combined,
)
from trend_prediction.task_templates import _get_adaptive_prompt


@pytest.mark.asyncio
async def test_keyword_fallback_classifies_ip_account_takeover_case_insensitively() -> None:
    event_text = "客户登录来源IP突变，设备指纹与历史常用终端不一致。"
    classifier = EventClassifier(use_rerank=False)

    category, confidence, _, _ = await classifier.classify_with_severity(event_text)

    assert category == "account_takeover"
    assert confidence > 0


@pytest.mark.asyncio
async def test_keyword_fallback_defaults_missing_severity_to_moderate() -> None:
    event_text = "客户账户疑似账户盗用。"
    classifier = EventClassifier(use_rerank=False)

    category, _, severity, severity_confidence = await classifier.classify_with_severity(event_text)

    assert category == "account_takeover"
    assert severity == "moderate"
    assert severity_confidence == 0.0


@pytest.mark.asyncio
async def test_keyword_fallback_classifies_seed_mule_account_as_mule_account() -> None:
    event_text = "多个客户向同一新开户账户集中转账，资金随后快速出金至外部支付通道，疑似跑分或资金归集账户。"
    classifier = EventClassifier(use_rerank=False)

    category, confidence, _, _ = await classifier.classify_with_severity(event_text)

    assert category == "mule_account"
    assert confidence > 0


@pytest.mark.asyncio
async def test_keyword_fallback_keeps_non_financial_text_out_of_legacy_domain_categories() -> None:
    event_text = "芯片公司发布新一代GPU和人工智能大模型加速方案。"
    classifier = EventClassifier(use_rerank=False)

    category, confidence, _, _ = await classifier.classify_with_severity(event_text)

    assert category == "general"
    assert confidence == 0.0


def test_classifier_candidate_categories_are_financial_risk_only() -> None:
    legacy_domain_categories = {
        "intl_politics",
        "tech",
        "economy",
        "society",
        "public_health",
        "energy",
        "finance",
    }

    assert set(CATEGORY_DESCRIPTIONS) == FINANCIAL_RISK_CATEGORIES
    assert set(CATEGORY_KEYWORDS) == FINANCIAL_RISK_CATEGORIES
    assert legacy_domain_categories.isdisjoint(CATEGORY_DESCRIPTIONS)
    assert legacy_domain_categories.isdisjoint(CATEGORY_KEYWORDS)


def test_financial_risk_categories_route_to_finance_prompt() -> None:
    prompt = _get_adaptive_prompt("mule_account", "intent_analysis")

    assert "# 金融风控意图分析报告" in prompt
    assert "银行零售风控" in prompt


def test_general_trend_prompt_replaces_time_range_placeholders() -> None:
    prompt = _get_adaptive_prompt("general", "trend_prediction", severity="critical")

    assert "{short_term}" not in prompt
    assert "{medium_term}" not in prompt
    assert "{long_term}" not in prompt
    assert "当前至24小时" in prompt
    assert "7-30天（案件复盘与规则沉淀）" in prompt


def test_legacy_domain_categories_use_general_fallback_prompts() -> None:
    prompt = _get_adaptive_prompt("tech", "trend_prediction", severity="critical")

    assert "# 风险演化预测报告" in prompt
    assert "# 科技趋势预测报告" not in prompt
    assert "{short_term}" not in prompt
    assert "当前至24小时" in prompt


class _FakeResponse:
    def __init__(self, results: list[dict[str, int | float]]) -> None:
        self._results = results

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, list[dict[str, int | float]]]:
        return {"results": self._results}


class _FakeAsyncClient:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        return None

    async def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, str | list[str] | int],
        timeout: float,
    ) -> _FakeResponse:
        assert url == "https://rerank.test/rerank"
        assert headers["Authorization"] == "Bearer test-key"
        assert json["top_n"] == len(CATEGORY_DESCRIPTIONS) + len(SEVERITY_DESCRIPTIONS)
        assert timeout == 30.0
        return self._response


@pytest.mark.asyncio
async def test_rerank_combined_maps_document_indexes_by_prefix_group(monkeypatch: pytest.MonkeyPatch) -> None:
    categories = list(CATEGORY_DESCRIPTIONS)
    severities = list(SEVERITY_DESCRIPTIONS)
    response = _FakeResponse(
        [
            {"index": categories.index("mule_account"), "relevance_score": 0.8},
            {
                "index": len(categories) + severities.index("critical"),
                "relevance_score": 0.6,
            },
        ]
    )
    monkeypatch.setattr(
        classifier_module.httpx,
        "AsyncClient",
        lambda: _FakeAsyncClient(response),
    )

    (category, category_confidence, _), (severity, severity_confidence, _) = await _rerank_classify_combined(
        "多个客户向同一新账户归集并快速出金。",
        CATEGORY_DESCRIPTIONS,
        SEVERITY_DESCRIPTIONS,
        "https://rerank.test",
        "test-key",
        "test-model",
    )

    assert category == "mule_account"
    assert category_confidence == 1.0
    assert severity == "critical"
    assert severity_confidence == 1.0
