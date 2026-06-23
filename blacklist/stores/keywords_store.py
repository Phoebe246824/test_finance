from __future__ import annotations

import hashlib
from typing import Any

from pymilvus import DataType

from blacklist.stores.base import FieldSpec, MilvusBaseStore


class KeywordsStore(MilvusBaseStore):
    collection_name = "blacklist_keywords"
    primary_field = "keyword_id"

    def fields(self) -> list[FieldSpec]:
        return [
            FieldSpec("keyword_id", DataType.VARCHAR, is_primary=True, max_length=128),
            FieldSpec("keyword", DataType.VARCHAR, max_length=512),
            FieldSpec("summary", DataType.VARCHAR, max_length=1024),
            FieldSpec("description", DataType.VARCHAR, max_length=4096),
            FieldSpec("hit_count", DataType.INT64),
            FieldSpec("enabled", DataType.BOOL),
            FieldSpec("created_at", DataType.VARCHAR, max_length=64),
            FieldSpec("updated_at", DataType.VARCHAR, max_length=64),
        ]

    async def query_keywords(self) -> list[str]:
        rows = self.query_rows(
            'keyword_id != "" and enabled == true',
            ["keyword", "updated_at"],
            limit=10000,
        )
        rows.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        return [str(row["keyword"]) for row in rows]

    async def append_keyword(
        self,
        keyword: str,
        summary: str = "",
        description: str = "",
    ) -> int:
        keyword_id = self.keyword_id(keyword)
        now = self.now_iso()
        existing = self._find_keyword_row(keyword_id)
        row = {
            "keyword_id": keyword_id,
            "keyword": keyword,
            "summary": summary,
            "description": description,
            "hit_count": int(existing.get("hit_count") or 0) + 1 if existing else 1,
            "enabled": True,
            "created_at": str(existing.get("created_at") or now) if existing else now,
            "updated_at": now,
        }
        return self.upsert_rows([row])

    async def remove_keyword(self, keyword: str) -> bool:
        row = self._find_keyword_row(self.keyword_id(keyword))
        if not row:
            return False
        row.update({"enabled": False, "updated_at": self.now_iso()})
        return self.upsert_rows([row]) > 0

    async def get_keyword_stats(self) -> dict[str, float]:
        rows = self.query_rows(
            'keyword_id != "" and enabled == true',
            ["keyword", "hit_count"],
            limit=10000,
        )
        return {
            str(row["keyword"]): float(row.get("hit_count") or 1.0)
            for row in rows
        }

    def list_items(self) -> list[dict[str, Any]]:
        rows = self.query_rows(
            'keyword_id != "" and enabled == true',
            [
                "keyword_id",
                "keyword",
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
            {**row, "value": row["keyword"]}
            for row in sorted(
                rows,
                key=lambda item: str(item.get("updated_at") or ""),
                reverse=True,
            )
        ]

    def _find_keyword_row(self, keyword_id: str) -> dict[str, Any]:
        rows = self.query_rows(
            f"keyword_id == {self.quote(keyword_id)}",
            [
                "keyword_id",
                "keyword",
                "summary",
                "description",
                "hit_count",
                "enabled",
                "created_at",
            ],
            limit=1,
        )
        return dict(rows[0]) if rows else {}

    @staticmethod
    def keyword_id(keyword: str) -> str:
        return hashlib.sha256(keyword.encode("utf-8")).hexdigest()

