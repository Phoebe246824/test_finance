from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter

from backend.app.db.session import get_connection

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _risk_bucket(row: dict) -> str:
    if row.get("status") == "stashed" or row.get("risk_score") is None:
        return "low"
    level = row.get("risk_level")
    if level:
        return str(level)
    score = float(row.get("risk_score") or 0)
    if score >= 0.7:
        return "high"
    if score >= 0.35:
        return "medium"
    return "low"


@router.get("/overview")
async def overview() -> dict:
    today = datetime.now().date().isoformat()
    since_7d = (datetime.now() - timedelta(days=7)).isoformat(timespec="seconds")

    with get_connection() as conn:
        event_rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT * FROM financial_events
                ORDER BY updated_at DESC
                """
            ).fetchall()
        ]
        review_rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT * FROM review_actions
                ORDER BY created_at DESC
                """
            ).fetchall()
        ]
        blacklist_count = conn.execute(
            "SELECT COUNT(*) AS count FROM blacklist_items WHERE enabled = 1"
        ).fetchone()["count"]

    buckets = {"high": 0, "medium": 0, "low": 0}
    event_type_counts: dict[str, int] = {}
    keyword_counts: dict[str, int] = {}
    score_total = 0.0
    scored_count = 0
    report_count = 0

    reviewed_event_ids = {row["event_id"] for row in review_rows}
    for row in event_rows:
        bucket = _risk_bucket(row)
        buckets[bucket] = buckets.get(bucket, 0) + 1
        event_type = row.get("event_type") or "未知"
        event_type_counts[event_type] = event_type_counts.get(event_type, 0) + 1
        if row.get("risk_score") is not None:
            score_total += float(row["risk_score"])
            scored_count += 1
        trend_report = _loads(row.get("trend_report_json"), {})
        if trend_report:
            report_count += 1
        for keyword in _loads(row.get("matched_keywords_json"), []):
            keyword_counts[keyword] = keyword_counts.get(keyword, 0) + 1

    total = len(event_rows)
    today_count = sum(1 for row in event_rows if str(row.get("created_at", "")).startswith(today))
    last_7d_count = sum(1 for row in event_rows if str(row.get("created_at", "")) >= since_7d)
    pending_review = sum(
        1
        for row in event_rows
        if _risk_bucket(row) == "high" and row["event_id"] not in reviewed_event_ids
    )

    return {
        "metrics": {
            "total_events": total,
            "today_events": today_count,
            "last_7d_events": last_7d_count,
            "high_risk_events": buckets["high"],
            "pending_review": pending_review,
            "blacklist_items": blacklist_count,
            "avg_risk_score": round(score_total / scored_count, 4) if scored_count else None,
            "trend_report_coverage": round(report_count / total, 4) if total else 0,
        },
        "risk_distribution": buckets,
        "event_type_distribution": [
            {"name": key, "value": value}
            for key, value in sorted(
                event_type_counts.items(), key=lambda item: item[1], reverse=True
            )
        ],
        "top_keywords": [
            {"name": key, "value": value}
            for key, value in sorted(
                keyword_counts.items(), key=lambda item: item[1], reverse=True
            )[:8]
        ],
        "recent_events": [
            {
                "event_id": row["event_id"],
                "title": row.get("title") or row["event_id"],
                "summary": row.get("summary") or row.get("raw_content", "")[:120],
                "status": row.get("status"),
                "risk_level": row.get("risk_level"),
                "risk_score": row.get("risk_score"),
                "event_type": row.get("event_type"),
                "updated_at": row.get("updated_at"),
            }
            for row in event_rows[:8]
        ],
        "recent_reviews": review_rows[:8],
    }
