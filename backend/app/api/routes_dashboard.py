from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter

from backend.app.services import store_provider

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


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
    stores = store_provider.get_store_bundle()
    today = datetime.now().date().isoformat()
    since_7d = (datetime.now() - timedelta(days=7)).isoformat(timespec="seconds")
    event_rows = stores.events.list_events(page=1, page_size=10000)["items"]
    review_rows = stores.review_actions.list_recent(limit=10000)
    blacklist_count = (
        len(stores.persons.list_items())
        + len(stores.keywords.list_items())
        + len(stores.event_samples.list_items())
    )

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
        if row.get("trend_report"):
            report_count += 1
        for keyword in row.get("matched_keywords") or []:
            keyword_counts[keyword] = keyword_counts.get(keyword, 0) + 1

    total = len(event_rows)
    return {
        "metrics": {
            "total_events": total,
            "today_events": sum(
                1
                for row in event_rows
                if str(row.get("created_at", "")).startswith(today)
            ),
            "last_7d_events": sum(
                1
                for row in event_rows
                if str(row.get("created_at", "")) >= since_7d
            ),
            "high_risk_events": buckets["high"],
            "pending_review": sum(
                1
                for row in event_rows
                if _risk_bucket(row) == "high"
                and row["event_id"] not in reviewed_event_ids
            ),
            "blacklist_items": blacklist_count,
            "avg_risk_score": round(score_total / scored_count, 4)
            if scored_count
            else None,
            "trend_report_coverage": round(report_count / total, 4) if total else 0,
        },
        "risk_distribution": buckets,
        "event_type_distribution": [
            {"name": key, "value": value}
            for key, value in sorted(
                event_type_counts.items(),
                key=lambda item: item[1],
                reverse=True,
            )
        ],
        "top_keywords": [
            {"name": key, "value": value}
            for key, value in sorted(
                keyword_counts.items(),
                key=lambda item: item[1],
                reverse=True,
            )[:8]
        ],
        "recent_events": event_rows[:8],
        "recent_reviews": review_rows[:8],
    }
