from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from blacklist.milvus_client import MilvusConfig, create_milvus_client
from blacklist.stores.events_store import EventsStore
from blacklist.stores.factory import create_embedding_fn, events_collection_from_config


@dataclass
class MilvusDiagnostics:
    connectivity_ok: bool | None = None
    collection_exists: bool | None = None
    collection_name: str | None = None
    queried_event_id: str | None = None
    row_found: bool | None = None
    row_data: dict[str, Any] | None = None
    error_type: str | None = None
    error_message: str | None = None
    connection_error: str | None = None
    collection_error: str | None = None
    all_rows_count: int | None = None


async def diagnose_milvus_failure(
    store: Any | None = None,
    event_id: str | None = None,
) -> MilvusDiagnostics:
    if not event_id:
        return MilvusDiagnostics(
            queried_event_id=event_id,
            error_type="missing_event_id",
            error_message="No event_id provided for diagnosis",
        )

    store = store or default_events_store()
    collection_name = str(
        getattr(store, "collection_name", getattr(store, "_collection_name", "events"))
    )
    diag = MilvusDiagnostics(
        collection_name=collection_name,
        queried_event_id=event_id,
    )

    try:
        store.ensure_collection_ready()
        diag.collection_exists = True
        diag.connectivity_ok = True
    except Exception as exc:
        diag.connectivity_ok = False
        err_msg = str(exc)
        if "collection not found" in err_msg.lower() or "not exist" in err_msg.lower():
            diag.collection_exists = False
            diag.error_type = "collection_not_found"
        else:
            diag.error_type = "backend_access_failed"
        diag.connection_error = err_msg
        diag.error_message = f"Milvus connectivity / collection check failed: {exc}"
        return diag

    try:
        raw_rows = store.query_event_rows(
            event_id,
            ["event_id", "person_ids", "is_graph_built", "raw_content"],
        )
        if not raw_rows:
            diag.row_found = False
            diag.error_type = "row_not_found"
            diag.all_rows_count = store.count_rows_for_diagnostics()
            diag.error_message = (
                f"Collection {collection_name!r} exists with "
                f"{diag.all_rows_count} total rows, but no row found for "
                f"event_id={event_id!r}"
            )
            return diag

        diag.row_found = True
        first = raw_rows[0]
        diag.row_data = {
            "event_id": first.get("event_id"),
            "person_ids": sorted(first.get("person_ids") or []),
            "is_graph_built": first.get("is_graph_built"),
        }
        diag.error_type = None
        diag.error_message = None
    except Exception as exc:
        err_msg = str(exc)
        if "collection not found" in err_msg.lower() or "not exist" in err_msg.lower():
            diag.error_type = "collection_not_found"
            diag.collection_exists = False
        else:
            diag.error_type = "backend_access_failed"
        diag.collection_error = err_msg
        diag.error_message = (
            f"Milvus query error for event_id={event_id!r}: {err_msg}"
        )
    return diag


def default_events_store() -> EventsStore:
    client = create_milvus_client(
        MilvusConfig(
            uri=os.getenv("MILVUS_URI", "http://localhost:19530"),
            token=os.getenv("MILVUS_TOKEN", ""),
        )
    )
    embedding_fn = create_embedding_fn(
        {
            "model": os.getenv("EMBEDDER_MODEL") or "BAAI/bge-m3",
            "api_key": os.getenv("EMBEDDER_API_KEY")
            or os.getenv("LLM_API_KEY")
            or "",
            "api_base": os.getenv("EMBEDDER_API_BASE")
            or "https://api.openai.com/v1",
        }
    )
    return EventsStore(
        client=client,
        embedding_fn=embedding_fn,
        ttl_days=int(os.getenv("KV_TTL_DAYS") or "90"),
        embedding_dim=int(os.getenv("EMBEDDING_DIM") or "1024"),
        collection_name=events_collection_from_config(),
    )
