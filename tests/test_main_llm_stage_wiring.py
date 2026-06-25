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
        self.llm_stages: list[str] = []
        self.reasoning_stages: list[str] = []
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

    def fake_get_llm_for(stage: str) -> str:
        recorder.llm_stages.append(stage)
        return f"llm:{stage}"

    def fake_reasoning_kwargs_for(stage: str) -> dict[str, str]:
        recorder.reasoning_stages.append(stage)
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
    await main.classify_event({}, _sample_event())
    await main.normalize_payload_to_event(
        {"data": "客户 P102 向虚拟币商户分拆转账"},
        {},
    )

    assert stage_recorder.llm_stages == ["classify", "normalize"]
    assert [kwargs["llm"] for kwargs in stage_recorder.agent_kwargs] == [
        "llm:classify",
        "llm:normalize",
    ]
    assert stage_recorder.reasoning_stages == []


@pytest.mark.asyncio
async def test_main_attaches_reasoning_kwargs_only_to_risk_agents(
    stage_recorder: StageRecorder,
) -> None:
    event = _sample_event()

    await main.evaluate_risk({}, event, {})
    await main.second_evaluate_risk({}, event, {})
    await main.simulate_dashboard({}, event, {})

    assert stage_recorder.llm_stages == ["risk_first", "risk_second", "dashboard"]
    assert stage_recorder.reasoning_stages == ["risk_first", "risk_second"]
    assert stage_recorder.agent_kwargs[0]["planning_config"] == "planning:risk_first"
    assert stage_recorder.agent_kwargs[1]["planning_config"] == "planning:risk_second"
    assert "planning_config" not in stage_recorder.agent_kwargs[2]
