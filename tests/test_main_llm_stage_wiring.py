from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pytest

import main
from models import EventSource, NormalizedEvent


@dataclass(frozen=True, slots=True)
class FakeCrewResult:
    raw: str


class StageRecorder:
    def __init__(self) -> None:
        self.llm_calls: list[tuple[str, dict[str, Any]]] = []
        self.reasoning_calls: list[tuple[str, dict[str, Any]]] = []
        self.classifier_configs: list[dict[str, Any]] = []
        self.agent_kwargs: list[dict[str, Any]] = []


class FakeAgent:
    def __init__(self, **kwargs: Any) -> None:
        recorder: StageRecorder = kwargs.pop("_recorder")
        recorder.agent_kwargs.append(kwargs)


class FakeTask:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


class FakeCrew:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs

    async def kickoff_async(self, *args: Any, **kwargs: Any) -> FakeCrewResult:
        return FakeCrewResult(
            raw=(
                '{"event_type":"反洗钱",'
                '"key_entities":{"customer":"P102"},'
                '"summary":"疑似高危交易",'
                '"dimension_scores":{"customer_identity":0.8,'
                '"transaction_behavior":0.8,"counterparty":0.8,'
                '"amount_velocity":0.8,"device_geo":0.8,'
                '"history_context":0.8,"compliance_signal":0.8},'
                '"risk_level":"high","risk_score":0.8,'
                '"reasoning":"stage routed","report":"ok"}'
            )
        )


def _sample_event() -> NormalizedEvent:
    return NormalizedEvent(
        event_id="E-STAGE",
        source=EventSource.NEWS,
        raw_content="客户 P102 向虚拟币商户分拆转账",
        title="疑似高危交易",
        structured_data={"customer": "P102"},
        timestamp=datetime(2026, 6, 14, 12, 0),
        ingestion_time=datetime(2026, 6, 14, 12, 1),
        trace_id="trace-stage",
        content_type="text",
        event_type="反洗钱",
        risk_level="high",
        risk_score=0.8,
        summary="疑似高危交易",
    )


@pytest.fixture
def stage_recorder(monkeypatch: pytest.MonkeyPatch) -> StageRecorder:
    recorder = StageRecorder()

    def fake_get_llm_for(stage: str, *, config: dict[str, Any] | None = None) -> str:
        recorder.llm_calls.append((stage, config or {}))
        return f"llm:{stage}"

    def fake_reasoning_kwargs_for(stage: str, *, config: dict[str, Any] | None = None) -> dict[str, str]:
        recorder.reasoning_calls.append((stage, config or {}))
        return {"planning_config": f"planning:{stage}"}

    def fake_agent(**kwargs: Any) -> FakeAgent:
        return FakeAgent(_recorder=recorder, **kwargs)

    async def fake_retrieve_financial_knowledge(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"items": []}

    def fake_intent_task(**kwargs: Any) -> FakeTask:
        return FakeTask(name="intent", **kwargs)

    def fake_trend_task(**kwargs: Any) -> FakeTask:
        return FakeTask(name="trend", **kwargs)

    class FakeEventClassifier:
        def __init__(
            self,
            use_rerank: bool = True,
            rerank_base_url: str | None = None,
            rerank_api_key: str | None = None,
            rerank_model: str | None = None,
        ) -> None:
            recorder.classifier_configs.append(
                {
                    "use_rerank": use_rerank,
                    "base_url": rerank_base_url,
                    "api_key": rerank_api_key,
                    "model": rerank_model,
                }
            )

        async def classify_with_severity(self, text: str) -> tuple[str, float, str, float]:
            return ("finance", 1.0, "high", 1.0)

        def get_category_name(self, category: str) -> str:
            return category

        def get_severity_name(self, severity: str) -> str:
            return severity

    monkeypatch.setattr(main, "get_llm_for", fake_get_llm_for)
    monkeypatch.setattr(main, "reasoning_kwargs_for", fake_reasoning_kwargs_for)
    monkeypatch.setattr(main, "Agent", fake_agent)
    monkeypatch.setattr(main, "Task", FakeTask)
    monkeypatch.setattr(main, "Crew", FakeCrew)
    monkeypatch.setattr(main, "retrieve_financial_knowledge", fake_retrieve_financial_knowledge)
    monkeypatch.setattr(main, "get_intent_analysis_task", fake_intent_task)
    monkeypatch.setattr(main, "get_trend_prediction_task", fake_trend_task)
    monkeypatch.setattr(main, "EventClassifier", FakeEventClassifier)
    return recorder


@pytest.mark.asyncio
async def test_main_uses_semantic_stage_router_for_classification_and_normalization(
    stage_recorder: StageRecorder,
) -> None:
    config = {"llm": {"model": "web-base"}}

    await main.classify_event(config, _sample_event())
    await main.normalize_payload_to_event(
        {"data": "客户 P102 向虚拟币商户分拆转账"},
        config,
    )

    assert [stage for stage, _ in stage_recorder.llm_calls] == ["classify", "normalize"]
    assert [config for _, config in stage_recorder.llm_calls] == [config, config]
    assert [kwargs["llm"] for kwargs in stage_recorder.agent_kwargs] == [
        "llm:classify",
        "llm:normalize",
    ]
    assert stage_recorder.reasoning_calls == []


@pytest.mark.asyncio
async def test_main_attaches_reasoning_kwargs_only_to_risk_agents(
    stage_recorder: StageRecorder,
) -> None:
    event = _sample_event()
    config = {
        "llm": {"model": "web-base"},
        "reranker": {
            "base_url": "https://web-reranker.example/v1",
            "api_key": "web-reranker-key",
            "model": "web-reranker-model",
        },
    }

    await main.evaluate_risk(config, event, {})
    await main.second_evaluate_risk(config, event, {})
    await main.simulate_dashboard(config, event, {})

    assert [stage for stage, _ in stage_recorder.llm_calls] == [
        "risk_first",
        "risk_second",
        "dashboard",
    ]
    assert [config for _, config in stage_recorder.llm_calls] == [config, config, config]
    assert [stage for stage, _ in stage_recorder.reasoning_calls] == [
        "risk_first",
        "risk_second",
    ]
    assert [config for _, config in stage_recorder.reasoning_calls] == [config, config]
    assert stage_recorder.agent_kwargs[0]["planning_config"] == "planning:risk_first"
    assert stage_recorder.agent_kwargs[1]["planning_config"] == "planning:risk_second"
    assert "planning_config" not in stage_recorder.agent_kwargs[2]
    assert stage_recorder.classifier_configs == [
        {
            "use_rerank": True,
            "base_url": "https://web-reranker.example/v1",
            "api_key": "web-reranker-key",
            "model": "web-reranker-model",
        }
    ]
