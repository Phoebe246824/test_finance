from __future__ import annotations

from typing import Any

import pytest

from backend.app.services.settings_service import load_app_settings, save_app_settings
from tests.settings_demo.conftest import reset_runtime_state


def test_web_runtime_config_reads_saved_neo4j_database() -> None:
    # Given
    settings, _ = load_app_settings()
    settings["runtime_config"]["NEO4J_DATABASE"] = "sentinel_demo"
    save_app_settings(settings)
    reset_runtime_state()

    # When
    from backend.app.services.web_runtime_config import load_web_runtime_config

    config = load_web_runtime_config()

    # Then
    assert config["neo4j"]["database"] == "sentinel_demo"


async def _empty_records() -> Any:
    if False:
        yield None


class _FakeSession:
    def __init__(self, calls: list[dict[str, Any]]) -> None:
        self.calls = calls

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None

    async def run(self, query: str, **kwargs: Any) -> Any:
        self.calls.append({"query": query, "params": kwargs})
        return _empty_records()


class _FakeDriver:
    def __init__(self) -> None:
        self.databases: list[str | None] = []
        self.calls: list[dict[str, Any]] = []

    def session(self, *, database: str | None = None) -> _FakeSession:
        self.databases.append(database)
        return _FakeSession(self.calls)

    async def close(self) -> None:
        return None


@pytest.mark.anyio
async def test_neo4j_graph_service_uses_configured_database(monkeypatch) -> None:
    # Given
    settings, _ = load_app_settings()
    settings["runtime_config"]["NEO4J_DATABASE"] = "sentinel_demo"
    save_app_settings(settings)
    reset_runtime_state()
    fake_driver = _FakeDriver()

    monkeypatch.setattr(
        "backend.app.services.neo4j_graph_service.AsyncGraphDatabase.driver",
        lambda *args, **kwargs: fake_driver,
    )

    # When
    from backend.app.services.neo4j_graph_service import Neo4jGraphService

    service = Neo4jGraphService()
    graph = await service.graph_by_terms(["P102"])

    # Then
    assert service._database == "sentinel_demo"
    assert graph == {"nodes": [], "edges": []}
    assert fake_driver.databases == ["sentinel_demo", "sentinel_demo"]
