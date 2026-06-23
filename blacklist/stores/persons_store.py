from __future__ import annotations

from typing import Any

from pymilvus import DataType

from blacklist.stores.base import FieldSpec, MilvusBaseStore


class PersonsStore(MilvusBaseStore):
    collection_name = "blacklist_persons"
    primary_field = "person_id"

    def fields(self) -> list[FieldSpec]:
        return [
            FieldSpec("person_id", DataType.VARCHAR, is_primary=True, max_length=128),
            FieldSpec("summary", DataType.VARCHAR, max_length=1024),
            FieldSpec("description", DataType.VARCHAR, max_length=4096),
            FieldSpec("hit_count", DataType.INT64),
            FieldSpec("enabled", DataType.BOOL),
            FieldSpec("created_at", DataType.VARCHAR, max_length=64),
            FieldSpec("updated_at", DataType.VARCHAR, max_length=64),
        ]

    async def query_person(self, id_number: str) -> float | None:
        rows = self.query_rows(
            f"person_id == {self.quote(id_number.upper())} and enabled == true",
            ["person_id", "hit_count"],
            limit=1,
        )
        return 1.0 if rows else None

    async def append_person(
        self,
        id_number: str,
        summary: str = "",
        description: str = "",
    ) -> int:
        person_id = id_number.upper()
        now = self.now_iso()
        existing = self._find_person_row(person_id)
        row = {
            "person_id": person_id,
            "summary": summary,
            "description": description,
            "hit_count": int(existing.get("hit_count") or 0) + 1 if existing else 1,
            "enabled": True,
            "created_at": str(existing.get("created_at") or now) if existing else now,
            "updated_at": now,
        }
        return self.upsert_rows([row])

    async def remove_person(self, id_number: str) -> bool:
        row = self._find_person_row(id_number.upper())
        if not row:
            return False
        row.update({"enabled": False, "updated_at": self.now_iso()})
        return self.upsert_rows([row]) > 0

    async def get_person_stats(self) -> dict[str, float]:
        rows = self.query_rows(
            'person_id != "" and enabled == true',
            ["person_id", "hit_count"],
            limit=10000,
        )
        return {
            str(row["person_id"]): float(row.get("hit_count") or 1.0)
            for row in rows
        }

    def list_items(self) -> list[dict[str, Any]]:
        rows = self.query_rows(
            'person_id != "" and enabled == true',
            [
                "person_id",
                "summary",
                "description",
                "hit_count",
                "enabled",
                "created_at",
                "updated_at",
            ],
            limit=10000,
        )
        return [
            {**row, "value": row["person_id"]}
            for row in sorted(
                rows,
                key=lambda item: str(item.get("updated_at") or ""),
                reverse=True,
            )
        ]

    def _find_person_row(self, person_id: str) -> dict[str, Any]:
        rows = self.query_rows(
            f"person_id == {self.quote(person_id)}",
            ["person_id", "summary", "description", "hit_count", "enabled", "created_at"],
            limit=1,
        )
        return dict(rows[0]) if rows else {}

