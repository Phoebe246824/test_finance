from __future__ import annotations

import sys
from typing import Any

import pytest

import scripts.cleanup_milvus_duplicates as cleanup_script


class FakeClient:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeEventsStore:
    duplicate_limit: int | None = None
    expired_retention_days: int | None = None
    last_kwargs: dict[str, Any] = {}

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        FakeEventsStore.last_kwargs = dict(kwargs)

    def cleanup_duplicate_content(self, *, limit: int = 10000) -> int:
        FakeEventsStore.duplicate_limit = limit
        return 2

    def cleanup_expired(
        self,
        *,
        graph_built_retention_days: int | None = None,
    ) -> int:
        FakeEventsStore.expired_retention_days = graph_built_retention_days
        return 3


@pytest.fixture(autouse=True)
def reset_fake_store() -> None:
    FakeEventsStore.duplicate_limit = None
    FakeEventsStore.expired_retention_days = None
    FakeEventsStore.last_kwargs = {}


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> FakeClient:
    client = FakeClient()
    monkeypatch.setattr(cleanup_script, "create_milvus_client", lambda config: client)
    monkeypatch.setattr(cleanup_script, "create_embedding_fn", lambda config: lambda text: [0.0])
    monkeypatch.setattr(cleanup_script, "EventsStore", FakeEventsStore)
    return client


def test_cleanup_script_keeps_duplicate_cleanup_as_default(
    fake_client: FakeClient,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["cleanup_milvus_duplicates.py", "--limit", "123"])
    monkeypatch.setenv("MILVUS_STASH_COLLECTION", "risk_events")

    cleanup_script.main()

    assert FakeEventsStore.duplicate_limit == 123
    assert FakeEventsStore.expired_retention_days is None
    assert FakeEventsStore.last_kwargs["collection_name"] == "risk_events"
    assert fake_client.closed is True
    assert "Deleted duplicate Milvus event rows: 2" in capsys.readouterr().out


def test_cleanup_script_can_delete_expired_events(
    fake_client: FakeClient,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cleanup_milvus_duplicates.py",
            "--expired",
            "--graph-built-retention-days",
            "7",
        ],
    )
    monkeypatch.setenv("MILVUS_STASH_COLLECTION", "risk_events")

    cleanup_script.main()

    assert FakeEventsStore.duplicate_limit is None
    assert FakeEventsStore.expired_retention_days == 7
    assert FakeEventsStore.last_kwargs["collection_name"] == "risk_events"
    assert fake_client.closed is True
    assert "Deleted expired Milvus event rows: 3" in capsys.readouterr().out
