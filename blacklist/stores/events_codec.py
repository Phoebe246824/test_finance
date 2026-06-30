from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Any

from models import NormalizedEvent


def content_hash(raw_content: str) -> str:
    normalized = " ".join(raw_content.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def bounded_json_text(value: Any, max_length: int) -> str:
    text = json_text(value)
    if len(text) <= max_length:
        return text
    if isinstance(value, dict):
        compact = {
            key: _short_value(item)
            for key, item in value.items()
        }
        text = json_text(
            {
                **compact,
                "_truncated": True,
                "_original_length": len(json_text(value)),
            }
        )
        if len(text) <= max_length:
            return text
    return json_text(
        {
            "_truncated": True,
            "_original_length": len(json_text(value)),
            "text": str(value)[: max_length - 128],
        }
    )[:max_length]


def _short_value(value: Any) -> Any:
    if isinstance(value, str):
        return value[:1200]
    if isinstance(value, list):
        return [_short_value(item) for item in value[:20]]
    if isinstance(value, dict):
        return {str(key): _short_value(item) for key, item in list(value.items())[:20]}
    return value


def json_value(value: Any, fallback: Any) -> Any:
    if not value:
        return fallback
    if isinstance(value, list | dict):
        return value
    try:
        return json.loads(str(value))
    except json.JSONDecodeError:
        return fallback


def event_row(
    event: NormalizedEvent,
    *,
    embedding: list[float],
    person_ids: list[str],
    status: str,
    blacklist_decision: str,
    matched_persons: list[str] | None = None,
    matched_keywords: list[str] | None = None,
    event_similarity: dict[str, Any] | None = None,
    ttl_days: int,
) -> dict[str, Any]:
    created_at = event.timestamp
    now = datetime.now().isoformat(timespec="seconds")
    return {
        "event_id": event.event_id,
        "content_hash": content_hash(event.raw_content),
        "raw_content": event.raw_content,
        "title": event.title or event.event_id,
        "source": getattr(event.source, "value", str(event.source)),
        "embedding": embedding,
        "person_ids": sorted({pid.upper() for pid in person_ids if pid}),
        "status": status,
        "blacklist_decision": blacklist_decision,
        "matched_persons": json_text(matched_persons or []),
        "matched_keywords": json_text(matched_keywords or []),
        "event_similarity": json_text(event_similarity or {}),
        "risk_level": getattr(event.risk_level, "value", str(event.risk_level)),
        "risk_score": float(event.risk_score or 0.0),
        "event_type": event.event_type or "",
        "summary": event.summary or "",
        "reasoning": event.reasoning or "",
        "dimension_scores": json_text({}),
        "trend_report": json_text({}),
        "is_graph_built": False,
        "created_at": created_at.isoformat(),
        "updated_at": now,
        "expire_at": (created_at + timedelta(days=ttl_days)).isoformat(),
    }


def empty_event_row(
    event_id: str,
    raw_content: str,
    title: str,
    *,
    embedding_dim: int,
    ttl_days: int,
) -> dict[str, Any]:
    now = datetime.now()
    now_text = now.isoformat(timespec="seconds")
    return {
        "event_id": event_id,
        "content_hash": content_hash(raw_content),
        "raw_content": raw_content,
        "title": title,
        "source": "",
        "embedding": [0.0] * embedding_dim,
        "person_ids": [],
        "status": "pending",
        "blacklist_decision": "",
        "matched_persons": "[]",
        "matched_keywords": "[]",
        "event_similarity": "{}",
        "risk_level": "",
        "risk_score": 0.0,
        "event_type": "",
        "summary": "",
        "reasoning": "",
        "dimension_scores": "{}",
        "trend_report": "{}",
        "is_graph_built": False,
        "created_at": now_text,
        "updated_at": now_text,
        "expire_at": (now + timedelta(days=ttl_days)).isoformat(timespec="seconds"),
    }


def analysis_row(
    result: dict[str, Any],
    *,
    existing: dict[str, Any],
    embedding: list[float],
    embedding_dim: int,
    ttl_days: int,
) -> dict[str, Any]:
    event_id = str(result["event_id"])
    raw_content = str(result.get("raw_content") or existing.get("raw_content") or "")
    title = str(result.get("title") or existing.get("title") or event_id)
    blacklist = result.get("blacklist") or {}
    base = empty_event_row(
        event_id,
        raw_content,
        title,
        embedding_dim=embedding_dim,
        ttl_days=ttl_days,
    )
    risk_level = result.get("risk_level") or ""
    return {
        **base,
        **existing,
        "event_id": event_id,
        "raw_content": raw_content,
        "title": title,
        "content_hash": existing.get("content_hash") or content_hash(raw_content),
        "embedding": existing.get("embedding") or embedding,
        "status": str(result.get("status") or "analyzed"),
        "blacklist_decision": str(blacklist.get("decision") or ""),
        "matched_persons": json_text(blacklist.get("matched_persons") or []),
        "matched_keywords": json_text(blacklist.get("matched_keywords") or []),
        "event_similarity": json_text(blacklist.get("event_similarity") or {}),
        "risk_level": str(getattr(risk_level, "value", risk_level)),
        "risk_score": float(result.get("risk_score") or 0.0),
        "event_type": str(result.get("event_type") or ""),
        "summary": str(result.get("summary") or ""),
        "reasoning": str(result.get("reasoning") or ""),
        "dimension_scores": json_text(result.get("dimension_scores") or {}),
        "trend_report": bounded_json_text(result.get("trend_report") or {}, 16000),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


def api_event(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    person_ids = item.get("person_ids") or []
    if isinstance(person_ids, str):
        item["person_ids"] = [person_ids]
    elif isinstance(person_ids, Iterable):
        item["person_ids"] = list(person_ids)
    else:
        item["person_ids"] = []
    item["matched_persons"] = json_value(item.get("matched_persons"), [])
    item["matched_keywords"] = json_value(item.get("matched_keywords"), [])
    item["event_similarity"] = json_value(item.get("event_similarity"), {})
    item["dimension_scores"] = json_value(item.get("dimension_scores"), {})
    item["trend_report"] = json_value(item.get("trend_report"), {})
    return item
