from __future__ import annotations

from typing import Final

from pymilvus import DataType

from blacklist.stores.base import FieldSpec

EVENTS_COLLECTION: Final = "stashed_events"
ANALYZED_EVENTS_COLLECTION: Final = "events"
EVENT_PRIMARY_FIELD: Final = "event_id"
EVENT_VECTOR_FIELD: Final = "embedding"
EVENT_OUTPUT_FIELDS: Final = [
    "event_id",
    "person_ids",
    "raw_content",
    "content_hash",
    "created_at",
    "updated_at",
    "expire_at",
    "is_graph_built",
    "status",
    "title",
    "source",
    "event_type",
    "summary",
    "risk_level",
    "risk_score",
    "reasoning",
    "blacklist_decision",
    "matched_persons",
    "matched_keywords",
    "event_similarity",
    "dimension_scores",
    "trend_report",
]


def event_fields(embedding_dim: int) -> list[FieldSpec]:
    return [
        FieldSpec("event_id", DataType.VARCHAR, is_primary=True, max_length=128),
        FieldSpec("content_hash", DataType.VARCHAR, max_length=128),
        FieldSpec("raw_content", DataType.VARCHAR, max_length=8192),
        FieldSpec("title", DataType.VARCHAR, max_length=1024),
        FieldSpec("source", DataType.VARCHAR, max_length=64),
        FieldSpec("embedding", DataType.FLOAT_VECTOR, dim=embedding_dim),
        FieldSpec(
            "person_ids",
            DataType.ARRAY,
            max_length=128,
            max_capacity=256,
            element_type=DataType.VARCHAR,
        ),
        FieldSpec("status", DataType.VARCHAR, max_length=64),
        FieldSpec("blacklist_decision", DataType.VARCHAR, max_length=64),
        FieldSpec("matched_persons", DataType.VARCHAR, max_length=4096),
        FieldSpec("matched_keywords", DataType.VARCHAR, max_length=4096),
        FieldSpec("event_similarity", DataType.VARCHAR, max_length=4096),
        FieldSpec("risk_level", DataType.VARCHAR, max_length=64),
        FieldSpec("risk_score", DataType.DOUBLE),
        FieldSpec("event_type", DataType.VARCHAR, max_length=256),
        FieldSpec("summary", DataType.VARCHAR, max_length=2048),
        FieldSpec("reasoning", DataType.VARCHAR, max_length=4096),
        FieldSpec("dimension_scores", DataType.VARCHAR, max_length=4096),
        FieldSpec("trend_report", DataType.VARCHAR, max_length=16384),
        FieldSpec("is_graph_built", DataType.BOOL),
        FieldSpec("created_at", DataType.VARCHAR, max_length=64),
        FieldSpec("updated_at", DataType.VARCHAR, max_length=64),
        FieldSpec("expire_at", DataType.VARCHAR, max_length=64),
    ]
