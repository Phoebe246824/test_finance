from __future__ import annotations

import json
from datetime import date, datetime, timedelta
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


def _row_date(row: dict, field: str = "created_at") -> date | None:
    value = str(row.get(field) or "")
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None


def _has_blacklist_hit(row: dict) -> bool:
    persons = _loads(row.get("matched_persons_json"), [])
    keywords = _loads(row.get("matched_keywords_json"), [])
    similarity = _loads(row.get("event_similarity_json"), {})
    decision = str(row.get("blacklist_decision") or "").upper()
    return bool(persons or keywords or similarity.get("hit") or decision in {"BLOCK", "REVIEW", "HIT"})


def _delta(current: int | float, previous: int | float) -> dict:
    return {
        "value": round(current - previous, 4),
        "direction": "up" if current > previous else "down" if current < previous else "flat",
    }


@router.get("/overview")
async def overview() -> dict:
    today_date = datetime.now().date()
    yesterday_date = today_date - timedelta(days=1)
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
                ORDER BY created_at ASC, id ASC
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
    blacklist_hit_count = 0

    reviewed_event_ids = {row["event_id"] for row in review_rows}
    high_risk_event_ids: set[str] = set()
    for row in event_rows:
        bucket = _risk_bucket(row)
        buckets[bucket] = buckets.get(bucket, 0) + 1
        if bucket == "high":
            high_risk_event_ids.add(row["event_id"])
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
        if _has_blacklist_hit(row):
            blacklist_hit_count += 1

    total = len(event_rows)
    today_rows = [row for row in event_rows if _row_date(row) == today_date]
    yesterday_rows = [row for row in event_rows if _row_date(row) == yesterday_date]
    today_count = len(today_rows)
    last_7d_count = sum(1 for row in event_rows if str(row.get("created_at", "")) >= since_7d)
    pending_review = sum(
        1
        for row in event_rows
        if _risk_bucket(row) == "high" and row["event_id"] not in reviewed_event_ids
    )
    reviewed_high_risk_ids = high_risk_event_ids & reviewed_event_ids
    suggest_freeze_count = sum(1 for row in review_rows if row["action_type"] == "suggest_freeze")
    false_positive_count = sum(1 for row in review_rows if row["action_type"] == "false_positive")
    today_buckets = {"high": 0, "medium": 0, "low": 0}
    yesterday_buckets = {"high": 0, "medium": 0, "low": 0}
    for row in today_rows:
        today_buckets[_risk_bucket(row)] += 1
    for row in yesterday_rows:
        yesterday_buckets[_risk_bucket(row)] += 1

    today_pending_review = sum(
        1
        for row in today_rows
        if _risk_bucket(row) == "high" and row["event_id"] not in reviewed_event_ids
    )
    yesterday_pending_review = sum(
        1
        for row in yesterday_rows
        if _risk_bucket(row) == "high" and row["event_id"] not in reviewed_event_ids
    )
    today_report_coverage = (
        sum(1 for row in today_rows if _loads(row.get("trend_report_json"), {})) / len(today_rows)
        if today_rows
        else 0
    )
    yesterday_report_coverage = (
        sum(1 for row in yesterday_rows if _loads(row.get("trend_report_json"), {})) / len(yesterday_rows)
        if yesterday_rows
        else 0
    )
    today_blacklist_hits = sum(1 for row in today_rows if _has_blacklist_hit(row))
    yesterday_blacklist_hits = sum(1 for row in yesterday_rows if _has_blacklist_hit(row))

    trend_days = [today_date - timedelta(days=offset) for offset in range(6, -1, -1)]
    risk_trend = []
    for day in trend_days:
        day_rows = [row for row in event_rows if _row_date(row) == day]
        day_buckets = {"high": 0, "medium": 0, "low": 0}
        for row in day_rows:
            day_buckets[_risk_bucket(row)] += 1
        risk_trend.append({"date": day.isoformat(), "label": day.strftime("%m-%d"), **day_buckets})

    return {
        "metrics": {
            "total_events": total,
            "today_events": today_count,
            "last_7d_events": last_7d_count,
            "high_risk_events": buckets["high"],
            "pending_review": pending_review,
            "blacklist_items": blacklist_count,
            "review_actions": len(review_rows),
            "reviewed_events": len(reviewed_event_ids),
            "review_coverage": round(len(reviewed_high_risk_ids) / len(high_risk_event_ids), 4)
            if high_risk_event_ids
            else 0,
            "suggest_freeze_count": suggest_freeze_count,
            "false_positive_count": false_positive_count,
            "avg_risk_score": round(score_total / scored_count, 4) if scored_count else None,
            "trend_report_coverage": round(report_count / total, 4) if total else 0,
            "blacklist_hit_events": blacklist_hit_count,
        },
        "metric_deltas": {
            "total_events": _delta(today_count, len(yesterday_rows)),
            "high_risk_events": _delta(today_buckets["high"], yesterday_buckets["high"]),
            "pending_review": _delta(today_pending_review, yesterday_pending_review),
            "trend_report_coverage": _delta(today_report_coverage, yesterday_report_coverage),
            "blacklist_hit_events": _delta(today_blacklist_hits, yesterday_blacklist_hits),
        },
        "risk_distribution": buckets,
        "risk_trend": risk_trend,
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
                "blacklist_decision": row.get("blacklist_decision"),
                "matched_persons": _loads(row.get("matched_persons_json"), []),
                "matched_keywords": _loads(row.get("matched_keywords_json"), []),
                "event_similarity": _loads(row.get("event_similarity_json"), {}),
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
            }
            for row in event_rows[:50]
        ],
        "recent_reviews": review_rows[-8:],
    }
