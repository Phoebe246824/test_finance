from __future__ import annotations

from typing import Any

from pymilvus import DataType

from blacklist.stores.base import FieldSpec, MilvusBaseStore


class ReviewActionsStore(MilvusBaseStore):
    collection_name = "review_actions"
    primary_field = "action_id"

    def fields(self) -> list[FieldSpec]:
        return [
            FieldSpec("action_id", DataType.VARCHAR, is_primary=True, max_length=128),
            FieldSpec("event_id", DataType.VARCHAR, max_length=128),
            FieldSpec("action_type", DataType.VARCHAR, max_length=128),
            FieldSpec("comment", DataType.VARCHAR, max_length=4096),
            FieldSpec("created_at", DataType.VARCHAR, max_length=64),
        ]

    def list_for_event(self, event_id: str) -> list[dict[str, Any]]:
        rows = self.query_rows(
            f"event_id == {self.quote(event_id)}",
            ["action_id", "event_id", "action_type", "comment", "created_at"],
            limit=10000,
        )
        return sorted(
            rows,
            key=lambda item: str(item.get("created_at") or ""),
            reverse=True,
        )
