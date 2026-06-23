from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.app.api import routes_system
from backend.app.main import create_app
from backend.app.services import store_provider


class FakeEvents:
    def __init__(self) -> None:
        self.deleted: list[str] = []
        self.rows = {
            "E001": {
                "event_id": "E001",
                "title": "分拆交易",
                "raw_content": "客户 P102 疑似分拆交易",
                "summary": "疑似分拆交易",
                "status": "analyzed",
                "risk_level": "high",
                "risk_score": 0.91,
                "event_type": "反洗钱",
                "matched_persons": ["P102"],
                "matched_keywords": ["分拆交易"],
                "event_similarity": {},
                "dimension_scores": {},
                "trend_report": {},
                "created_at": "2026-06-23T09:00:00",
                "updated_at": "2026-06-23T09:00:00",
            }
        }

    def ensure_collection(self) -> None:
        return None

    def list_events(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        risk_level: str | None = None,
        keyword: str | None = None,
    ) -> dict[str, Any]:
        items = list(self.rows.values())
        if risk_level:
            items = [item for item in items if item["risk_level"] == risk_level]
        if keyword:
            items = [item for item in items if keyword in item["raw_content"]]
        return {
            "total": len(items),
            "page": page,
            "page_size": page_size,
            "items": items,
        }

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        return self.rows.get(event_id)

    def delete_event(self, event_id: str) -> bool:
        if event_id not in self.rows:
            return False
        self.deleted.append(event_id)
        del self.rows[event_id]
        return True


class FakeReviews:
    def __init__(self) -> None:
        self.rows: list[dict[str, str]] = []

    def list_for_event(self, event_id: str) -> list[dict[str, str]]:
        return [row for row in self.rows if row["event_id"] == event_id]

    def create(self, event_id: str, action_type: str, comment: str) -> dict[str, str]:
        row = {
            "action_id": "A001",
            "event_id": event_id,
            "action_type": action_type,
            "comment": comment,
            "created_at": "2026-06-23T09:30:00",
        }
        self.rows.append(row)
        return row

    def list_recent(self, limit: int = 8) -> list[dict[str, str]]:
        return self.rows[:limit]


class FakeBlacklistItemsStore:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, str]] = {}

    def list_items(self) -> list[dict[str, str]]:
        return list(self.items.values())

    async def append_person(
        self,
        value: str,
        summary: str = "",
        description: str = "",
    ) -> int:
        self.items[value] = {
            "value": value,
            "summary": summary,
            "description": description,
        }
        return 1

    async def append_keyword(
        self,
        value: str,
        summary: str = "",
        description: str = "",
    ) -> int:
        self.items[value] = {
            "value": value,
            "summary": summary,
            "description": description,
        }
        return 1

    async def append_event(
        self,
        value: str,
        summary: str,
        description: str = "",
    ) -> int:
        self.items[value] = {
            "value": value,
            "summary": summary,
            "description": description,
        }
        return 1

    async def remove_person(self, value: str) -> bool:
        return self.items.pop(value, None) is not None

    async def remove_keyword(self, value: str) -> bool:
        return self.items.pop(value, None) is not None

    async def remove_event(self, value: str) -> bool:
        return self.items.pop(value, None) is not None


class FakeStoreBundle:
    def __init__(self) -> None:
        self.events = FakeEvents()
        self.review_actions = FakeReviews()
        self.persons = FakeBlacklistItemsStore()
        self.keywords = FakeBlacklistItemsStore()
        self.event_samples = FakeBlacklistItemsStore()


def test_default_api_uses_milvus_store_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = FakeStoreBundle()

    async def fake_neo4j_ready() -> bool:
        return True

    bundle.persons.items["P102"] = {
        "value": "P102",
        "summary": "客户P102",
        "description": "涉诈",
    }
    monkeypatch.setattr(store_provider, "get_store_bundle", lambda: bundle)
    monkeypatch.setattr(routes_system, "_neo4j_ready", fake_neo4j_ready)

    with TestClient(create_app()) as client:
        health = client.get("/api/system/health")
        persons = client.get("/api/blacklist/persons")
        events = client.get("/api/events", params={"risk_level": "high"})
        detail = client.get("/api/events/E001")
        review = client.post(
            "/api/events/E001/review-actions",
            json={"action_type": "approve", "comment": "confirmed"},
        )
        dashboard = client.get("/api/dashboard/overview")

    assert health.status_code == 200
    assert health.json()["api"] is True
    assert "milvus" in health.json()
    assert persons.status_code == 200
    assert persons.json()["items"][0]["value"] == "P102"
    assert events.json()["total"] == 1
    assert detail.json()["review_actions"] == []
    assert review.json()["created"] is True
    assert dashboard.json()["metrics"]["total_events"] == 1
