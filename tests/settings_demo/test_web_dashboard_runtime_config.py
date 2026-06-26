from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pytest

import main
from backend.app.services.settings_service import load_app_settings, save_app_settings
from models import EventSource, NormalizedEvent
from tests.settings_demo.conftest import public_dns_result, reset_runtime_state


@dataclass(frozen=True, slots=True)
class _FakeCrewResult:
    raw: str


def _sample_event() -> NormalizedEvent:
    return NormalizedEvent(
        event_id="evt-web-runtime",
        source=EventSource.NEWS,
        raw_content="客户 P102 向虚拟币商户分拆转账",
        title="疑似高危交易",
        structured_data={"customer": "P102"},
        timestamp=datetime(2026, 6, 14, 12, 0),
        ingestion_time=datetime(2026, 6, 14, 12, 1),
        trace_id="trace-web-runtime",
        content_type="text",
        event_type="反洗钱",
        risk_level="high",
        risk_score=0.8,
        summary="疑似高危交易",
    )


@pytest.mark.anyio
async def test_simulate_dashboard_uses_persisted_web_runtime_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    monkeypatch.setattr(
        "backend.app.services.url_safety.socket.getaddrinfo", public_dns_result
    )
    settings, _ = load_app_settings()
    settings["runtime_config"]["RAGFLOW_ENABLED"] = True
    settings["runtime_config"]["RAGFLOW_BASE_URL"] = "https://saved-ragflow.example"
    settings["runtime_config"]["RAGFLOW_API_KEY"] = "saved-ragflow-key"
    settings["runtime_config"]["RAGFLOW_DATASET_IDS"] = ["saved-a", "saved-b"]
    settings["runtime_config"]["RAGFLOW_TIMEOUT_SECONDS"] = 33.5
    settings["runtime_config"]["RAGFLOW_MAX_CONTEXT_CHARS"] = 1234
    settings["runtime_config"]["RAGFLOW_FAIL_OPEN"] = False
    settings["runtime_config"]["LLM_MODEL"] = "saved-dashboard-model"
    settings["runtime_config"]["LLM_REASON_MODEL"] = "saved-dashboard-reason-model"
    settings["runtime_config"]["LLM_REASON_BASE_URL"] = (
        "https://saved-reason.example/v1"
    )
    settings["runtime_config"]["LLM_REASON_API_KEY"] = "saved-reason-key"
    settings["runtime_config"]["RERANKER_BASE_URL"] = (
        "https://saved-reranker.example/v1"
    )
    settings["runtime_config"]["RERANKER_API_KEY"] = "saved-reranker-key"
    settings["runtime_config"]["RERANKER_MODEL"] = "saved-reranker-model"
    save_app_settings(settings)
    reset_runtime_state()
    monkeypatch.setenv("RAGFLOW_BASE_URL", "https://env-ragflow.example")
    monkeypatch.setenv("RAGFLOW_API_KEY", "env-ragflow-key")
    monkeypatch.setenv("LLM_MODEL", "env-dashboard-model")

    from backend.app.services.web_runtime_config import load_web_runtime_config

    config = load_web_runtime_config()
    captured: dict[str, Any] = {}

    async def fake_retrieve_financial_knowledge(
        analysis_config: dict[str, Any],
        event: NormalizedEvent,
        *,
        stage: str,
    ) -> dict[str, Any]:
        captured["analysis_config"] = analysis_config
        captured["stage"] = stage
        captured["event_id"] = event.event_id
        return {"items": []}

    class FakeEventClassifier:
        def __init__(
            self,
            use_rerank: bool = True,
            rerank_base_url: str | None = None,
            rerank_api_key: str | None = None,
            rerank_model: str | None = None,
        ) -> None:
            captured["classifier_config"] = {
                "use_rerank": use_rerank,
                "base_url": rerank_base_url,
                "api_key": rerank_api_key,
                "model": rerank_model,
            }

        async def classify_with_severity(
            self, text: str
        ) -> tuple[str, float, str, float]:
            return ("finance", 1.0, "high", 1.0)

        def get_category_name(self, category: str) -> str:
            return category

        def get_severity_name(self, severity: str) -> str:
            return severity

    class FakeAgent:
        def __init__(self, **kwargs: Any) -> None:
            captured.setdefault("agent_llms", []).append(kwargs["llm"])

    class FakeTask:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

    class FakeCrew:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

        async def kickoff_async(self) -> _FakeCrewResult:
            return _FakeCrewResult(raw="dashboard ok")

    def fake_get_llm_for(stage: str, *, config: dict[str, Any] | None = None) -> str:
        captured.setdefault("llm_calls", []).append((stage, config))
        return f"llm:{stage}:{config['llm_reason']['model'] if config else 'missing'}"

    monkeypatch.setattr(main, "get_llm_for", fake_get_llm_for)
    monkeypatch.setattr(
        main, "retrieve_financial_knowledge", fake_retrieve_financial_knowledge
    )
    monkeypatch.setattr(main, "EventClassifier", FakeEventClassifier)
    monkeypatch.setattr(main, "Agent", FakeAgent)
    monkeypatch.setattr(main, "Task", FakeTask)
    monkeypatch.setattr(main, "Crew", FakeCrew)
    monkeypatch.setattr(
        main, "get_intent_analysis_task", lambda **kwargs: FakeTask(**kwargs)
    )
    monkeypatch.setattr(
        main, "get_trend_prediction_task", lambda **kwargs: FakeTask(**kwargs)
    )

    # When
    result = await main.simulate_dashboard(config, _sample_event(), {})

    # Then
    ragflow_config = captured["analysis_config"]["ragflow"]["client"]
    assert captured["stage"] == "dashboard"
    assert captured["event_id"] == "evt-web-runtime"
    assert ragflow_config.base_url == "https://saved-ragflow.example"
    assert ragflow_config.api_key == "saved-ragflow-key"
    assert ragflow_config.dataset_ids == ["saved-a", "saved-b"]
    assert config["ragflow"]["client"].timeout_seconds == 33.5
    assert ragflow_config.timeout_seconds == 33.5
    assert ragflow_config.max_context_chars == 1234
    assert ragflow_config.fail_open is False
    assert captured["analysis_config"]["llm"]["model"] == "saved-dashboard-model"
    assert (
        captured["analysis_config"]["llm_reason"]["model"]
        == "saved-dashboard-reason-model"
    )
    assert captured["llm_calls"] == [("dashboard", config)]
    assert captured["agent_llms"] == [
        "llm:dashboard:saved-dashboard-reason-model",
        "llm:dashboard:saved-dashboard-reason-model",
    ]
    assert captured["classifier_config"] == {
        "use_rerank": True,
        "base_url": "https://saved-reranker.example/v1",
        "api_key": "saved-reranker-key",
        "model": "saved-reranker-model",
    }
    assert result["report"] == "dashboard ok"
