from __future__ import annotations

from typing import Any

from blacklist.stores.events_codec import api_event


def person_matches(
    rows: list[dict[str, Any]],
    person_ids: set[str],
    max_per_person: int,
) -> list[dict[str, Any]]:
    if not person_ids:
        return []
    matched: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in sorted(rows, key=lambda item: str(item.get("created_at") or ""), reverse=True):
        row_person_ids = {str(pid).upper() for pid in row.get("person_ids") or []}
        event_id = str(row["event_id"])
        if person_ids.intersection(row_person_ids) and event_id not in seen:
            matched.append(row)
            seen.add(event_id)
        if len(matched) >= max_per_person * len(person_ids):
            break
    return matched


def merge_recall_matches(
    person_rows: list[dict[str, Any]],
    semantic_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for row in person_rows:
        merged[str(row["event_id"])] = {**row, "match_source": "person_match"}
    for row in semantic_rows:
        event_id = str(row["event_id"])
        if event_id in merged:
            merged[event_id]["match_source"] = "both"
            merged[event_id]["semantic_score"] = row.get("semantic_score")
        else:
            merged[event_id] = {**row, "match_source": "semantic_match"}
    return sorted(
        [recall_event(row) for row in merged.values()],
        key=lambda item: (
            source_rank(str(item["match_source"])),
            str(item.get("created_at") or ""),
            float(item.get("semantic_score") or 0.0),
        ),
        reverse=True,
    )


def semantic_hits(
    hits: list[dict[str, Any]],
    eligible_ids: set[str],
    min_score: float,
) -> list[dict[str, Any]]:
    rows = [
        row
        for hit in hits
        if (row := semantic_row(hit, eligible_ids)) is not None
    ]
    return [
        row
        for row in rows
        if float(row.get("semantic_score") or 0.0) >= min_score
    ]


def semantic_row(hit: dict[str, Any], eligible_ids: set[str]) -> dict[str, Any] | None:
    entity = dict(hit.get("entity") or {})
    event_id = str(entity.get("event_id") or hit.get("id"))
    if event_id not in eligible_ids:
        return None
    return {
        **entity,
        "event_id": event_id,
        "semantic_score": float(hit.get("distance") or 0.0),
    }


def recall_event(row: dict[str, Any]) -> dict[str, Any]:
    item = api_event(row)
    item["match_source"] = row["match_source"]
    if "semantic_score" in row:
        item["semantic_score"] = row["semantic_score"]
    return item


def source_rank(source: str) -> int:
    return {"both": 3, "person_match": 2, "semantic_match": 1}.get(source, 0)
