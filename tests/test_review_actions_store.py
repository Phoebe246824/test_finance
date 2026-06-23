from __future__ import annotations

import logging

import pytest

from blacklist.stores.review_actions_store import ReviewActionsStore
from tests.fakes.fake_milvus import FakeMilvusClient


def test_list_recent_warns_when_scan_reaches_query_cap(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = FakeMilvusClient()
    store = ReviewActionsStore(client=client, embedding_dim=3)
    client.rows["review_actions"] = {
        f"A{index:05d}": {
            "action_id": f"A{index:05d}",
            "event_id": "E001",
            "action_type": "approve",
            "comment": "",
            "created_at": "2026-06-23T09:00:00",
        }
        for index in range(10_000)
    }

    with caplog.at_level(logging.WARNING):
        rows = store.list_recent(limit=5)

    assert len(rows) == 5
    assert "Milvus review actions list reached query cap" in caplog.text
