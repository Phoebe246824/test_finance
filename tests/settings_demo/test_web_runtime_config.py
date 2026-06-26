from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pytest

import main
from backend.app.core.security import CurrentUser
from backend.app.services.analysis_service import AnalysisService
from backend.app.services.settings_service import load_app_settings, save_app_settings
from models import EventSource, NormalizedEvent
from tests.settings_demo.conftest import public_dns_result, reset_runtime_state


def test_web_runtime_config_uses_saved_values_while_cli_load_config_uses_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    monkeypatch.setenv("LLM_MODEL", "bootstrap-model")
    settings, _ = load_app_settings()
    settings["runtime_config"]["LLM_MODEL"] = "saved-web-model"
    settings["runtime_config"]["LLM_API_KEY"] = "saved-web-key"
    save_app_settings(settings)
    reset_runtime_state()
    monkeypatch.setenv("LLM_MODEL", "env-cli-model")
    monkeypatch.setenv("LLM_API_KEY", "env-cli-key")

    # When
    from backend.app.services.web_runtime_config import load_web_runtime_config

    web_config = load_web_runtime_config()
    cli_config = main.load_config()

    # Then
    assert web_config["llm"]["model"] == "saved-web-model"
    assert web_config["llm"]["api_key"] == "saved-web-key"
    assert cli_config["llm"]["model"] == "env-cli-model"
    assert cli_config["llm"]["api_key"] == "env-cli-key"


def test_web_runtime_config_falls_back_to_env_only_for_blank_secret_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    monkeypatch.setenv("LLM_MODEL", "bootstrap-model")
    settings, _ = load_app_settings()
    settings["runtime_config"]["LLM_MODEL"] = "saved-web-model"
    settings["runtime_config"]["LLM_API_KEY"] = ""
    settings["runtime_config"]["EMBEDDER_API_KEY"] = ""
    settings["runtime_config"]["RAGFLOW_API_KEY"] = ""
    settings["runtime_config"]["RAGFLOW_DATASET_ID"] = ""
    settings["runtime_config"]["RAGFLOW_DATASET_IDS"] = ["dataset-a", "dataset-b"]
    save_app_settings(settings)
    reset_runtime_state()
    monkeypatch.setenv("LLM_MODEL", "env-model-ignored-for-web")
    monkeypatch.setenv("LLM_API_KEY", "env-llm-secret")
    monkeypatch.setenv("EMBEDDER_API_KEY", "env-embedder-secret")
    monkeypatch.setenv("RAGFLOW_API_KEY", "env-ragflow-secret")

    # When
    from backend.app.services.web_runtime_config import load_web_runtime_config

    web_config = load_web_runtime_config()

    # Then
    assert web_config["llm"]["model"] == "saved-web-model"
    assert web_config["llm"]["api_key"] == "env-llm-secret"
    assert web_config["embedder"]["api_key"] == "env-embedder-secret"
    assert web_config["ragflow"]["client"].api_key == "env-ragflow-secret"
    assert web_config["ragflow"]["client"].dataset_ids == ["dataset-a", "dataset-b"]


@pytest.mark.anyio
async def test_analysis_service_passes_web_config_without_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    captured: dict[str, object] = {}
    web_config = {"llm": {"model": "saved-web-model"}}

    async def fake_process_message_detailed(
        message: str,
        config: dict | None = None,
        progress_callback: Callable[[object], None] | None = None,
    ) -> dict[str, str]:
        captured["message"] = message
        captured["config"] = config
        captured["progress_callback"] = progress_callback
        return {"event_id": "evt-1"}

    async def fake_dispatch_analysis_notifications(*, result: dict[str, str], actor: CurrentUser) -> None:
        return None

    monkeypatch.setattr(
        "backend.app.services.analysis_service.load_web_runtime_config",
        lambda: web_config,
    )
    monkeypatch.setattr(
        "backend.app.services.analysis_service.process_message_detailed",
        fake_process_message_detailed,
    )
    monkeypatch.setattr(
        "backend.app.services.analysis_service.dispatch_analysis_notifications",
        fake_dispatch_analysis_notifications,
    )

    # When
    result = await AnalysisService().analyze(
        "风险事件",
        actor=CurrentUser(username="tester", role="admin"),
    )

    # Then
    assert result == {"event_id": "evt-1"}
    assert captured == {
        "message": "风险事件",
        "config": web_config,
        "progress_callback": None,
    }


