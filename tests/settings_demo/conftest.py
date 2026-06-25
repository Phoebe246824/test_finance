from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest

from backend.app.services.runtime_state import runtime_state

ADMIN_HEADERS = {"Authorization": "Bearer sentinel-admin-token"}


class AsyncClientFactory:
    def __init__(self, transport: httpx.MockTransport) -> None:
        self.transport = transport
        self.client_class = httpx.AsyncClient

    def __call__(self, *, timeout: float, **kwargs) -> httpx.AsyncClient:
        kwargs.pop("transport", None)
        return self.client_class(transport=self.transport, timeout=timeout, **kwargs)


@pytest.fixture(autouse=True)
def isolated_settings_file(tmp_path, monkeypatch) -> Iterator[None]:
    monkeypatch.setenv("SENTINEL_SETTINGS_FILE", str(tmp_path / "app_settings.json"))
    reset_runtime_state()
    yield
    reset_runtime_state()


def reset_runtime_state() -> None:
    runtime_state.settings = None
    runtime_state.settings_updated_at = ""
    runtime_state.audit_logs.clear()
    runtime_state._next_audit_id = 1
    runtime_state.tasks.clear()
    runtime_state._subscribers.clear()
    runtime_state._task_finished_at.clear()


def public_dns_result(host, port, *args, **kwargs):
    return [
        (
            2,
            1,
            6,
            "",
            ("93.184.216.34", port or 443),
        )
    ]
