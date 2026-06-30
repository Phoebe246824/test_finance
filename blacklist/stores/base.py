from __future__ import annotations

import inspect
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, TypeVar

from pymilvus import DataType, MilvusClient
from pymilvus.exceptions import MilvusException

EmbeddingFn = Callable[[str], list[float] | Awaitable[list[float]]]
INTERNAL_VECTOR_FIELD: Final = "_storage_vector"
INTERNAL_VECTOR_DIM: Final = 2
INTERNAL_VECTOR_VALUE: Final = (0.0, 0.0)
T = TypeVar("T")


@dataclass(frozen=True)
class FieldSpec:
    name: str
    dtype: DataType
    is_primary: bool = False
    max_length: int | None = None
    max_capacity: int | None = None
    element_type: DataType | None = None
    dim: int | None = None
    default_value: Any | None = None


class MilvusBaseStore:
    collection_name: str
    primary_field: str
    vector_field: str = ""

    def __init__(self, client: MilvusClient | Any, *, embedding_dim: int = 1024) -> None:
        self._client = client
        self._embedding_dim = embedding_dim
        self._collection_ready = False

    def fields(self) -> list[FieldSpec]:
        raise NotImplementedError

    def ensure_collection(self) -> None:
        if self._collection_ready:
            return
        if self._client.has_collection(self.collection_name):
            self._collection_ready = True
            return

        schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
        for field in self._schema_fields():
            kwargs: dict[str, Any] = {
                "field_name": field.name,
                "datatype": field.dtype,
                "is_primary": field.is_primary,
            }
            if field.max_length is not None:
                kwargs["max_length"] = field.max_length
            if field.max_capacity is not None:
                kwargs["max_capacity"] = field.max_capacity
            if field.element_type is not None:
                kwargs["element_type"] = field.element_type
            if field.dim is not None:
                kwargs["dim"] = field.dim
            if field.default_value is not None:
                kwargs["default_value"] = field.default_value
            schema.add_field(**kwargs)

        index_params = None
        index_field = self._index_vector_field()
        if index_field:
            index_params = MilvusClient.prepare_index_params()
            index_params.add_index(
                field_name=index_field,
                index_type="AUTOINDEX",
                metric_type="COSINE",
            )

        self._client.create_collection(
            collection_name=self.collection_name,
            schema=schema,
            index_params=index_params,
        )
        load_collection = getattr(self._client, "load_collection", None)
        if load_collection is not None:
            load_collection(collection_name=self.collection_name)
        self._collection_ready = True

    def upsert_rows(self, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0

        def operation() -> dict[str, Any]:
            result = self._client.upsert(
                collection_name=self.collection_name,
                data=self._storage_rows(rows),
            )
            self.flush()
            return result

        result = self._with_collection_retry(operation)
        return int(result.get("upsert_count", len(rows)))

    def query_rows(
        self,
        filter_expr: str,
        output_fields: list[str],
        *,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        if not filter_expr.strip():
            raise ValueError("Milvus query filter must be non-empty")
        return self._with_collection_retry(
            lambda: self._client.query(
                collection_name=self.collection_name,
                filter=filter_expr,
                output_fields=output_fields,
                limit=limit,
            )
        )

    def delete_rows(self, filter_expr: str) -> int:
        if not filter_expr.strip():
            raise ValueError("Milvus delete filter must be non-empty")

        def operation() -> dict[str, Any]:
            result = self._client.delete(
                collection_name=self.collection_name,
                filter=filter_expr,
            )
            self.flush()
            return result

        result = self._with_collection_retry(operation)
        return int(result.get("delete_count", 0))

    def flush(self) -> None:
        flush = getattr(self._client, "flush", None)
        if flush is not None:
            flush(collection_name=self.collection_name)

    def collection_operation(self, operation: Callable[[], T]) -> T:
        return self._with_collection_retry(operation)

    def _with_collection_retry(self, operation: Callable[[], T]) -> T:
        self.ensure_collection()
        try:
            return operation()
        except MilvusException as exc:
            if not self._is_collection_not_found(exc):
                raise
            self._collection_ready = False
            self.ensure_collection()
            return operation()

    @staticmethod
    def _is_collection_not_found(exc: MilvusException) -> bool:
        message = str(exc).lower()
        return "collection not found" in message or "collection not exist" in message

    def _schema_fields(self) -> list[FieldSpec]:
        fields = self.fields()
        if self.vector_field:
            return fields
        return [
            *fields,
            FieldSpec(
                INTERNAL_VECTOR_FIELD,
                DataType.FLOAT_VECTOR,
                dim=INTERNAL_VECTOR_DIM,
            ),
        ]

    def _index_vector_field(self) -> str:
        return self.vector_field or INTERNAL_VECTOR_FIELD

    def _storage_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = [self._clamp_row(row) for row in rows]
        if self.vector_field:
            return rows
        return [
            {**row, INTERNAL_VECTOR_FIELD: list(INTERNAL_VECTOR_VALUE)}
            for row in rows
        ]

    def _clamp_row(self, row: dict[str, Any]) -> dict[str, Any]:
        limits = {
            field.name: field.max_length
            for field in self.fields()
            if field.max_length is not None
        }
        clamped = dict(row)
        for field_name, max_length in limits.items():
            value = clamped.get(field_name)
            if isinstance(value, str) and len(value) > max_length:
                clamped[field_name] = value[: max_length - 3] + "..."
        return clamped

    @staticmethod
    async def resolve_embedding(embedding_fn: EmbeddingFn, text: str) -> list[float]:
        embedding = embedding_fn(text)
        if inspect.isawaitable(embedding):
            embedding = await embedding
        return [float(value) for value in embedding]

    @staticmethod
    def now_iso() -> str:
        return datetime.now().isoformat(timespec="seconds")

    @staticmethod
    def quote(value: str) -> str:
        return json.dumps(value)

    @staticmethod
    def id_filter(field_name: str, values: list[str]) -> str:
        quoted = ", ".join(json.dumps(value) for value in values)
        return f"{field_name} in [{quoted}]"
