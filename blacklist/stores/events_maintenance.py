from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from blacklist.stores.events_codec import content_hash

QueryRowsFn = Callable[[str, list[str]], list[dict[str, Any]]]
QuoteFn = Callable[[str], str]


def expired_event_ids(
    query_rows: QueryRowsFn,
    quote: QuoteFn,
    *,
    now: datetime,
    graph_built_retention_days: int | None,
) -> list[str]:
    delete_ids = row_event_ids(
        query_rows(
            f"expire_at <= {quote(now.isoformat())}",
            ["event_id"],
        )
    )
    if graph_built_retention_days is None:
        return sorted(set(delete_ids))
    retention_cutoff = now - timedelta(days=graph_built_retention_days)
    delete_ids.extend(
        row_event_ids(
            query_rows(
                " and ".join(
                    [
                        "is_graph_built == true",
                        f"created_at <= {quote(retention_cutoff.isoformat())}",
                    ]
                ),
                ["event_id"],
            )
        )
    )
    return sorted(set(delete_ids))


def duplicate_event_ids(rows: list[dict[str, Any]]) -> list[str]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        raw_content = str(row.get("raw_content") or "")
        row_hash = str(row.get("content_hash") or content_hash(raw_content))
        grouped.setdefault(row_hash, []).append(row)
    delete_ids: list[str] = []
    for duplicate_rows in grouped.values():
        duplicate_rows.sort(
            key=lambda item: (
                str(item.get("created_at") or ""),
                str(item.get("event_id") or ""),
            )
        )
        delete_ids.extend(row_event_ids(duplicate_rows[1:]))
    return delete_ids


def row_event_ids(rows: list[dict[str, Any]]) -> list[str]:
    return [str(row["event_id"]) for row in rows if row.get("event_id")]
