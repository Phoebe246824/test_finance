from __future__ import annotations

from collections.abc import Callable

import pytest

from backend.app.core.security import CurrentUser
from backend.app.services.analysis_service import AnalysisService


@pytest.mark.anyio
async def test_analysis_service_passes_web_config_without_progress(
    monkeypatch,
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

    async def fake_dispatch_analysis_notifications(
        *,
        result: dict[str, str],
        actor: CurrentUser,
    ) -> None:
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
    monkeypatch,
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

    async def fake_dispatch_analysis_notifications(
        *,
        result: dict[str, str],
        actor: CurrentUser,
    ) -> None:
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
        lambda config, rules: (
            applied_rules.extend(rules) or config.update({"rules": rules})
        ),
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
    monkeypatch,
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

    async def fake_dispatch_analysis_notifications(
        *,
        result: dict[str, str],
        actor: CurrentUser,
    ) -> None:
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
    assert captured["config"] == {
        "llm": {"model": "saved-web-model"},
        "rules": [{"id": "rule"}],
    }
    assert captured["progress_callback"] is progress_callback
