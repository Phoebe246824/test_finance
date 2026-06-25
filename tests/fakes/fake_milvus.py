from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pymilvus.exceptions import ErrorCode, MilvusException


class FakeMilvusClient:
    def __init__(self) -> None:
        self.collections: set[str] = set()
        self.schemas: dict[str, Any] = {}
        self.index_params: dict[str, Any] = {}
        self.rows: dict[str, dict[str, dict[str, Any]]] = {}
        self.create_calls: list[dict[str, Any]] = []
        self.query_calls: list[dict[str, Any]] = []
        self.search_calls: list[dict[str, Any]] = []
        self.deleted_filters: list[dict[str, str]] = []
        self.flushed: list[str] = []

    def has_collection(self, collection_name: str) -> bool:
        return collection_name in self.collections

    def create_collection(self, **kwargs: Any) -> None:
        collection_name = str(kwargs["collection_name"])
        self.collections.add(collection_name)
        self.schemas[collection_name] = kwargs.get("schema")
        self.index_params[collection_name] = kwargs.get("index_params")
        self.rows.setdefault(collection_name, {})
        self.create_calls.append(dict(kwargs))

    def load_collection(self, **kwargs: Any) -> None:
        self.collections.add(str(kwargs["collection_name"]))

    def flush(self, **kwargs: Any) -> None:
        self.flushed.append(str(kwargs["collection_name"]))

    def upsert(self, collection_name: str, data: list[dict[str, Any]]) -> dict[str, int]:
        collection_rows = self.rows.setdefault(collection_name, {})
        primary_field = self._primary_field(collection_name)
        for row in data:
            collection_rows[str(row[primary_field])] = dict(row)
        return {"upsert_count": len(data)}

    def query(
        self,
        collection_name: str,
        filter: str,
        output_fields: list[str],
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        self.query_calls.append(
            {
                "collection_name": collection_name,
                "filter": filter,
                "output_fields": output_fields,
                "limit": limit,
            }
        )
        rows = [
            self._project(row, output_fields)
            for row in self._filter_rows(collection_name, filter)
        ]
        return rows[:limit] if limit is not None else rows

    def search(
        self,
        collection_name: str,
        data: list[list[float]],
        anns_field: str,
        filter: str,
        limit: int,
        output_fields: list[str],
    ) -> list[list[dict[str, Any]]]:
        query_vector = data[0]
        self.search_calls.append(
            {
                "collection_name": collection_name,
                "anns_field": anns_field,
                "filter": filter,
                "limit": limit,
                "output_fields": output_fields,
            }
        )
        rows = self._filter_rows(collection_name, filter)
        ranked = sorted(
            rows,
            key=lambda row: self._dot(query_vector, row.get(anns_field) or []),
            reverse=True,
        )[:limit]
        primary_field = self._primary_field(collection_name)
        return [
            [
                {
                    "id": row[primary_field],
                    "distance": self._dot(query_vector, row.get(anns_field) or []),
                    "entity": self._project(row, output_fields),
                }
                for row in ranked
            ]
        ]

    def delete(self, collection_name: str, filter: str) -> dict[str, int]:
        collection_rows = self.rows.setdefault(collection_name, {})
        primary_field = self._primary_field(collection_name)
        delete_ids = [
            str(row[primary_field])
            for row in self._filter_rows(collection_name, filter)
        ]
        for row_id in delete_ids:
            collection_rows.pop(row_id, None)
        self.deleted_filters.append(
            {"collection_name": collection_name, "filter": filter}
        )
        return {"delete_count": len(delete_ids)}

    def drop_collection(self, collection_name: str) -> None:
        self.collections.discard(collection_name)
        self.rows.pop(collection_name, None)

    def close(self) -> None:
        return None

    def _primary_field(self, collection_name: str) -> str:
        schema = self.schemas.get(collection_name)
        fields = getattr(schema, "fields", []) if schema is not None else []
        for field in fields:
            if getattr(field, "is_primary", False):
                return str(field.name)
        return "event_id"

    def _filter_rows(self, collection_name: str, filter_expr: str) -> list[dict[str, Any]]:
        rows = list(self.rows.setdefault(collection_name, {}).values())
        if not filter_expr or filter_expr in {'event_id != ""', 'action_id != ""'}:
            return rows
        result = rows
        for part in [item.strip() for item in filter_expr.split(" and ")]:
            result = [row for row in result if self._matches(row, part)]
        return result

    def _matches(self, row: dict[str, Any], expr: str) -> bool:
        if " in [" in expr:
            field = expr.split(" in [", 1)[0].strip()
            return str(row.get(field)) in self._list_values(expr)
        if " == true" in expr:
            field = expr.split(" == true", 1)[0].strip()
            return row.get(field) is True
        if " == false" in expr:
            field = expr.split(" == false", 1)[0].strip()
            return row.get(field) is False
        if " == " in expr:
            field, raw_value = expr.split(" == ", 1)
            return str(row.get(field.strip())) == self._literal(raw_value)
        if " != " in expr:
            field, raw_value = expr.split(" != ", 1)
            return str(row.get(field.strip())) != self._literal(raw_value)
        if " > " in expr:
            field, raw_value = expr.split(" > ", 1)
            return str(row.get(field.strip()) or "") > self._literal(raw_value)
        if " <= " in expr:
            field, raw_value = expr.split(" <= ", 1)
            return str(row.get(field.strip()) or "") <= self._literal(raw_value)
        return True

    @staticmethod
    def _project(row: dict[str, Any], output_fields: Iterable[str]) -> dict[str, Any]:
        return {field: row.get(field) for field in output_fields}

    @staticmethod
    def _dot(query_vector: list[float], vector: Any) -> float:
        return sum(
            float(left) * float(right)
            for left, right in zip(query_vector, vector, strict=False)
        )

    @staticmethod
    def _literal(raw_value: str) -> str:
        return raw_value.strip().strip('"').strip("'")

    @staticmethod
    def _list_values(expr: str) -> list[str]:
        inside = expr.split("[", 1)[1].split("]", 1)[0]
        return [
            item.strip().strip('"').strip("'")
            for item in inside.split(",")
            if item.strip()
        ]


class CollectionNotFoundFakeMilvusClient(FakeMilvusClient):
    def upsert(
        self,
        collection_name: str,
        data: list[dict[str, Any]],
    ) -> dict[str, int]:
        if collection_name not in self.collections:
            raise self._collection_not_found(collection_name)
        return super().upsert(collection_name, data)

    def query(
        self,
        collection_name: str,
        filter: str,
        output_fields: list[str],
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        if collection_name not in self.collections:
            raise self._collection_not_found(collection_name)
        return super().query(collection_name, filter, output_fields, limit)

    def delete(self, collection_name: str, filter: str) -> dict[str, int]:
        if collection_name not in self.collections:
            raise self._collection_not_found(collection_name)
        return super().delete(collection_name, filter)

    def search(
        self,
        collection_name: str,
        data: list[list[float]],
        anns_field: str,
        filter: str,
        limit: int,
        output_fields: list[str],
    ) -> list[list[dict[str, Any]]]:
        if collection_name not in self.collections:
            raise self._collection_not_found(collection_name)
        return super().search(
            collection_name,
            data,
            anns_field,
            filter,
            limit,
            output_fields,
        )

    @staticmethod
    def _collection_not_found(collection_name: str) -> MilvusException:
        return MilvusException(
            ErrorCode.COLLECTION_NOT_FOUND,
            f"collection not found[collection={collection_name}]",
        )
