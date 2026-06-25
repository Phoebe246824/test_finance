from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.services.runtime_state import runtime_state
from tests.settings_demo.conftest import ADMIN_HEADERS


def test_saving_enabled_data_management_only_persists_policy(monkeypatch):
    client = TestClient(create_app(), raise_server_exceptions=False)

    class FakeEvents:
        def __init__(self) -> None:
            self.retention_days: list[int | None] = []

        def cleanup_expired(self, *, graph_built_retention_days: int | None = None) -> int:
            self.retention_days.append(graph_built_retention_days)
            return 3

    class FakeStores:
        def __init__(self) -> None:
            self.events = FakeEvents()

    stores = FakeStores()
    monkeypatch.setattr(
        "backend.app.services.data_management_service.store_provider.get_store_bundle",
        lambda: stores,
    )

    settings = client.get("/api/settings", headers=ADMIN_HEADERS).json()["settings"]
    settings["data_management"]["retentionDays"] = 14

    response = client.put("/api/settings", headers=ADMIN_HEADERS, json=settings)

    assert response.status_code == 200
    assert response.json()["settings"]["data_management"]["retentionDays"] == 14
    assert stores.events.retention_days == []

def test_explicit_data_management_cleanup_runs_event_cleanup(monkeypatch):
    client = TestClient(create_app(), raise_server_exceptions=False)

    class FakeEvents:
        def __init__(self) -> None:
            self.retention_days: list[int | None] = []

        def cleanup_expired(self, *, graph_built_retention_days: int | None = None) -> int:
            self.retention_days.append(graph_built_retention_days)
            return 3

    class FakeStores:
        def __init__(self) -> None:
            self.events = FakeEvents()

    stores = FakeStores()
    monkeypatch.setattr(
        "backend.app.services.data_management_service.store_provider.get_store_bundle",
        lambda: stores,
    )

    settings = client.get("/api/settings", headers=ADMIN_HEADERS).json()["settings"]
    settings["data_management"]["retentionDays"] = 14
    save_response = client.put("/api/settings", headers=ADMIN_HEADERS, json=settings)
    assert save_response.status_code == 200

    response = client.post("/api/settings/data-management/cleanup", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    assert response.json() == {"enabled": True, "deleted": 3, "status": "completed"}
    assert stores.events.retention_days == [14]
    cleanup_logs = [
        row for row in runtime_state.audit_logs if row["action"] == "data_management.cleanup"
    ]
    assert len(cleanup_logs) == 1
    assert cleanup_logs[0]["detail"]["deleted"] == 3

def test_data_management_cleanup_failure_is_reported_without_losing_saved_policy(monkeypatch):
    from pymilvus.exceptions import MilvusException

    client = TestClient(create_app(), raise_server_exceptions=False)

    def unavailable_store():
        raise MilvusException(message="milvus unavailable")

    monkeypatch.setattr(
        "backend.app.services.data_management_service.store_provider.get_store_bundle",
        unavailable_store,
    )

    settings = client.get("/api/settings", headers=ADMIN_HEADERS).json()["settings"]
    settings["data_management"]["retentionDays"] = 21

    save_response = client.put("/api/settings", headers=ADMIN_HEADERS, json=settings)
    assert save_response.status_code == 200

    response = client.post("/api/settings/data-management/cleanup", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    assert response.json() == {"enabled": True, "deleted": 0, "status": "failed"}
    cleanup_logs = [
        row for row in runtime_state.audit_logs if row["action"] == "data_management.cleanup_failed"
    ]
    assert len(cleanup_logs) == 1
    assert cleanup_logs[0]["detail"]["retentionDays"] == 21
