from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from backend.app.db.session import get_connection


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _row_to_dict(row) -> dict:
    item = dict(row)
    for field in (
        "matched_persons_json",
        "matched_keywords_json",
        "event_similarity_json",
        "dimension_scores_json",
        "trend_report_json",
    ):
        value = item.get(field)
        item[field.removesuffix("_json")] = json.loads(value) if value else None
    return item


def _plain_value(value: Any) -> Any:
    return getattr(value, "value", value)


class EventRepository:
    def upsert_from_analysis(self, result: dict[str, Any]) -> None:
        now = _now()
        blacklist = result.get("blacklist") or {}
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO financial_events (
                    event_id, title, raw_content, event_type, summary, status,
                    risk_level, risk_score, reasoning, blacklist_decision,
                    matched_persons_json, matched_keywords_json, event_similarity_json,
                    dimension_scores_json, trend_report_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    title=excluded.title,
                    raw_content=excluded.raw_content,
                    event_type=excluded.event_type,
                    summary=excluded.summary,
                    status=excluded.status,
                    risk_level=excluded.risk_level,
                    risk_score=excluded.risk_score,
                    reasoning=excluded.reasoning,
                    blacklist_decision=excluded.blacklist_decision,
                    matched_persons_json=excluded.matched_persons_json,
                    matched_keywords_json=excluded.matched_keywords_json,
                    event_similarity_json=excluded.event_similarity_json,
                    dimension_scores_json=excluded.dimension_scores_json,
                    trend_report_json=excluded.trend_report_json,
                    updated_at=excluded.updated_at
                """,
                (
                    result.get("event_id"),
                    result.get("title") or "",
                    result.get("raw_content") or "",
                    result.get("event_type") or "",
                    result.get("summary") or "",
                    result.get("status") or "unknown",
                    str(_plain_value(result.get("risk_level") or "")),
                    result.get("risk_score"),
                    result.get("reasoning") or "",
                    blacklist.get("decision") or "",
                    json.dumps(blacklist.get("matched_persons") or [], ensure_ascii=False),
                    json.dumps(blacklist.get("matched_keywords") or [], ensure_ascii=False),
                    json.dumps(blacklist.get("event_similarity") or {}, ensure_ascii=False),
                    json.dumps(result.get("dimension_scores") or {}, ensure_ascii=False),
                    json.dumps(result.get("trend_report") or {}, ensure_ascii=False),
                    now,
                    now,
                ),
            )

    def list_events(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        risk_level: str | None = None,
        keyword: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict:
        where = []
        params: list[Any] = []
        if risk_level:
            where.append("risk_level = ?")
            params.append(risk_level)
        if keyword:
            where.append("(raw_content LIKE ? OR title LIKE ? OR summary LIKE ?)")
            like = f"%{keyword}%"
            params.extend([like, like, like])
        if date_from:
            where.append("date(created_at) >= date(?)")
            params.append(date_from)
        if date_to:
            where.append("date(created_at) <= date(?)")
            params.append(date_to)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        offset = (page - 1) * page_size
        with get_connection() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) AS count FROM financial_events {where_sql}",
                params,
            ).fetchone()["count"]
            rows = conn.execute(
                f"""
                SELECT * FROM financial_events
                {where_sql}
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?
                """,
                [*params, page_size, offset],
            ).fetchall()
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [_row_to_dict(row) for row in rows],
        }

    def get_event(self, event_id: str) -> dict | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM financial_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        return _row_to_dict(row) if row else None

    def delete_event(self, event_id: str) -> bool:
        with get_connection() as conn:
            result = conn.execute(
                "DELETE FROM financial_events WHERE event_id = ?",
                (event_id,),
            )
        return result.rowcount > 0