@pytest.mark.anyio
async def test_analysis_service_applies_risk_rules_without_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    captured: dict[str, object] = {}
    applied_rules: list[object] = []
    web_config = {"llm": {"model": "saved-web-model"}}

    async def fake_process_message_detailed(
        message: str,
        config: dict | None = None,
        progress_callback: Callable[[object], None] | None = None,
    ) -> dict[str, str]:
        captured["message"] = message
        captured["config"] = config
        captured["progress_callback"] = progress_callback
        return {"event_id": "evt-rules"}

    async def fake_dispatch_analysis_notifications(*, result: dict[str, str], actor: CurrentUser) -> None:
        return None

    monkeypatch.setattr(
        "backend.app.services.analysis_service.load_web_runtime_config",
        lambda: web_config,
    )
    monkeypatch.setattr(
        "backend.app.services.analysis_service.load_risk_rules",
        lambda: ([{"id": "rule"}], "updated"),
    )
    monkeypatch.setattr(
        "backend.app.services.analysis_service.apply_rules_to_config",
        lambda config, rules: applied_rules.extend(rules) or config.update({"rules": rules}),
    )
    monkeypatch.setattr(
        "backend.app.services.analysis_service.process_message_detailed",
        fake_process_message_detailed,
    )
    monkeypatch.setattr(
        "backend.app.services.analysis_service.dispatch_analysis_notifications",
        fake_dispatch_analysis_notifications,
    )

    # When
    result = await AnalysisService().analyze("风险事件")

    # Then
    assert result == {"event_id": "evt-rules"}
    assert applied_rules == [{"id": "rule"}]
    assert captured == {
        "message": "风险事件",
        "config": {"llm": {"model": "saved-web-model"}, "rules": [{"id": "rule"}]},
        "progress_callback": None,
    }


@pytest.mark.anyio
async def test_analysis_service_passes_web_config_with_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    captured: dict[str, object] = {}
    progress_events: list[object] = []
    progress_callback = progress_events.append
    web_config = {"llm": {"model": "saved-web-model"}}

    async def fake_process_message_detailed(
        message: str,
        config: dict | None = None,
        progress_callback: Callable[[object], None] | None = None,
    ) -> dict[str, str]:
        captured["message"] = message
        captured["config"] = config
        captured["progress_callback"] = progress_callback
        return {"event_id": "evt-2"}

    async def fake_dispatch_analysis_notifications(*, result: dict[str, str], actor: CurrentUser) -> None:
        return None

    monkeypatch.setattr(
        "backend.app.services.analysis_service.load_web_runtime_config",
        lambda: web_config,
    )
    monkeypatch.setattr(
        "backend.app.services.analysis_service.load_risk_rules",
        lambda: ([{"id": "rule"}], "updated"),
    )
    monkeypatch.setattr(
        "backend.app.services.analysis_service.apply_rules_to_config",
        lambda config, rules: config.update({"rules": rules}),
    )
    monkeypatch.setattr(
        "backend.app.services.analysis_service.process_message_detailed",
        fake_process_message_detailed,
    )
    monkeypatch.setattr(
        "backend.app.services.analysis_service.dispatch_analysis_notifications",
        fake_dispatch_analysis_notifications,
    )

    # When
    result = await AnalysisService().analyze(
        "风险事件",
        progress_callback=progress_callback,
        actor=CurrentUser(username="tester", role="admin"),
    )

    # Then
    assert result == {"event_id": "evt-2"}
    assert captured["message"] == "风险事件"
    assert captured["config"] == {"llm": {"model": "saved-web-model"}, "rules": [{"id": "rule"}]}
    assert captured["progress_callback"] is progress_callback


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
    monkeypatch.setattr("backend.app.services.url_safety.socket.getaddrinfo", public_dns_result)
    settings, _ = load_app_settings()
    settings["runtime_config"]["RAGFLOW_ENABLED"] = True
    settings["runtime_config"]["RAGFLOW_BASE_URL"] = "https://saved-ragflow.example"
    settings["runtime_config"]["RAGFLOW_API_KEY"] = "saved-ragflow-key"
    settings["runtime_config"]["RAGFLOW_DATASET_IDS"] = ["saved-a", "saved-b"]
    settings["runtime_config"]["RAGFLOW_TIMEOUT_SECONDS"] = 33.5
    settings["runtime_config"]["RAGFLOW_MAX_CONTEXT_CHARS"] = 1234
    settings["runtime_config"]["RAGFLOW_FAIL_OPEN"] = False
    settings["runtime_config"]["LLM_MODEL"] = "saved-dashboard-model"
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
        async def classify_with_severity(self, text: str) -> tuple[str, float, str, float]:
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

    monkeypatch.setattr(main, "get_llm_for", lambda stage: f"llm:{stage}")
    monkeypatch.setattr(main, "retrieve_financial_knowledge", fake_retrieve_financial_knowledge)
    monkeypatch.setattr(main, "EventClassifier", FakeEventClassifier)
    monkeypatch.setattr(main, "Agent", FakeAgent)
    monkeypatch.setattr(main, "Task", FakeTask)
    monkeypatch.setattr(main, "Crew", FakeCrew)
    monkeypatch.setattr(main, "get_intent_analysis_task", lambda **kwargs: FakeTask(**kwargs))
    monkeypatch.setattr(main, "get_trend_prediction_task", lambda **kwargs: FakeTask(**kwargs))

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
    assert captured["agent_llms"] == ["llm:dashboard", "llm:dashboard"]
    assert result["report"] == "dashboard ok"
