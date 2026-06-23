# Milvus Storage Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate Sentinel storage onto Milvus for events, review actions, blacklist persons, blacklist keywords, and blacklist event samples while preserving same-person and semantic recall.

**Architecture:** Milvus becomes the only runtime storage backend for the application layer. A shared Milvus client factory feeds focused store classes under `blacklist/stores/`; `events` owns full event persistence and stash recall, while blacklist stores own exact person/keyword checks and semantic event-sample matching. SQLite and Redis runtime paths are removed; RabbitMQ code stays present but is marked deprecated and moved behind optional dependencies.

**Tech Stack:** Python 3.13, Pydantic v2, FastAPI, CrewAI Flow, pymilvus, Graphiti embedder configured by `.env` `EMBEDDER_*`, pytest, uv, Docker Compose.

---

## Source Spec

Implement the design in `docs/superpowers/specs/2026-06-23-milvus-storage-consolidation-design.md`.

Important constraints from the spec:

- Default storage is Milvus, not SQLite.
- Blacklist data moves from Redis/SQLite into Milvus collections.
- Event stash behavior is merged into the full `events` collection.
- Semantic recall stays available through Milvus vector search using embeddings from configured `EMBEDDER_MODEL`, `EMBEDDER_API_KEY`, and `EMBEDDER_API_BASE`.
- RabbitMQ code remains in the repository, but the runtime dependency is deprecated and optional.
- Each intermediate commit must keep `import main; import backend.app.main` working.

## Scope Check

This plan covers one subsystem: storage consolidation. It touches the root flow, Web API persistence, demo scripts, dependency metadata, Compose defaults, and documentation because the spec requires all of them to agree on the new storage shape. It does not redesign Graphiti/Neo4j, risk scoring, taxonomy categories, Vue UI, or LLM routing.

## File Structure

### Create

- `blacklist/milvus_client.py` — parse Milvus config and build a `pymilvus.MilvusClient`.
- `blacklist/stores/__init__.py` — public exports for focused Milvus stores.
- `blacklist/stores/base.py` — shared collection creation, query, upsert, delete, flush, embedding helpers.
- `blacklist/stores/events_store.py` — full event persistence, dedupe, stash protocol, vector recall, event list/detail/dashboard queries.
- `blacklist/stores/review_actions_store.py` — review action CRUD stored in Milvus.
- `blacklist/stores/persons_store.py` — person blacklist CRUD and exact lookup.
- `blacklist/stores/keywords_store.py` — keyword blacklist CRUD and enabled keyword scan.
- `blacklist/stores/event_samples_store.py` — semantic blacklist sample CRUD and vector matching.
- `blacklist/stores/factory.py` — single composition point returning all stores with a shared Milvus client and configured embedder.
- `backend/app/services/store_provider.py` — FastAPI-friendly cached store bundle provider, resettable in tests.
- `tests/fakes/fake_milvus.py` — deterministic fake Milvus client for unit and API tests.
- `tests/test_milvus_store_base.py` — shared client/base schema tests.
- `tests/test_events_store.py` — event persistence and stash recall tests.
- `tests/test_blacklist_milvus_stores.py` — person/keyword/event sample store tests.
- `tests/test_default_milvus_api.py` — Web API uses Milvus stores by default.
- `tests/test_default_milvus_runtime.py` — root runtime uses Milvus stores and configured embedder by default.

### Modify

- `blacklist/filter.py` — accept focused stores instead of `BlacklistStore`; semantic event sample match comes from `EventSamplesStore`.
- `blacklist/__init__.py` — export new stores/factory only.
- `main.py` — remove backend selection, create Milvus stores, persist every event to `events`, keep same-person and semantic recall through `EventsStore`.
- `backend/app/repositories/events.py` — delegate to `EventsStore` and `ReviewActionsStore`.
- `backend/app/api/routes_blacklist.py` — call `PersonsStore`, `KeywordsStore`, and `EventSamplesStore`.
- `backend/app/api/routes_events.py` — call repository/review store, no SQLite connection.
- `backend/app/api/routes_dashboard.py` — aggregate via `EventsStore`, `ReviewActionsStore`, and blacklist store counts.
- `backend/app/api/routes_system.py` — health reports `api`, `milvus`, `neo4j`.
- `backend/app/api/routes_graph.py` — unchanged logic, but `EventRepository` now reads Milvus.
- `backend/app/main.py` — remove `init_db()` startup.
- `backend/app/core/config.py` — remove SQLite database URL setting.
- `scripts/reset_and_seed_blacklist.py` — reset Milvus collections and seed Milvus blacklist stores.
- `scripts/run_blacklist_kv_demo.py` — remove Redis reset, seed Milvus stores, default collection `events`.
- `scripts/blacklist_demo_assertions.py` — inspect `EventsStore`, default collection `events`.
- `scripts/cleanup_milvus_duplicates.py` — use `EventsStore.cleanup_duplicate_content`.
- `consumer.py`, `classifier.py`, `graph_service.py` — mark RabbitMQ entrypoints deprecated and guard optional `pika`.
- `models.py` — update RabbitMQ docstrings to say legacy queue format.
- `docker-compose.yaml` — include only Milvus and Neo4j compose files.
- `compose/milvus.yaml` — start etcd/minio/milvus by default; keep Attu under profile.
- `.env.example` — remove SQLite/Redis/RabbitMQ default variables, set `MILVUS_STASH_COLLECTION=events`.
- `pyproject.toml`, `requirements.txt`, `uv.lock` — remove `redis` and `pika` from default dependencies; add optional `legacy`.
- `README.md`, `docs/architecture.md`, `docs/setup.md`, `docs/env-vars.md`, `docs/commands.md`, `docs/testing.md`, `docs/pitfalls.md`, `docs/competition_plan.md`, `docs/competition_paper_outline.md`, `docs/competition_ppt_outline.md`, `docs/demo_script.md` — make docs match Milvus-default architecture.

### Delete

- `blacklist/store.py`
- `blacklist/sqlite_store.py`
- `blacklist/sqlite_stash.py`
- `blacklist/runtime_storage.py`
- `blacklist/milvus_stash.py`
- `backend/app/db/session.py`
- `backend/app/db/`
- `tests/test_sqlite_blacklist_store.py`
- `tests/test_sqlite_stash_store.py`
- `tests/test_default_sqlite_api.py`
- `tests/test_default_sqlite_runtime.py`
- `tests/test_blacklist_manager.py`

## Collection Contracts

Use these names and defaults everywhere:

```python
EVENTS_COLLECTION = "events"
REVIEW_ACTIONS_COLLECTION = "review_actions"
BLACKLIST_PERSONS_COLLECTION = "blacklist_persons"
BLACKLIST_KEYWORDS_COLLECTION = "blacklist_keywords"
BLACKLIST_EVENT_SAMPLES_COLLECTION = "blacklist_event_samples"
```

The `events` collection must keep compatibility with the current stash protocol:

```python
class EventStashProtocol(Protocol):
    async def stash_event(self, event: NormalizedEvent, id_numbers: list[str]) -> int: ...

    async def fetch_related_events(
        self,
        event: NormalizedEvent,
        id_numbers: list[str],
        top_k_semantic: int = 10,
        max_per_person: int = 20,
    ) -> list[dict]: ...

    async def mark_events_graph_built(self, event_ids: list[str]) -> int: ...
```

`stash_event()` is kept as a compatibility alias for the flow, but it writes to the unified `events` collection with `status="stashed"` rather than to a separate stash collection.

---

### Task 1: Shared Milvus Client, Store Base, and Fake Client

**Files:**
- Create: `blacklist/milvus_client.py`
- Create: `blacklist/stores/base.py`
- Create: `blacklist/stores/__init__.py`
- Create: `tests/fakes/fake_milvus.py`
- Create: `tests/test_milvus_store_base.py`

- [ ] **Step 1: Write fake Milvus client for tests**

Create `tests/fakes/fake_milvus.py`:

```python
from __future__ import annotations

from collections.abc import Iterable
from typing import Any


class FakeMilvusClient:
    def __init__(self) -> None:
        self.collections: set[str] = set()
        self.schemas: dict[str, Any] = {}
        self.index_params: dict[str, Any] = {}
        self.rows: dict[str, dict[str, dict[str, Any]]] = {}
        self.create_calls: list[dict[str, Any]] = []
        self.query_calls: list[dict[str, Any]] = []
        self.search_calls: list[dict[str, Any]] = []
        self.deleted_filters: list[dict[str, str]] = []
        self.flushed: list[str] = []

    def has_collection(self, collection_name: str) -> bool:
        return collection_name in self.collections

    def create_collection(self, **kwargs: Any) -> None:
        collection_name = str(kwargs["collection_name"])
        self.collections.add(collection_name)
        self.schemas[collection_name] = kwargs.get("schema")
        self.index_params[collection_name] = kwargs.get("index_params")
        self.rows.setdefault(collection_name, {})
        self.create_calls.append(dict(kwargs))

    def load_collection(self, **kwargs: Any) -> None:
        self.collections.add(str(kwargs["collection_name"]))

    def flush(self, **kwargs: Any) -> None:
        self.flushed.append(str(kwargs["collection_name"]))

    def upsert(self, collection_name: str, data: list[dict[str, Any]]) -> dict[str, int]:
        collection_rows = self.rows.setdefault(collection_name, {})
        primary_field = self._primary_field(collection_name)
        for row in data:
            collection_rows[str(row[primary_field])] = dict(row)
        return {"upsert_count": len(data)}

    def query(
        self,
        collection_name: str,
        filter: str,
        output_fields: list[str],
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        self.query_calls.append(
            {
                "collection_name": collection_name,
                "filter": filter,
                "output_fields": output_fields,
                "limit": limit,
            }
        )
        rows = [self._project(row, output_fields) for row in self._filter_rows(collection_name, filter)]
        return rows[:limit] if limit is not None else rows

    def search(
        self,
        collection_name: str,
        data: list[list[float]],
        anns_field: str,
        filter: str,
        limit: int,
        output_fields: list[str],
    ) -> list[list[dict[str, Any]]]:
        query_vector = data[0]
        self.search_calls.append(
            {
                "collection_name": collection_name,
                "anns_field": anns_field,
                "filter": filter,
                "limit": limit,
                "output_fields": output_fields,
            }
        )
        rows = self._filter_rows(collection_name, filter)

        def score(row: dict[str, Any]) -> float:
            vector = row.get(anns_field) or []
            return sum(float(a) * float(b) for a, b in zip(query_vector, vector, strict=False))

        ranked = sorted(rows, key=score, reverse=True)[:limit]
        primary_field = self._primary_field(collection_name)
        return [
            [
                {
                    "id": row[primary_field],
                    "distance": score(row),
                    "entity": self._project(row, output_fields),
                }
                for row in ranked
            ]
        ]

    def delete(self, collection_name: str, filter: str) -> dict[str, int]:
        rows = self.rows.setdefault(collection_name, {})
        primary_field = self._primary_field(collection_name)
        delete_ids = [str(row[primary_field]) for row in self._filter_rows(collection_name, filter)]
        for row_id in delete_ids:
            rows.pop(row_id, None)
        self.deleted_filters.append({"collection_name": collection_name, "filter": filter})
        return {"delete_count": len(delete_ids)}

    def drop_collection(self, collection_name: str) -> None:
        self.collections.discard(collection_name)
        self.rows.pop(collection_name, None)

    def close(self) -> None:
        return None

    def _primary_field(self, collection_name: str) -> str:
        schema = self.schemas.get(collection_name)
        fields = getattr(schema, "fields", []) if schema is not None else []
        for field in fields:
            if getattr(field, "is_primary", False):
                return str(field.name)
        return "event_id"

    def _filter_rows(self, collection_name: str, filter_expr: str) -> list[dict[str, Any]]:
        rows = list(self.rows.setdefault(collection_name, {}).values())
        if not filter_expr or filter_expr == 'event_id != ""':
            return rows
        result = rows
        for part in [item.strip() for item in filter_expr.split(" and ")]:
            result = [row for row in result if self._matches(row, part)]
        return result

    def _matches(self, row: dict[str, Any], expr: str) -> bool:
        if " in [" in expr:
            field = expr.split(" in [", 1)[0].strip()
            values = self._list_values(expr)
            return str(row.get(field)) in values
        if " == true" in expr:
            field = expr.split(" == true", 1)[0].strip()
            return row.get(field) is True
        if " == false" in expr:
            field = expr.split(" == false", 1)[0].strip()
            return row.get(field) is False
        if " == " in expr:
            field, raw_value = expr.split(" == ", 1)
            return str(row.get(field.strip())) == self._literal(raw_value)
        if " != " in expr:
            field, raw_value = expr.split(" != ", 1)
            return str(row.get(field.strip())) != self._literal(raw_value)
        if " > " in expr:
            field, raw_value = expr.split(" > ", 1)
            return str(row.get(field.strip()) or "") > self._literal(raw_value)
        if " <= " in expr:
            field, raw_value = expr.split(" <= ", 1)
            return str(row.get(field.strip()) or "") <= self._literal(raw_value)
        return True

    @staticmethod
    def _project(row: dict[str, Any], output_fields: Iterable[str]) -> dict[str, Any]:
        return {field: row.get(field) for field in output_fields}

    @staticmethod
    def _literal(raw_value: str) -> str:
        return raw_value.strip().strip('"').strip("'")

    @staticmethod
    def _list_values(expr: str) -> list[str]:
        inside = expr.split("[", 1)[1].split("]", 1)[0]
        return [item.strip().strip('"').strip("'") for item in inside.split(",") if item.strip()]
```

- [ ] **Step 2: Write failing base/client tests**

Create `tests/test_milvus_store_base.py`:

```python
from __future__ import annotations

import os

from pymilvus import DataType, MilvusClient

from blacklist.milvus_client import MilvusConfig, create_milvus_client, milvus_config_from_app
from blacklist.stores.base import FieldSpec, MilvusBaseStore
from tests.fakes.fake_milvus import FakeMilvusClient


class DummyStore(MilvusBaseStore):
    collection_name = "dummy_collection"
    primary_field = "dummy_id"
    vector_field = ""

    def fields(self) -> list[FieldSpec]:
        return [
            FieldSpec("dummy_id", DataType.VARCHAR, is_primary=True, max_length=64),
            FieldSpec("name", DataType.VARCHAR, max_length=256),
            FieldSpec("enabled", DataType.BOOL),
        ]


def test_milvus_config_from_app_uses_config_values() -> None:
    config = {"milvus": {"uri": "http://milvus:19530", "token": "abc"}}

    result = milvus_config_from_app(config)

    assert result == MilvusConfig(uri="http://milvus:19530", token="abc")


def test_milvus_config_from_app_falls_back_to_env(monkeypatch) -> None:
    monkeypatch.setenv("MILVUS_URI", "http://env-milvus:19530")
    monkeypatch.setenv("MILVUS_TOKEN", "env-token")

    result = milvus_config_from_app({})

    assert result == MilvusConfig(uri="http://env-milvus:19530", token="env-token")


def test_create_milvus_client_passes_uri_and_token(monkeypatch) -> None:
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("blacklist.milvus_client.MilvusClient", FakeClient)

    create_milvus_client(MilvusConfig(uri="http://127.0.0.1:19530", token="secret"))

    assert captured == {"uri": "http://127.0.0.1:19530", "token": "secret"}


def test_create_milvus_client_omits_empty_token(monkeypatch) -> None:
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("blacklist.milvus_client.MilvusClient", FakeClient)

    create_milvus_client(MilvusConfig(uri="http://127.0.0.1:19530", token=""))

    assert captured == {"uri": "http://127.0.0.1:19530"}


def test_base_store_creates_collection_once_with_schema() -> None:
    client = FakeMilvusClient()
    store = DummyStore(client=client)

    store.ensure_collection()
    store.ensure_collection()

    assert len(client.create_calls) == 1
    assert client.create_calls[0]["collection_name"] == "dummy_collection"
    schema = client.create_calls[0]["schema"]
    field_names = [field.name for field in schema.fields]
    assert field_names == ["dummy_id", "name", "enabled"]
```

Run:

```bash
uv run pytest tests/test_milvus_store_base.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'blacklist.milvus_client'`.

- [ ] **Step 3: Implement Milvus client factory**

Create `blacklist/milvus_client.py`:

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from pymilvus import MilvusClient


@dataclass(frozen=True)
class MilvusConfig:
    uri: str = "http://localhost:19530"
    token: str = ""


def milvus_config_from_app(config: dict[str, Any]) -> MilvusConfig:
    milvus_config = config.get("milvus", {}) if isinstance(config, dict) else {}
    return MilvusConfig(
        uri=str(milvus_config.get("uri") or os.getenv("MILVUS_URI") or "http://localhost:19530"),
        token=str(milvus_config.get("token") or os.getenv("MILVUS_TOKEN") or ""),
    )


def create_milvus_client(config: MilvusConfig) -> MilvusClient:
    kwargs: dict[str, str] = {"uri": config.uri}
    if config.token:
        kwargs["token"] = config.token
    return MilvusClient(**kwargs)
```

- [ ] **Step 4: Implement store base**

Create `blacklist/stores/base.py`:

```python
from __future__ import annotations

import inspect
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pymilvus import DataType, MilvusClient

EmbeddingFn = Callable[[str], list[float] | Awaitable[list[float]]]


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
        for field in self.fields():
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
        if self.vector_field:
            index_params = MilvusClient.prepare_index_params()
            index_params.add_index(
                field_name=self.vector_field,
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
        self.ensure_collection()
        result = self._client.upsert(collection_name=self.collection_name, data=rows)
        self.flush()
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
        self.ensure_collection()
        return self._client.query(
            collection_name=self.collection_name,
            filter=filter_expr,
            output_fields=output_fields,
            limit=limit,
        )

    def delete_rows(self, filter_expr: str) -> int:
        if not filter_expr.strip():
            raise ValueError("Milvus delete filter must be non-empty")
        self.ensure_collection()
        result = self._client.delete(collection_name=self.collection_name, filter=filter_expr)
        self.flush()
        return int(result.get("delete_count", 0))

    def flush(self) -> None:
        flush = getattr(self._client, "flush", None)
        if flush is not None:
            flush(collection_name=self.collection_name)

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
```

Create `blacklist/stores/__init__.py`:

```python
from blacklist.stores.base import EmbeddingFn, FieldSpec, MilvusBaseStore

__all__ = ["EmbeddingFn", "FieldSpec", "MilvusBaseStore"]
```

- [ ] **Step 5: Run base/client tests**

Run:

```bash
uv run pytest tests/test_milvus_store_base.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add blacklist/milvus_client.py blacklist/stores/__init__.py blacklist/stores/base.py tests/fakes/fake_milvus.py tests/test_milvus_store_base.py
git commit -m "feat: add shared milvus store foundation"
```

---

### Task 2: Events Store with Full Event Persistence and Stash Recall

**Files:**
- Create: `blacklist/stores/events_store.py`
- Create: `tests/test_events_store.py`
- Modify: `blacklist/stores/__init__.py`

- [ ] **Step 1: Write failing events store tests**

Create `tests/test_events_store.py`:

```python
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from blacklist.stores.events_store import EventsStore
from models import EventSource, NormalizedEvent, RiskLevel
from tests.fakes.fake_milvus import FakeMilvusClient


def fake_embed(text: str) -> list[float]:
    if "分拆转账" in text or "alpha" in text:
        return [1.0, 0.0, 0.0]
    if "工资入账" in text or "beta" in text:
        return [0.0, 1.0, 0.0]
    return [0.0, 0.0, 1.0]


def make_event(event_id: str, text: str, timestamp: datetime) -> NormalizedEvent:
    return NormalizedEvent(
        event_id=event_id,
        source=EventSource.TRANSACTION,
        raw_content=text,
        title=event_id,
        timestamp=timestamp,
        summary=text[:20],
    )


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 6, 23, 9, 0, 0)


@pytest.fixture
def client() -> FakeMilvusClient:
    return FakeMilvusClient()


@pytest.fixture
def store(client: FakeMilvusClient) -> EventsStore:
    return EventsStore(client=client, embedding_fn=fake_embed, embedding_dim=3, ttl_days=30)


@pytest.mark.asyncio
async def test_upsert_event_creates_events_collection_and_full_row(store, client, now) -> None:
    event = make_event("E001", "客户 P102 工资入账后日常消费", now)

    written = await store.upsert_event(
        event,
        person_ids=["p102"],
        status="stashed",
        blacklist_decision="miss",
    )

    assert written == 1
    assert client.create_calls[0]["collection_name"] == "events"
    row = client.rows["events"]["E001"]
    assert row["event_id"] == "E001"
    assert row["content_hash"]
    assert row["raw_content"] == "客户 P102 工资入账后日常消费"
    assert row["title"] == "E001"
    assert row["source"] == "transaction"
    assert row["person_ids"] == ["P102"]
    assert row["status"] == "stashed"
    assert row["blacklist_decision"] == "miss"
    assert row["embedding"] == [0.0, 1.0, 0.0]
    assert row["is_graph_built"] is False
    assert row["created_at"] == now.isoformat()
    assert row["expire_at"] == (now + timedelta(days=30)).isoformat()


@pytest.mark.asyncio
async def test_stash_event_deduplicates_by_content_hash(store, client, now) -> None:
    first = make_event("E001", "客户 P102 工资入账后日常消费", now)
    duplicate = make_event("E002", "客户 P102   工资入账后日常消费", now)

    assert await store.stash_event(first, ["P102"]) == 1
    assert await store.stash_event(duplicate, ["P102"]) == 0
    assert list(client.rows["events"]) == ["E001"]


@pytest.mark.asyncio
async def test_fetch_related_events_merges_same_person_and_semantic_matches(store, now) -> None:
    await store.stash_event(make_event("E001", "alpha P102 分拆转账前置交易", now), ["P102"])
    await store.stash_event(make_event("E002", "alpha P999 相似跨境分拆转账", now), ["P999"])
    await store.stash_event(make_event("E003", "beta P102 工资入账", now), ["P102"])

    results = await store.fetch_related_events(
        make_event("E999", "alpha P102 当前可疑分拆转账", now),
        ["P102"],
        top_k_semantic=2,
        max_per_person=10,
    )

    assert [(item["event_id"], item["match_source"]) for item in results] == [
        ("E001", "both"),
        ("E003", "person_match"),
        ("E002", "semantic_match"),
    ]


@pytest.mark.asyncio
async def test_fetch_related_events_excludes_current_expired_and_built_events(store, now) -> None:
    await store.stash_event(make_event("CURRENT", "alpha P102 current", now), ["P102"])
    await store.stash_event(make_event("EXPIRED", "alpha P102 old", now - timedelta(days=40)), ["P102"])
    await store.stash_event(make_event("BUILT", "alpha P102 built", now), ["P102"])
    await store.mark_events_graph_built(["BUILT"])
    await store.stash_event(make_event("VALID", "alpha P102 valid", now), ["P102"])

    results = await store.fetch_related_events(
        make_event("CURRENT", "alpha P102 trigger", now),
        ["P102"],
        top_k_semantic=10,
        max_per_person=10,
    )

    assert [item["event_id"] for item in results] == ["VALID"]


@pytest.mark.asyncio
async def test_upsert_analysis_result_updates_event_fields(store, now) -> None:
    event = make_event("E001", "alpha P102 分拆转账", now)
    await store.upsert_event(event, person_ids=["P102"], status="pending")

    await store.upsert_analysis_result(
        {
            "event_id": "E001",
            "raw_content": event.raw_content,
            "title": event.title,
            "event_type": "反洗钱",
            "summary": "疑似分拆交易",
            "status": "analyzed",
            "risk_level": RiskLevel.HIGH,
            "risk_score": 0.92,
            "reasoning": "多账户拆分",
            "blacklist": {
                "decision": "PASS",
                "matched_persons": ["P102"],
                "matched_keywords": ["分拆交易"],
                "event_similarity": {"hit": True, "score": 0.88},
            },
            "dimension_scores": {"transaction_behavior": 0.9},
            "trend_report": {"trend": "rising"},
        }
    )

    row = store.get_event("E001")
    assert row is not None
    assert row["event_type"] == "反洗钱"
    assert row["risk_level"] == "high"
    assert row["risk_score"] == pytest.approx(0.92)
    assert row["matched_keywords"] == ["分拆交易"]
    assert row["event_similarity"] == {"hit": True, "score": 0.88}
    assert row["dimension_scores"] == {"transaction_behavior": 0.9}
    assert row["trend_report"] == {"trend": "rising"}


def test_list_events_filters_and_orders_by_updated_at(store, client, now) -> None:
    client.rows["events"] = {
        "E001": {
            "event_id": "E001",
            "raw_content": "低风险工资入账",
            "title": "工资",
            "summary": "工资",
            "status": "stashed",
            "risk_level": "low",
            "risk_score": 0.0,
            "event_type": "正常交易",
            "created_at": "2026-06-22T09:00:00",
            "updated_at": "2026-06-22T09:00:00",
            "matched_keywords": "[]",
            "matched_persons": "[]",
            "event_similarity": "{}",
            "dimension_scores": "{}",
            "trend_report": "{}",
        },
        "E002": {
            "event_id": "E002",
            "raw_content": "疑似分拆交易",
            "title": "分拆",
            "summary": "分拆",
            "status": "analyzed",
            "risk_level": "high",
            "risk_score": 0.91,
            "event_type": "反洗钱",
            "created_at": "2026-06-23T09:00:00",
            "updated_at": "2026-06-23T09:00:00",
            "matched_keywords": "[\"分拆交易\"]",
            "matched_persons": "[\"P102\"]",
            "event_similarity": "{}",
            "dimension_scores": "{}",
            "trend_report": "{}",
        },
    }

    result = store.list_events(page=1, page_size=20, risk_level="high", keyword="分拆")

    assert result["total"] == 1
    assert [item["event_id"] for item in result["items"]] == ["E002"]
```

Run:

```bash
uv run pytest tests/test_events_store.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'blacklist.stores.events_store'`.

- [ ] **Step 2: Implement events store**

Create `blacklist/stores/events_store.py`:

```python
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any

from pymilvus import DataType

from blacklist.stores.base import EmbeddingFn, FieldSpec, MilvusBaseStore
from models import NormalizedEvent


class EventsStore(MilvusBaseStore):
    collection_name = "events"
    primary_field = "event_id"
    vector_field = "embedding"
    output_fields = [
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

    def __init__(
        self,
        client: Any,
        *,
        embedding_fn: EmbeddingFn,
        embedding_dim: int = 1024,
        ttl_days: int = 90,
    ) -> None:
        super().__init__(client, embedding_dim=embedding_dim)
        self._embedding_fn = embedding_fn
        self._ttl_days = ttl_days

    def fields(self) -> list[FieldSpec]:
        return [
            FieldSpec("event_id", DataType.VARCHAR, is_primary=True, max_length=128),
            FieldSpec("content_hash", DataType.VARCHAR, max_length=128),
            FieldSpec("raw_content", DataType.VARCHAR, max_length=8192),
            FieldSpec("title", DataType.VARCHAR, max_length=1024),
            FieldSpec("source", DataType.VARCHAR, max_length=64),
            FieldSpec("embedding", DataType.FLOAT_VECTOR, dim=self._embedding_dim),
            FieldSpec("person_ids", DataType.ARRAY, max_length=128, max_capacity=256, element_type=DataType.VARCHAR),
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
            FieldSpec("trend_report", DataType.VARCHAR, max_length=8192),
            FieldSpec("is_graph_built", DataType.BOOL),
            FieldSpec("created_at", DataType.VARCHAR, max_length=64),
            FieldSpec("updated_at", DataType.VARCHAR, max_length=64),
            FieldSpec("expire_at", DataType.VARCHAR, max_length=64),
        ]

    async def stash_event(self, event: NormalizedEvent, id_numbers: list[str]) -> int:
        return await self.upsert_event(event, person_ids=id_numbers, status="stashed", blacklist_decision="miss")

    async def upsert_event(
        self,
        event: NormalizedEvent,
        *,
        person_ids: list[str],
        status: str,
        blacklist_decision: str = "",
        matched_persons: list[str] | None = None,
        matched_keywords: list[str] | None = None,
        event_similarity: dict[str, Any] | None = None,
    ) -> int:
        content_hash = self._content_hash(event.raw_content)
        existing = self.query_by_content_hash(content_hash)
        if existing and existing[0].get("event_id") != event.event_id:
            return 0

        created_at = event.timestamp
        updated_at = datetime.now()
        row = {
            "event_id": event.event_id,
            "content_hash": content_hash,
            "raw_content": event.raw_content,
            "title": event.title or event.event_id,
            "source": getattr(event.source, "value", str(event.source)),
            "embedding": await self.resolve_embedding(self._embedding_fn, event.raw_content),
            "person_ids": sorted({pid.upper() for pid in person_ids if pid}),
            "status": status,
            "blacklist_decision": blacklist_decision,
            "matched_persons": self._json(matched_persons or []),
            "matched_keywords": self._json(matched_keywords or []),
            "event_similarity": self._json(event_similarity or {}),
            "risk_level": getattr(event.risk_level, "value", str(event.risk_level)),
            "risk_score": float(event.risk_score or 0.0),
            "event_type": event.event_type or "",
            "summary": event.summary or "",
            "reasoning": event.reasoning or "",
            "dimension_scores": self._json({}),
            "trend_report": self._json({}),
            "is_graph_built": False,
            "created_at": created_at.isoformat(),
            "updated_at": updated_at.isoformat(timespec="seconds"),
            "expire_at": (created_at + timedelta(days=self._ttl_days)).isoformat(),
        }
        return self.upsert_rows([row])

    async def upsert_analysis_result(self, result: dict[str, Any]) -> int:
        event_id = str(result["event_id"])
        existing = self.get_raw_event(event_id) or {}
        blacklist = result.get("blacklist") or {}
        now = datetime.now().isoformat(timespec="seconds")
        raw_content = str(result.get("raw_content") or existing.get("raw_content") or "")
        title = str(result.get("title") or existing.get("title") or event_id)
        row = {
            **self._empty_row(event_id, raw_content, title),
            **existing,
            "event_id": event_id,
            "raw_content": raw_content,
            "title": title,
            "content_hash": existing.get("content_hash") or self._content_hash(raw_content),
            "embedding": existing.get("embedding") or await self.resolve_embedding(self._embedding_fn, raw_content),
            "status": str(result.get("status") or "analyzed"),
            "blacklist_decision": str(blacklist.get("decision") or existing.get("blacklist_decision") or ""),
            "matched_persons": self._json(blacklist.get("matched_persons") or []),
            "matched_keywords": self._json(blacklist.get("matched_keywords") or []),
            "event_similarity": self._json(blacklist.get("event_similarity") or {}),
            "risk_level": str(getattr(result.get("risk_level") or "", "value", result.get("risk_level") or "")),
            "risk_score": float(result.get("risk_score") or 0.0),
            "event_type": str(result.get("event_type") or ""),
            "summary": str(result.get("summary") or ""),
            "reasoning": str(result.get("reasoning") or ""),
            "dimension_scores": self._json(result.get("dimension_scores") or {}),
            "trend_report": self._json(result.get("trend_report") or {}),
            "updated_at": now,
        }
        return self.upsert_rows([row])

    def get_raw_event(self, event_id: str) -> dict[str, Any] | None:
        rows = self.query_rows(self.id_filter("event_id", [event_id]), [*self.output_fields, "embedding"], limit=1)
        return dict(rows[0]) if rows else None

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        row = self.get_raw_event(event_id)
        return self._row_to_api(row) if row else None

    def list_events(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        risk_level: str | None = None,
        keyword: str | None = None,
    ) -> dict[str, Any]:
        rows = self.query_rows('event_id != ""', self.output_fields, limit=10000)
        filtered = []
        for row in rows:
            if risk_level and str(row.get("risk_level") or "") != risk_level:
                continue
            haystack = " ".join(str(row.get(field) or "") for field in ("raw_content", "title", "summary"))
            if keyword and keyword not in haystack:
                continue
            filtered.append(row)
        filtered.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        offset = (page - 1) * page_size
        return {
            "total": len(filtered),
            "page": page,
            "page_size": page_size,
            "items": [self._row_to_api(row) for row in filtered[offset : offset + page_size]],
        }

    def delete_event(self, event_id: str) -> bool:
        return self.delete_rows(self.id_filter("event_id", [event_id])) > 0

    def query_by_content_hash(self, content_hash: str) -> list[dict[str, Any]]:
        return self.query_rows(
            f"content_hash == {self.quote(content_hash)}",
            ["event_id", "content_hash", "raw_content"],
            limit=1,
        )

    async def fetch_related_events(
        self,
        event: NormalizedEvent,
        id_numbers: list[str],
        top_k_semantic: int = 10,
        max_per_person: int = 20,
    ) -> list[dict[str, Any]]:
        now = datetime.now().isoformat()
        eligible = self.query_rows(
            " and ".join(
                [
                    "is_graph_built == false",
                    f"expire_at > {self.quote(now)}",
                    f"event_id != {self.quote(event.event_id)}",
                ]
            ),
            [*self.output_fields, "embedding"],
        )
        person_ids = {pid.upper() for pid in id_numbers if pid}
        person_matches = self._person_matches(eligible, person_ids, max_per_person)
        semantic_matches = await self._semantic_matches(event, eligible, top_k_semantic)

        merged: dict[str, dict[str, Any]] = {}
        for row in person_matches:
            merged[str(row["event_id"])] = {**row, "match_source": "person_match"}
        for row in semantic_matches:
            event_id = str(row["event_id"])
            if event_id in merged:
                merged[event_id]["match_source"] = "both"
                merged[event_id]["semantic_score"] = row.get("semantic_score")
            else:
                merged[event_id] = {**row, "match_source": "semantic_match"}
        return sorted(
            [self._row_to_api(row) | {"match_source": row["match_source"], **({"semantic_score": row["semantic_score"]} if "semantic_score" in row else {})} for row in merged.values()],
            key=lambda item: (self._source_rank(item["match_source"]), item.get("created_at", ""), item.get("semantic_score", 0.0)),
            reverse=True,
        )

    async def mark_events_graph_built(self, event_ids: list[str]) -> int:
        unique_ids = sorted({event_id for event_id in event_ids if event_id})
        if not unique_ids:
            return 0
        rows = self.query_rows(self.id_filter("event_id", unique_ids), [*self.output_fields, "embedding"])
        updated = [{**row, "is_graph_built": True, "updated_at": datetime.now().isoformat(timespec="seconds")} for row in rows]
        return self.upsert_rows(updated)

    def cleanup_duplicate_content(self, *, limit: int = 10000) -> int:
        rows = self.query_rows('event_id != ""', ["event_id", "content_hash", "raw_content", "created_at"], limit=limit)
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            content_hash = str(row.get("content_hash") or self._content_hash(str(row.get("raw_content") or "")))
            grouped.setdefault(content_hash, []).append(row)
        delete_ids: list[str] = []
        for duplicate_rows in grouped.values():
            duplicate_rows.sort(key=lambda item: (str(item.get("created_at") or ""), str(item.get("event_id") or "")))
            delete_ids.extend(str(row["event_id"]) for row in duplicate_rows[1:] if row.get("event_id"))
        return self.delete_rows(self.id_filter("event_id", delete_ids)) if delete_ids else 0

    def _person_matches(self, rows: list[dict[str, Any]], person_ids: set[str], max_per_person: int) -> list[dict[str, Any]]:
        if not person_ids:
            return []
        matched: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in sorted(rows, key=lambda item: str(item.get("created_at") or ""), reverse=True):
            row_person_ids = {str(pid).upper() for pid in row.get("person_ids") or []}
            if person_ids.intersection(row_person_ids) and row["event_id"] not in seen:
                matched.append(row)
                seen.add(str(row["event_id"]))
            if len(matched) >= max_per_person * len(person_ids):
                break
        return matched

    async def _semantic_matches(self, event: NormalizedEvent, eligible_rows: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
        if top_k <= 0 or not eligible_rows:
            return []
        eligible_ids = sorted(str(row["event_id"]) for row in eligible_rows)
        self.ensure_collection()
        result = self._client.search(
            collection_name=self.collection_name,
            data=[await self.resolve_embedding(self._embedding_fn, event.raw_content)],
            anns_field=self.vector_field,
            filter=self.id_filter("event_id", eligible_ids),
            limit=top_k,
            output_fields=self.output_fields,
        )
        rows: list[dict[str, Any]] = []
        for hit in result[0] if result else []:
            entity = dict(hit.get("entity") or {})
            event_id = str(entity.get("event_id") or hit.get("id"))
            if event_id in eligible_ids:
                rows.append({**entity, "event_id": event_id, "semantic_score": float(hit.get("distance") or 0.0)})
        return rows

    def _empty_row(self, event_id: str, raw_content: str, title: str) -> dict[str, Any]:
        now = datetime.now().isoformat(timespec="seconds")
        return {
            "event_id": event_id,
            "content_hash": self._content_hash(raw_content),
            "raw_content": raw_content,
            "title": title,
            "source": "",
            "embedding": [0.0] * self._embedding_dim,
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
            "created_at": now,
            "updated_at": now,
            "expire_at": (datetime.now() + timedelta(days=self._ttl_days)).isoformat(timespec="seconds"),
        }

    @classmethod
    def _row_to_api(cls, row: dict[str, Any]) -> dict[str, Any]:
        item = dict(row)
        for field, fallback in (
            ("matched_persons", []),
            ("matched_keywords", []),
            ("event_similarity", {}),
            ("dimension_scores", {}),
            ("trend_report", {}),
        ):
            item[field] = cls._loads(item.get(field), fallback)
        return item

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def _loads(value: Any, fallback: Any) -> Any:
        if not value:
            return fallback
        if isinstance(value, (list, dict)):
            return value
        try:
            return json.loads(str(value))
        except json.JSONDecodeError:
            return fallback

    @staticmethod
    def _content_hash(raw_content: str) -> str:
        normalized = " ".join(raw_content.split())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def _source_rank(source: str) -> int:
        return {"both": 3, "person_match": 2, "semantic_match": 1}.get(source, 0)
```

- [ ] **Step 3: Export EventsStore**

Modify `blacklist/stores/__init__.py`:

```python
from blacklist.stores.base import EmbeddingFn, FieldSpec, MilvusBaseStore
from blacklist.stores.events_store import EventsStore

__all__ = ["EmbeddingFn", "EventsStore", "FieldSpec", "MilvusBaseStore"]
```

- [ ] **Step 4: Run events store tests**

Run:

```bash
uv run pytest tests/test_events_store.py tests/test_milvus_store_base.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add blacklist/stores/__init__.py blacklist/stores/events_store.py tests/test_events_store.py
git commit -m "feat: persist events and stash recall in milvus"
```

---

### Task 3: Milvus Blacklist Stores and Refactored Filter

**Files:**
- Create: `blacklist/stores/persons_store.py`
- Create: `blacklist/stores/keywords_store.py`
- Create: `blacklist/stores/event_samples_store.py`
- Create: `tests/test_blacklist_milvus_stores.py`
- Modify: `blacklist/filter.py`
- Modify: `blacklist/stores/__init__.py`
- Modify: `tests/test_blacklist_filter.py`

- [ ] **Step 1: Write failing blacklist store tests**

Create `tests/test_blacklist_milvus_stores.py`:

```python
from __future__ import annotations

import pytest

from blacklist.stores.event_samples_store import EventSamplesStore
from blacklist.stores.keywords_store import KeywordsStore
from blacklist.stores.persons_store import PersonsStore
from tests.fakes.fake_milvus import FakeMilvusClient


def fake_embed(text: str) -> list[float]:
    if "分拆交易" in text or "洗钱" in text:
        return [1.0, 0.0, 0.0]
    return [0.0, 1.0, 0.0]


@pytest.mark.asyncio
async def test_persons_store_crud_exact_lookup() -> None:
    client = FakeMilvusClient()
    store = PersonsStore(client)

    await store.append_person("p102", summary="客户P102", description="涉诈账户")

    assert await store.query_person("P102") == 1.0
    assert await store.get_person_stats() == {"P102": 1.0}
    assert await store.remove_person("P102") is True
    assert await store.query_person("P102") is None


@pytest.mark.asyncio
async def test_keywords_store_lists_enabled_keywords() -> None:
    client = FakeMilvusClient()
    store = KeywordsStore(client)

    await store.append_keyword("分拆交易", summary="AML")
    await store.append_keyword("工资入账", summary="normal")
    await store.remove_keyword("工资入账")

    assert await store.query_keywords() == ["分拆交易"]
    assert await store.get_keyword_stats() == {"分拆交易": 1.0}


@pytest.mark.asyncio
async def test_event_samples_store_semantic_match() -> None:
    client = FakeMilvusClient()
    store = EventSamplesStore(client, embedding_fn=fake_embed, embedding_dim=3)
    await store.append_event("S001", "AML样本", "疑似分拆交易与洗钱")
    await store.append_event("S002", "正常样本", "普通工资入账")

    match = await store.find_best_match("客户疑似分拆交易洗钱", threshold=0.5)

    assert match is not None
    assert match.hit is True
    assert match.event_id == "S001"
    assert match.summary == "AML样本"
    assert match.score > 0.5


@pytest.mark.asyncio
async def test_event_samples_store_returns_miss_below_threshold() -> None:
    client = FakeMilvusClient()
    store = EventSamplesStore(client, embedding_fn=fake_embed, embedding_dim=3)
    await store.append_event("S001", "正常样本", "普通工资入账")

    match = await store.find_best_match("分拆交易洗钱", threshold=0.95)

    assert match is None
```

Run:

```bash
uv run pytest tests/test_blacklist_milvus_stores.py -q
```

Expected: FAIL with missing store modules.

- [ ] **Step 2: Implement person store**

Create `blacklist/stores/persons_store.py`:

```python
from __future__ import annotations

from typing import Any

from pymilvus import DataType

from blacklist.stores.base import FieldSpec, MilvusBaseStore


class PersonsStore(MilvusBaseStore):
    collection_name = "blacklist_persons"
    primary_field = "person_id"

    def fields(self) -> list[FieldSpec]:
        return [
            FieldSpec("person_id", DataType.VARCHAR, is_primary=True, max_length=128),
            FieldSpec("summary", DataType.VARCHAR, max_length=1024),
            FieldSpec("description", DataType.VARCHAR, max_length=4096),
            FieldSpec("hit_count", DataType.INT64),
            FieldSpec("enabled", DataType.BOOL),
            FieldSpec("created_at", DataType.VARCHAR, max_length=64),
            FieldSpec("updated_at", DataType.VARCHAR, max_length=64),
        ]

    async def query_person(self, id_number: str) -> float | None:
        rows = self.query_rows(
            f"person_id == {self.quote(id_number.upper())} and enabled == true",
            ["person_id", "hit_count"],
            limit=1,
        )
        return 1.0 if rows else None

    async def append_person(self, id_number: str, summary: str = "", description: str = "") -> int:
        person_id = id_number.upper()
        now = self.now_iso()
        existing = self.query_rows(f"person_id == {self.quote(person_id)}", ["person_id", "hit_count", "created_at"], limit=1)
        row = {
            "person_id": person_id,
            "summary": summary,
            "description": description,
            "hit_count": int(existing[0].get("hit_count") or 0) + 1 if existing else 1,
            "enabled": True,
            "created_at": str(existing[0].get("created_at") or now) if existing else now,
            "updated_at": now,
        }
        return self.upsert_rows([row])

    async def remove_person(self, id_number: str) -> bool:
        person_id = id_number.upper()
        rows = self.query_rows(f"person_id == {self.quote(person_id)}", ["person_id", "summary", "description", "hit_count", "created_at"], limit=1)
        if not rows:
            return False
        row: dict[str, Any] = dict(rows[0])
        row.update({"enabled": False, "updated_at": self.now_iso()})
        return self.upsert_rows([row]) > 0

    async def get_person_stats(self) -> dict[str, float]:
        rows = self.query_rows('person_id != "" and enabled == true', ["person_id", "hit_count"], limit=10000)
        return {str(row["person_id"]): float(row.get("hit_count") or 1.0) for row in rows}

    def list_items(self) -> list[dict[str, Any]]:
        rows = self.query_rows('person_id != "" and enabled == true', ["person_id", "summary", "description", "hit_count", "enabled", "created_at", "updated_at"], limit=10000)
        return [{**row, "value": row["person_id"]} for row in sorted(rows, key=lambda item: str(item.get("updated_at") or ""), reverse=True)]
```

- [ ] **Step 3: Implement keyword store**

Create `blacklist/stores/keywords_store.py`:

```python
from __future__ import annotations

import hashlib
from typing import Any

from pymilvus import DataType

from blacklist.stores.base import FieldSpec, MilvusBaseStore


class KeywordsStore(MilvusBaseStore):
    collection_name = "blacklist_keywords"
    primary_field = "keyword_id"

    def fields(self) -> list[FieldSpec]:
        return [
            FieldSpec("keyword_id", DataType.VARCHAR, is_primary=True, max_length=128),
            FieldSpec("keyword", DataType.VARCHAR, max_length=512),
            FieldSpec("summary", DataType.VARCHAR, max_length=1024),
            FieldSpec("description", DataType.VARCHAR, max_length=4096),
            FieldSpec("hit_count", DataType.INT64),
            FieldSpec("enabled", DataType.BOOL),
            FieldSpec("created_at", DataType.VARCHAR, max_length=64),
            FieldSpec("updated_at", DataType.VARCHAR, max_length=64),
        ]

    async def query_keywords(self) -> list[str]:
        rows = self.query_rows('keyword_id != "" and enabled == true', ["keyword", "updated_at"], limit=10000)
        rows.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        return [str(row["keyword"]) for row in rows]

    async def append_keyword(self, keyword: str, summary: str = "", description: str = "") -> int:
        keyword_id = self.keyword_id(keyword)
        now = self.now_iso()
        existing = self.query_rows(f"keyword_id == {self.quote(keyword_id)}", ["keyword_id", "hit_count", "created_at"], limit=1)
        row = {
            "keyword_id": keyword_id,
            "keyword": keyword,
            "summary": summary,
            "description": description,
            "hit_count": int(existing[0].get("hit_count") or 0) + 1 if existing else 1,
            "enabled": True,
            "created_at": str(existing[0].get("created_at") or now) if existing else now,
            "updated_at": now,
        }
        return self.upsert_rows([row])

    async def remove_keyword(self, keyword: str) -> bool:
        keyword_id = self.keyword_id(keyword)
        rows = self.query_rows(f"keyword_id == {self.quote(keyword_id)}", ["keyword_id", "keyword", "summary", "description", "hit_count", "created_at"], limit=1)
        if not rows:
            return False
        row: dict[str, Any] = dict(rows[0])
        row.update({"enabled": False, "updated_at": self.now_iso()})
        return self.upsert_rows([row]) > 0

    async def get_keyword_stats(self) -> dict[str, float]:
        rows = self.query_rows('keyword_id != "" and enabled == true', ["keyword", "hit_count"], limit=10000)
        return {str(row["keyword"]): float(row.get("hit_count") or 1.0) for row in rows}

    def list_items(self) -> list[dict[str, Any]]:
        rows = self.query_rows('keyword_id != "" and enabled == true', ["keyword_id", "keyword", "summary", "description", "hit_count", "enabled", "created_at", "updated_at"], limit=10000)
        return [{**row, "value": row["keyword"]} for row in sorted(rows, key=lambda item: str(item.get("updated_at") or ""), reverse=True)]

    @staticmethod
    def keyword_id(keyword: str) -> str:
        return hashlib.sha256(keyword.encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Implement event samples store**

Create `blacklist/stores/event_samples_store.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pymilvus import DataType

from blacklist.stores.base import EmbeddingFn, FieldSpec, MilvusBaseStore


@dataclass(frozen=True)
class EventSampleMatch:
    hit: bool
    score: float
    event_id: str
    summary: str
    threshold: float


class EventSamplesStore(MilvusBaseStore):
    collection_name = "blacklist_event_samples"
    primary_field = "sample_id"
    vector_field = "embedding"

    def __init__(self, client: Any, *, embedding_fn: EmbeddingFn, embedding_dim: int = 1024) -> None:
        super().__init__(client, embedding_dim=embedding_dim)
        self._embedding_fn = embedding_fn

    def fields(self) -> list[FieldSpec]:
        return [
            FieldSpec("sample_id", DataType.VARCHAR, is_primary=True, max_length=128),
            FieldSpec("summary", DataType.VARCHAR, max_length=2048),
            FieldSpec("description", DataType.VARCHAR, max_length=8192),
            FieldSpec("embedding", DataType.FLOAT_VECTOR, dim=self._embedding_dim),
            FieldSpec("enabled", DataType.BOOL),
            FieldSpec("created_at", DataType.VARCHAR, max_length=64),
            FieldSpec("updated_at", DataType.VARCHAR, max_length=64),
        ]

    async def append_event(self, event_id: str, summary: str, description: str = "") -> int:
        text = description or summary
        now = self.now_iso()
        existing = self.query_rows(f"sample_id == {self.quote(event_id)}", ["sample_id", "created_at"], limit=1)
        row = {
            "sample_id": event_id,
            "summary": summary,
            "description": description or summary,
            "embedding": await self.resolve_embedding(self._embedding_fn, text),
            "enabled": True,
            "created_at": str(existing[0].get("created_at") or now) if existing else now,
            "updated_at": now,
        }
        return self.upsert_rows([row])

    async def remove_event(self, event_id: str) -> bool:
        rows = self.query_rows(f"sample_id == {self.quote(event_id)}", ["sample_id", "summary", "description", "embedding", "created_at"], limit=1)
        if not rows:
            return False
        row = dict(rows[0])
        row.update({"enabled": False, "updated_at": self.now_iso()})
        return self.upsert_rows([row]) > 0

    async def get_event_count(self) -> int:
        rows = self.query_rows('sample_id != "" and enabled == true', ["sample_id"], limit=10000)
        return len(rows)

    async def get_event_summaries(self) -> dict[str, str]:
        rows = self.query_rows('sample_id != "" and enabled == true', ["sample_id", "summary"], limit=10000)
        return {str(row["sample_id"]): str(row.get("summary") or "") for row in rows}

    async def find_best_match(self, query: str, *, threshold: float) -> EventSampleMatch | None:
        if await self.get_event_count() == 0:
            return None
        self.ensure_collection()
        result = self._client.search(
            collection_name=self.collection_name,
            data=[await self.resolve_embedding(self._embedding_fn, query)],
            anns_field=self.vector_field,
            filter="enabled == true",
            limit=1,
            output_fields=["sample_id", "summary", "description"],
        )
        hits = result[0] if result else []
        if not hits:
            return None
        hit = hits[0]
        score = float(hit.get("distance") or 0.0)
        entity = hit.get("entity") or {}
        sample_id = str(entity.get("sample_id") or hit.get("id") or "")
        summary = str(entity.get("summary") or entity.get("description") or "")
        if score <= threshold:
            return None
        return EventSampleMatch(hit=True, score=score, event_id=sample_id, summary=summary, threshold=threshold)

    def list_items(self) -> list[dict[str, Any]]:
        rows = self.query_rows('sample_id != "" and enabled == true', ["sample_id", "summary", "description", "enabled", "created_at", "updated_at"], limit=10000)
        return [{**row, "value": row["sample_id"]} for row in sorted(rows, key=lambda item: str(item.get("updated_at") or ""), reverse=True)]
```

- [ ] **Step 5: Refactor BlacklistFilter tests to focused stores**

Modify `tests/test_blacklist_filter.py` so the fixtures no longer import `blacklist.store.BlacklistStore` or Redis. Use this test support:

```python
class FakePersonsStore:
    def __init__(self, hits: set[str] | None = None) -> None:
        self.hits = {item.upper() for item in hits or set()}
        self.appended: list[str] = []

    async def query_person(self, id_number: str) -> float | None:
        return 1.0 if id_number.upper() in self.hits else None


class FakeKeywordsStore:
    def __init__(self, keywords: list[str] | None = None) -> None:
        self.keywords = keywords or []

    async def query_keywords(self) -> list[str]:
        return self.keywords


class FakeSamplesStore:
    def __init__(self, match=None) -> None:
        self.match = match

    async def find_best_match(self, query: str, *, threshold: float):
        return self.match


@pytest.fixture
def filter_instance():
    return BlacklistFilter(
        persons_store=FakePersonsStore(),
        keywords_store=FakeKeywordsStore(),
        samples_store=FakeSamplesStore(),
        similarity_threshold=0.5,
    )
```

Replace Redis-specific assertions such as `mock_redis.zincrby.assert_not_called()` with assertions about returned matches. Keep the existing behavioral test names and expected PASS/STASH outcomes.

Add this event similarity test:

```python
@pytest.mark.asyncio
async def test_event_similarity_details_come_from_event_sample_store(sample_event):
    filter_instance = BlacklistFilter(
        persons_store=FakePersonsStore(),
        keywords_store=FakeKeywordsStore(),
        samples_store=FakeSamplesStore(
            EventSampleMatch(
                hit=True,
                score=0.91,
                event_id="E-FIN-AML-001",
                summary="疑似分拆交易与洗钱",
                threshold=0.5,
            )
        ),
        similarity_threshold=0.5,
    )

    result = await filter_instance._check_event_similarity_details(sample_event)

    assert result.hit is True
    assert result.score == pytest.approx(0.91)
    assert result.event_id == "E-FIN-AML-001"
    assert result.summary == "疑似分拆交易与洗钱"
```

Run:

```bash
uv run pytest tests/test_blacklist_filter.py -q
```

Expected: FAIL because `BlacklistFilter` still expects `store=BlacklistStore`.

- [ ] **Step 6: Refactor BlacklistFilter implementation**

Modify `blacklist/filter.py`:

```python
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Protocol

from models import NormalizedEvent

logger = logging.getLogger(__name__)


class PersonsLookup(Protocol):
    async def query_person(self, id_number: str) -> float | None: ...


class KeywordsLookup(Protocol):
    async def query_keywords(self) -> list[str]: ...


class EventSamplesLookup(Protocol):
    async def find_best_match(self, query: str, *, threshold: float): ...


@dataclass
class EventSimilarityHit:
    hit: bool = False
    score: float = 0.0
    event_id: str = ""
    summary: str = ""
    threshold: float = 0.0


@dataclass
class BlacklistCheckResult:
    should_proceed: bool
    matched_persons: list[str] = field(default_factory=list)
    matched_keywords: list[str] = field(default_factory=list)
    event_similarity: EventSimilarityHit = field(default_factory=EventSimilarityHit)

    @property
    def event_hit(self) -> bool:
        return self.event_similarity.hit

    def as_legacy_tuple(self) -> tuple[bool, list[str], list[str], bool]:
        return (self.should_proceed, self.matched_persons, self.matched_keywords, self.event_hit)


class BlacklistFilter:
    def __init__(
        self,
        persons_store: PersonsLookup,
        keywords_store: KeywordsLookup,
        samples_store: EventSamplesLookup,
        similarity_threshold: float | None = None,
    ) -> None:
        self._persons = persons_store
        self._keywords = keywords_store
        self._samples = samples_store
        self._similarity_threshold = similarity_threshold or float(os.getenv("BLACKLIST_EVENT_SIMILARITY_THRESHOLD", "0.5"))

    async def check(self, event: NormalizedEvent) -> tuple[bool, list[str], list[str], bool]:
        return (await self.check_with_details(event)).as_legacy_tuple()

    async def check_with_details(self, event: NormalizedEvent) -> BlacklistCheckResult:
        matched_persons = await self._check_persons(event)
        matched_keywords = await self._check_keywords(event)
        event_similarity = await self._check_event_similarity_details(event)
        should_proceed = bool(matched_persons or matched_keywords or event_similarity.hit)
        if should_proceed:
            logger.info(
                "blacklist PASS: event_id=%s, persons=%s, keywords=%s, event_sim=%s, event_sim_score=%.4f, event_sim_id=%s",
                event.event_id,
                matched_persons,
                matched_keywords,
                event_similarity.hit,
                event_similarity.score,
                event_similarity.event_id,
            )
        else:
            logger.info("blacklist STASH: event_id=%s, no matches", event.event_id)
        return BlacklistCheckResult(
            should_proceed=should_proceed,
            matched_persons=matched_persons,
            matched_keywords=matched_keywords,
            event_similarity=event_similarity,
        )

    async def _check_persons(self, event: NormalizedEvent) -> list[str]:
        from utils.text import extract_person_id_numbers

        hits: list[str] = []
        for pid in extract_person_id_numbers(event.raw_content):
            if await self._persons.query_person(pid) is not None:
                hits.append(pid)
        return hits

    async def _check_keywords(self, event: NormalizedEvent) -> list[str]:
        keywords = await self._keywords.query_keywords()
        return [keyword for keyword in keywords if keyword in event.raw_content]

    async def _check_event_similarity(self, event: NormalizedEvent) -> bool:
        return (await self._check_event_similarity_details(event)).hit

    async def _check_event_similarity_details(self, event: NormalizedEvent) -> EventSimilarityHit:
        miss = EventSimilarityHit(threshold=self._similarity_threshold)
        try:
            match = await self._samples.find_best_match(event.raw_content, threshold=self._similarity_threshold)
        except Exception as exc:
            logger.warning("event sample similarity check failed: %s", exc)
            return miss
        if match is None:
            return miss
        return EventSimilarityHit(
            hit=bool(match.hit),
            score=float(match.score),
            event_id=str(match.event_id),
            summary=str(match.summary),
            threshold=float(match.threshold),
        )
```

- [ ] **Step 7: Export blacklist stores**

Modify `blacklist/stores/__init__.py`:

```python
from blacklist.stores.base import EmbeddingFn, FieldSpec, MilvusBaseStore
from blacklist.stores.event_samples_store import EventSampleMatch, EventSamplesStore
from blacklist.stores.events_store import EventsStore
from blacklist.stores.keywords_store import KeywordsStore
from blacklist.stores.persons_store import PersonsStore

__all__ = [
    "EmbeddingFn",
    "EventSampleMatch",
    "EventSamplesStore",
    "EventsStore",
    "FieldSpec",
    "KeywordsStore",
    "MilvusBaseStore",
    "PersonsStore",
]
```

- [ ] **Step 8: Run blacklist tests**

Run:

```bash
uv run pytest tests/test_blacklist_milvus_stores.py tests/test_blacklist_filter.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add blacklist/filter.py blacklist/stores/__init__.py blacklist/stores/persons_store.py blacklist/stores/keywords_store.py blacklist/stores/event_samples_store.py tests/test_blacklist_milvus_stores.py tests/test_blacklist_filter.py
git commit -m "feat: move blacklist matching to milvus stores"
```

---

### Task 4: Store Factory and Root Runtime Integration

**Files:**
- Create: `blacklist/stores/factory.py`
- Create: `tests/test_default_milvus_runtime.py`
- Modify: `blacklist/__init__.py`
- Modify: `main.py`

- [ ] **Step 1: Write failing runtime test for configured embedder**

Create `tests/test_default_milvus_runtime.py`:

```python
from __future__ import annotations

from datetime import datetime

import pytest

import main
from blacklist.stores import factory
from models import EventSource, NormalizedEvent
from tests.fakes.fake_milvus import FakeMilvusClient


@pytest.mark.asyncio
async def test_process_message_detailed_uses_milvus_and_configured_embedder(monkeypatch) -> None:
    fake_client = FakeMilvusClient()
    captured_embedder_configs: list[dict] = []

    async def fake_normalize_payload_to_event(payload, config):
        return NormalizedEvent(
            event_id="E-MILVUS-STASH",
            source=EventSource.TRANSACTION,
            raw_content="客户 P102 工资入账后日常消费",
            title="低风险历史",
            timestamp=datetime(2026, 6, 23, 10, 0, 0),
        )

    def fake_create_client(config):
        return fake_client

    def fake_create_embedding_fn(embedder_config):
        captured_embedder_configs.append(dict(embedder_config))
        return lambda text: [0.0, 1.0, 0.0]

    monkeypatch.setattr(main, "normalize_payload_to_event", fake_normalize_payload_to_event)
    monkeypatch.setattr(factory, "create_milvus_client", fake_create_client)
    monkeypatch.setattr(factory, "create_embedding_fn", fake_create_embedding_fn)

    config = main.load_config()
    config["embedder"] = {
        "model": "BAAI/bge-m3",
        "api_key": "env-embedder-key",
        "api_base": "http://127.0.0.1:1234/v1",
    }

    result = await main.process_message_detailed("客户 P102 工资入账后日常消费", config=config)

    assert result["status"] == "stashed"
    assert result["storage"] == {"backend": "milvus", "events_collection": "events"}
    assert captured_embedder_configs == [config["embedder"]]
    assert fake_client.rows["events"]["E-MILVUS-STASH"]["status"] == "stashed"
```

Run:

```bash
uv run pytest tests/test_default_milvus_runtime.py -q
```

Expected: FAIL because `blacklist.stores.factory` does not exist and `main.py` still imports `blacklist.runtime_storage`.

- [ ] **Step 2: Implement store factory with configured embedder**

Create `blacklist/stores/factory.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from blacklist.milvus_client import create_milvus_client, milvus_config_from_app
from blacklist.stores.event_samples_store import EventSamplesStore
from blacklist.stores.events_store import EventsStore
from blacklist.stores.keywords_store import KeywordsStore
from blacklist.stores.persons_store import PersonsStore
from blacklist.stores.review_actions_store import ReviewActionsStore


@dataclass(frozen=True)
class StoreBundle:
    events: EventsStore
    persons: PersonsStore
    keywords: KeywordsStore
    event_samples: EventSamplesStore
    review_actions: ReviewActionsStore


def create_embedding_fn(config: dict[str, Any]):
    from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig

    embedder = OpenAIEmbedder(
        config=OpenAIEmbedderConfig(
            embedding_model=config.get("model") or "BAAI/bge-m3",
            api_key=config.get("api_key") or "",
            base_url=config.get("api_base") or "https://api.openai.com/v1",
        )
    )
    return embedder.create


def create_store_bundle(config: dict[str, Any]) -> StoreBundle:
    client = create_milvus_client(milvus_config_from_app(config))
    milvus_config = config.get("milvus", {})
    embedding_dim = int(milvus_config.get("embedding_dim") or 1024)
    ttl_days = int(milvus_config.get("stash_ttl_days") or 90)
    embedding_fn = create_embedding_fn(config.get("embedder", {}))
    return StoreBundle(
        events=EventsStore(client=client, embedding_fn=embedding_fn, embedding_dim=embedding_dim, ttl_days=ttl_days),
        persons=PersonsStore(client=client, embedding_dim=embedding_dim),
        keywords=KeywordsStore(client=client, embedding_dim=embedding_dim),
        event_samples=EventSamplesStore(client=client, embedding_fn=embedding_fn, embedding_dim=embedding_dim),
        review_actions=ReviewActionsStore(client=client, embedding_dim=embedding_dim),
    )
```

This step references `ReviewActionsStore`; Task 5 creates it. For this task to pass before Task 5, add a minimal `blacklist/stores/review_actions_store.py`:

```python
from __future__ import annotations

from typing import Any

from pymilvus import DataType

from blacklist.stores.base import FieldSpec, MilvusBaseStore


class ReviewActionsStore(MilvusBaseStore):
    collection_name = "review_actions"
    primary_field = "action_id"

    def fields(self) -> list[FieldSpec]:
        return [
            FieldSpec("action_id", DataType.VARCHAR, is_primary=True, max_length=128),
            FieldSpec("event_id", DataType.VARCHAR, max_length=128),
            FieldSpec("action_type", DataType.VARCHAR, max_length=128),
            FieldSpec("comment", DataType.VARCHAR, max_length=4096),
            FieldSpec("created_at", DataType.VARCHAR, max_length=64),
        ]

    def list_for_event(self, event_id: str) -> list[dict[str, Any]]:
        rows = self.query_rows(f"event_id == {self.quote(event_id)}", ["action_id", "event_id", "action_type", "comment", "created_at"], limit=10000)
        return sorted(rows, key=lambda item: str(item.get("created_at") or ""), reverse=True)
```

- [ ] **Step 3: Update package exports**

Modify `blacklist/__init__.py`:

```python
from blacklist.filter import BlacklistCheckResult, BlacklistFilter, EventSimilarityHit
from blacklist.stores import EventSamplesStore, EventsStore, KeywordsStore, PersonsStore
from blacklist.stores.factory import StoreBundle, create_store_bundle

__all__ = [
    "BlacklistCheckResult",
    "BlacklistFilter",
    "EventSamplesStore",
    "EventSimilarityHit",
    "EventsStore",
    "KeywordsStore",
    "PersonsStore",
    "StoreBundle",
    "create_store_bundle",
]
```

- [ ] **Step 4: Update `main.py` imports and config defaults**

In `main.py`, replace:

```python
from blacklist.runtime_storage import (
    create_blacklist_store,
    create_stash_store,
    default_database_url,
    storage_config,
)
```

with:

```python
from blacklist.stores.factory import StoreBundle, create_store_bundle
```

Remove `default_database_url()` usage from `load_config()` and replace the storage/milvus parts with:

```python
"storage": {
    "backend": "milvus",
},
"milvus": {
    "uri": os.getenv("MILVUS_URI") or "http://localhost:19530",
    "token": os.getenv("MILVUS_TOKEN") or "",
    "stash_collection": os.getenv("MILVUS_STASH_COLLECTION") or "events",
    "stash_ttl_days": int(os.getenv("KV_TTL_DAYS") or "90"),
    "semantic_top_k": int(os.getenv("STASH_SEMANTIC_TOP_K") or "10"),
    "rerank_min_score": float(os.getenv("STASH_RERANK_MIN_SCORE") or "0.7"),
    "rerank_enabled": os.getenv("STASH_RERANK_ENABLED", "true").lower()
    not in ("0", "false", "no"),
    "max_per_person": int(os.getenv("BATCH_MAX_PER_PERSON") or "20"),
    "embedding_dim": int(os.getenv("EMBEDDING_DIM") or "1024"),
},
```

Update the config log line to remove RabbitMQ:

```python
logger.info(
    "config loaded: neo4j=%s, milvus=%s, llm=%s, embedder=%s",
    config["neo4j"]["uri"],
    config["milvus"]["uri"],
    config["llm"]["model"],
    config["embedder"]["model"],
)
```

- [ ] **Step 5: Update `process_message_detailed()` to write through Milvus stores**

Replace the storage setup block inside `process_message_detailed()` with:

```python
stores = create_store_bundle(config)
id_numbers = extract_person_id_numbers(normalized_event.raw_content)
bl_filter = BlacklistFilter(
    persons_store=stores.persons,
    keywords_store=stores.keywords,
    samples_store=stores.event_samples,
)
```

Immediately after store creation, write the pending event:

```python
await stores.events.upsert_event(
    normalized_event,
    person_ids=id_numbers or [],
    status="pending",
    blacklist_decision="pending",
)
```

In the STASH branch, replace `stash_store.stash_event(...)` with:

```python
stashed_count = await stores.events.upsert_event(
    normalized_event,
    person_ids=id_numbers or [],
    status="stashed",
    blacklist_decision="miss",
    matched_persons=blacklist_result.matched_persons,
    matched_keywords=blacklist_result.matched_keywords,
    event_similarity=blacklist_result.event_similarity.__dict__,
)
```

Return this storage payload:

```python
"storage": {"backend": "milvus", "events_collection": config["milvus"]["stash_collection"]},
```

In the PASS branch, append matches through focused stores:

```python
for pid in blacklist_result.matched_persons:
    await stores.persons.append_person(pid)
for keyword in blacklist_result.matched_keywords:
    await stores.keywords.append_keyword(keyword)
if blacklist_result.event_hit:
    await stores.event_samples.append_event(
        normalized_event.event_id,
        normalized_event.summary or normalized_event.raw_content[:200],
        normalized_event.raw_content,
    )
```

Create the flow with:

```python
flow = SentinelPipelineFlow(
    config,
    normalized_event,
    None,
    stores,
    stores.events,
    id_numbers,
)
```

After the flow completes and before returning, persist the analysis result:

```python
analysis_result = {
    "event_id": normalized_event.event_id,
    "status": "analyzed",
    "risk_level": normalized_event.risk_level,
    "risk_score": normalized_event.risk_score,
    "summary": normalized_event.summary,
    "event_type": normalized_event.event_type,
    "reasoning": normalized_event.reasoning,
    "dimension_scores": flow.state.get("risk_result", {}).get("dimension_scores", {}),
    "trend_report": flow.state.get("trend_report", {}),
    "blacklist": {
        "decision": "PASS",
        "matched_persons": blacklist_result.matched_persons,
        "matched_keywords": blacklist_result.matched_keywords,
        "event_similarity": blacklist_result.event_similarity.__dict__,
    },
    "raw_content": normalized_event.raw_content,
    "title": normalized_event.title,
}
await stores.events.upsert_analysis_result(analysis_result)
```

Remove the `finally` block that closes Redis.

- [ ] **Step 6: Run runtime tests**

Run:

```bash
uv run pytest tests/test_default_milvus_runtime.py tests/test_events_store.py tests/test_blacklist_filter.py -q
```

Expected: PASS.

- [ ] **Step 7: Verify imports still work**

Run:

```bash
uv run python -c "import main; import backend.app.main; print('imports ok')"
```

Expected: prints `imports ok`.

- [ ] **Step 8: Commit**

```bash
git add blacklist/__init__.py blacklist/stores/factory.py blacklist/stores/review_actions_store.py main.py tests/test_default_milvus_runtime.py
git commit -m "feat: use milvus stores in default runtime"
```

---

### Task 5: Web API Repository, Review Actions, Dashboard, and Health

**Files:**
- Modify: `blacklist/stores/review_actions_store.py`
- Create: `backend/app/services/store_provider.py`
- Modify: `backend/app/repositories/events.py`
- Modify: `backend/app/api/routes_events.py`
- Modify: `backend/app/api/routes_blacklist.py`
- Modify: `backend/app/api/routes_dashboard.py`
- Modify: `backend/app/api/routes_system.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/core/config.py`
- Create: `tests/test_default_milvus_api.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/test_default_milvus_api.py`:

```python
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.services import store_provider


class FakeEvents:
    def __init__(self) -> None:
        self.deleted: list[str] = []
        self.rows = {
            "E001": {
                "event_id": "E001",
                "title": "分拆交易",
                "raw_content": "客户 P102 疑似分拆交易",
                "summary": "疑似分拆交易",
                "status": "analyzed",
                "risk_level": "high",
                "risk_score": 0.91,
                "event_type": "反洗钱",
                "matched_persons": ["P102"],
                "matched_keywords": ["分拆交易"],
                "event_similarity": {},
                "dimension_scores": {},
                "trend_report": {},
                "created_at": "2026-06-23T09:00:00",
                "updated_at": "2026-06-23T09:00:00",
            }
        }

    def list_events(self, *, page=1, page_size=20, risk_level=None, keyword=None):
        items = list(self.rows.values())
        if risk_level:
            items = [item for item in items if item["risk_level"] == risk_level]
        if keyword:
            items = [item for item in items if keyword in item["raw_content"]]
        return {"total": len(items), "page": page, "page_size": page_size, "items": items}

    def get_event(self, event_id: str):
        return self.rows.get(event_id)

    def delete_event(self, event_id: str) -> bool:
        if event_id not in self.rows:
            return False
        self.deleted.append(event_id)
        del self.rows[event_id]
        return True

    def dashboard_overview_rows(self):
        return list(self.rows.values())


class FakeReviews:
    def __init__(self) -> None:
        self.rows = []

    def list_for_event(self, event_id: str):
        return [row for row in self.rows if row["event_id"] == event_id]

    def create(self, event_id: str, action_type: str, comment: str):
        row = {
            "action_id": "A001",
            "event_id": event_id,
            "action_type": action_type,
            "comment": comment,
            "created_at": "2026-06-23T09:30:00",
        }
        self.rows.append(row)
        return row

    def list_recent(self, limit: int = 8):
        return self.rows[:limit]


class FakeBlacklistStore:
    def __init__(self, kind: str) -> None:
        self.kind = kind
        self.items = {}

    def list_items(self):
        return list(self.items.values())

    async def append_person(self, value: str, summary: str = "", description: str = ""):
        self.items[value] = {"value": value, "summary": summary, "description": description}
        return 1

    async def append_keyword(self, value: str, summary: str = "", description: str = ""):
        self.items[value] = {"value": value, "summary": summary, "description": description}
        return 1

    async def append_event(self, value: str, summary: str, description: str = ""):
        self.items[value] = {"value": value, "summary": summary, "description": description}
        return 1

    async def remove_person(self, value: str):
        return self.items.pop(value, None) is not None

    async def remove_keyword(self, value: str):
        return self.items.pop(value, None) is not None

    async def remove_event(self, value: str):
        return self.items.pop(value, None) is not None


class FakeStoreBundle:
    def __init__(self) -> None:
        self.events = FakeEvents()
        self.review_actions = FakeReviews()
        self.persons = FakeBlacklistStore("person")
        self.keywords = FakeBlacklistStore("keyword")
        self.event_samples = FakeBlacklistStore("event")


def test_default_api_uses_milvus_store_provider(monkeypatch) -> None:
    bundle = FakeStoreBundle()
    bundle.persons.items["P102"] = {"value": "P102", "summary": "客户P102", "description": "涉诈"}

    monkeypatch.setattr(store_provider, "get_store_bundle", lambda: bundle)

    with TestClient(create_app()) as client:
        health = client.get("/api/system/health")
        persons = client.get("/api/blacklist/persons")
        events = client.get("/api/events", params={"risk_level": "high"})
        detail = client.get("/api/events/E001")
        review = client.post("/api/events/E001/review-actions", json={"action_type": "approve", "comment": "confirmed"})
        dashboard = client.get("/api/dashboard/overview")

    assert health.status_code == 200
    assert health.json()["api"] is True
    assert "milvus" in health.json()
    assert persons.status_code == 200
    assert persons.json()["items"][0]["value"] == "P102"
    assert events.json()["total"] == 1
    assert detail.json()["review_actions"] == []
    assert review.json()["created"] is True
    assert dashboard.json()["metrics"]["total_events"] == 1
```

Run:

```bash
uv run pytest tests/test_default_milvus_api.py -q
```

Expected: FAIL because `backend.app.services.store_provider` is missing and API routes still import SQLite session.

- [ ] **Step 2: Complete review actions store**

Replace `blacklist/stores/review_actions_store.py` with:

```python
from __future__ import annotations

import uuid
from typing import Any

from pymilvus import DataType

from blacklist.stores.base import FieldSpec, MilvusBaseStore


class ReviewActionsStore(MilvusBaseStore):
    collection_name = "review_actions"
    primary_field = "action_id"

    def fields(self) -> list[FieldSpec]:
        return [
            FieldSpec("action_id", DataType.VARCHAR, is_primary=True, max_length=128),
            FieldSpec("event_id", DataType.VARCHAR, max_length=128),
            FieldSpec("action_type", DataType.VARCHAR, max_length=128),
            FieldSpec("comment", DataType.VARCHAR, max_length=4096),
            FieldSpec("created_at", DataType.VARCHAR, max_length=64),
        ]

    def create(self, event_id: str, action_type: str, comment: str) -> dict[str, Any]:
        row = {
            "action_id": uuid.uuid4().hex,
            "event_id": event_id,
            "action_type": action_type,
            "comment": comment,
            "created_at": self.now_iso(),
        }
        self.upsert_rows([row])
        return row

    def list_for_event(self, event_id: str) -> list[dict[str, Any]]:
        rows = self.query_rows(
            f"event_id == {self.quote(event_id)}",
            ["action_id", "event_id", "action_type", "comment", "created_at"],
            limit=10000,
        )
        return sorted(rows, key=lambda item: str(item.get("created_at") or ""), reverse=True)

    def list_recent(self, limit: int = 8) -> list[dict[str, Any]]:
        rows = self.query_rows('action_id != ""', ["action_id", "event_id", "action_type", "comment", "created_at"], limit=10000)
        return sorted(rows, key=lambda item: str(item.get("created_at") or ""), reverse=True)[:limit]
```

- [ ] **Step 3: Add store provider**

Create `backend/app/services/store_provider.py`:

```python
from __future__ import annotations

from functools import lru_cache

from blacklist.stores.factory import StoreBundle, create_store_bundle
from main import load_config


@lru_cache(maxsize=1)
def get_store_bundle() -> StoreBundle:
    return create_store_bundle(load_config())


def reset_store_bundle_cache() -> None:
    get_store_bundle.cache_clear()
```

- [ ] **Step 4: Rewrite event repository**

Replace `backend/app/repositories/events.py`:

```python
from __future__ import annotations

from typing import Any

from backend.app.services.store_provider import get_store_bundle


class EventRepository:
    def __init__(self, stores=None) -> None:
        self._stores = stores or get_store_bundle()

    def upsert_from_analysis(self, result: dict[str, Any]) -> None:
        raise RuntimeError("upsert_from_analysis is asynchronous; call EventsStore.upsert_analysis_result from the flow")

    def list_events(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        risk_level: str | None = None,
        keyword: str | None = None,
    ) -> dict:
        return self._stores.events.list_events(
            page=page,
            page_size=page_size,
            risk_level=risk_level,
            keyword=keyword,
        )

    def get_event(self, event_id: str) -> dict | None:
        return self._stores.events.get_event(event_id)

    def delete_event(self, event_id: str) -> bool:
        return self._stores.events.delete_event(event_id)
```

- [ ] **Step 5: Rewrite event routes**

Modify `backend/app/api/routes_events.py` so it imports no SQLite session:

```python
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.app.repositories.events import EventRepository
from backend.app.services.store_provider import get_store_bundle

router = APIRouter(prefix="/api/events", tags=["events"])


class ReviewActionCreate(BaseModel):
    action_type: str = Field(..., min_length=1)
    comment: str = ""


@router.get("")
async def list_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    risk_level: str | None = None,
    keyword: str | None = None,
) -> dict:
    return EventRepository().list_events(page=page, page_size=page_size, risk_level=risk_level, keyword=keyword)


@router.get("/{event_id}")
async def get_event(event_id: str) -> dict:
    stores = get_store_bundle()
    event = stores.events.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")
    event["review_actions"] = stores.review_actions.list_for_event(event_id)
    return event


@router.delete("/{event_id}")
async def delete_event(event_id: str) -> dict:
    deleted = EventRepository().delete_event(event_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="event not found")
    return {"deleted": True, "event_id": event_id}


@router.post("/{event_id}/review-actions")
async def create_review_action(event_id: str, payload: ReviewActionCreate) -> dict:
    stores = get_store_bundle()
    if stores.events.get_event(event_id) is None:
        raise HTTPException(status_code=404, detail="event not found")
    row = stores.review_actions.create(event_id, payload.action_type, payload.comment)
    return {"created": True, **row}
```

- [ ] **Step 6: Rewrite blacklist routes**

Modify `backend/app/api/routes_blacklist.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.services.store_provider import get_store_bundle

router = APIRouter(prefix="/api/blacklist", tags=["blacklist"])
ITEM_TYPE_MAP = {"persons": "person", "keywords": "keyword", "events": "event"}


class BlacklistCreate(BaseModel):
    value: str = Field(..., min_length=1)
    summary: str = ""
    description: str = ""


def _normalize_item_type(item_type: str) -> str:
    normalized = ITEM_TYPE_MAP.get(item_type)
    if normalized is None:
        raise HTTPException(status_code=404, detail="unknown blacklist type")
    return normalized


def _store_for(item_type: str):
    stores = get_store_bundle()
    return {
        "person": stores.persons,
        "keyword": stores.keywords,
        "event": stores.event_samples,
    }[item_type]


@router.get("/{item_type}")
async def list_blacklist_items(item_type: str) -> dict:
    normalized = _normalize_item_type(item_type)
    return {"items": _store_for(normalized).list_items()}


@router.post("/{item_type}")
async def create_blacklist_item(item_type: str, payload: BlacklistCreate) -> dict:
    normalized = _normalize_item_type(item_type)
    store = _store_for(normalized)
    if normalized == "person":
        await store.append_person(payload.value, summary=payload.summary, description=payload.description)
    elif normalized == "keyword":
        await store.append_keyword(payload.value, summary=payload.summary, description=payload.description)
    else:
        await store.append_event(payload.value, payload.summary or payload.value, payload.description)
    return {"created": True, "item_type": normalized, "value": payload.value}


@router.delete("/{item_type}/{value}")
async def delete_blacklist_item(item_type: str, value: str) -> dict:
    normalized = _normalize_item_type(item_type)
    store = _store_for(normalized)
    removed = await {
        "person": store.remove_person,
        "keyword": store.remove_keyword,
        "event": store.remove_event,
    }[normalized](value)
    if not removed:
        raise HTTPException(status_code=404, detail="blacklist item not found")
    return {"deleted": True, "item_type": normalized, "value": value}
```

- [ ] **Step 7: Rewrite dashboard route**

Modify `backend/app/api/routes_dashboard.py` to remove SQLite and aggregate from stores:

```python
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter

from backend.app.services.store_provider import get_store_bundle

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
    stores = get_store_bundle()
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
            "today_events": sum(1 for row in event_rows if str(row.get("created_at", "")).startswith(today)),
            "last_7d_events": sum(1 for row in event_rows if str(row.get("created_at", "")) >= since_7d),
            "high_risk_events": buckets["high"],
            "pending_review": sum(1 for row in event_rows if _risk_bucket(row) == "high" and row["event_id"] not in reviewed_event_ids),
            "blacklist_items": blacklist_count,
            "avg_risk_score": round(score_total / scored_count, 4) if scored_count else None,
            "trend_report_coverage": round(report_count / total, 4) if total else 0,
        },
        "risk_distribution": buckets,
        "event_type_distribution": [{"name": key, "value": value} for key, value in sorted(event_type_counts.items(), key=lambda item: item[1], reverse=True)],
        "top_keywords": [{"name": key, "value": value} for key, value in sorted(keyword_counts.items(), key=lambda item: item[1], reverse=True)[:8]],
        "recent_events": event_rows[:8],
        "recent_reviews": review_rows[:8],
    }
```

- [ ] **Step 8: Rewrite health route**

Modify `backend/app/api/routes_system.py`:

```python
from __future__ import annotations

from fastapi import APIRouter

from backend.app.services.neo4j_graph_service import Neo4jGraphService
from backend.app.services.store_provider import get_store_bundle
from sentinel_edge import collect_hardware_profile

router = APIRouter(prefix="/api/system", tags=["system"])


def _milvus_ready() -> bool:
    try:
        stores = get_store_bundle()
        stores.events.ensure_collection()
        return True
    except Exception:
        return False


async def _neo4j_ready() -> bool:
    service = Neo4jGraphService()
    try:
        await service.graph_by_terms(["health"], limit=1)
        return True
    except Exception:
        return False
    finally:
        await service.close()


@router.get("/health")
async def health() -> dict:
    return {
        "api": True,
        "milvus": _milvus_ready(),
        "neo4j": await _neo4j_ready(),
    }


@router.get("/hardware")
async def hardware() -> dict:
    return collect_hardware_profile().to_dict()
```

- [ ] **Step 9: Remove backend SQLite startup/config**

Modify `backend/app/main.py` by deleting:

```python
from backend.app.db.session import init_db
```

and deleting the startup handler:

```python
@app.on_event("startup")
async def _startup() -> None:
    init_db()
```

Modify `backend/app/core/config.py` to:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    app_name: str = "Sentinel Edge API"
    cors_origins: tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    )


settings = Settings()
```

- [ ] **Step 10: Run API tests**

Run:

```bash
uv run pytest tests/test_default_milvus_api.py tests/test_events_store.py -q
```

Expected: PASS.

- [ ] **Step 11: Verify no backend SQLite imports remain**

Run:

```bash
rg -n "backend\\.app\\.db\\.session|sqlite3|get_connection|DATABASE_URL" backend tests/test_default_milvus_api.py
```

Expected: no output.

- [ ] **Step 12: Commit**

```bash
git add backend/app/services/store_provider.py backend/app/repositories/events.py backend/app/api/routes_events.py backend/app/api/routes_blacklist.py backend/app/api/routes_dashboard.py backend/app/api/routes_system.py backend/app/main.py backend/app/core/config.py blacklist/stores/review_actions_store.py tests/test_default_milvus_api.py
git commit -m "feat: serve web api from milvus stores"
```

---

### Task 6: Scripts and Demo State Use Milvus Stores

**Files:**
- Modify: `scripts/reset_and_seed_blacklist.py`
- Modify: `scripts/run_blacklist_kv_demo.py`
- Modify: `scripts/blacklist_demo_assertions.py`
- Modify: `scripts/cleanup_milvus_duplicates.py`
- Modify: `tests/test_reset_and_seed_blacklist.py`
- Modify: `tests/test_blacklist_demo_assertions.py`

- [ ] **Step 1: Update reset script tests**

Modify `tests/test_reset_and_seed_blacklist.py`:

```python
from __future__ import annotations

import pytest

from scripts.reset_and_seed_blacklist import (
    EVENT_SEEDS,
    KEYWORD_SEEDS,
    PERSON_SEEDS,
    reset_milvus_collections,
    seed_blacklist_stores,
)
from tests.fakes.fake_milvus import FakeMilvusClient


def test_reset_milvus_collections_drops_existing_collections() -> None:
    client = FakeMilvusClient()
    for collection in ("events", "blacklist_persons", "blacklist_keywords", "blacklist_event_samples", "review_actions"):
        client.collections.add(collection)

    dropped = reset_milvus_collections(client)

    assert dropped == ["blacklist_event_samples", "blacklist_keywords", "blacklist_persons", "events", "review_actions"]
    assert client.collections == set()


@pytest.mark.asyncio
async def test_seed_blacklist_stores_writes_persons_keywords_and_samples() -> None:
    client = FakeMilvusClient()
    await seed_blacklist_stores(client=client, embedding_fn=lambda text: [1.0, 0.0, 0.0], embedding_dim=3)

    assert set(client.rows["blacklist_persons"]) == set(PERSON_SEEDS)
    assert len(client.rows["blacklist_keywords"]) == len(KEYWORD_SEEDS)
    assert set(client.rows["blacklist_event_samples"]) == {event_id for event_id, _summary in EVENT_SEEDS}
```

Run:

```bash
uv run pytest tests/test_reset_and_seed_blacklist.py -q
```

Expected: FAIL because reset helpers still depend on Redis and SQLite.

- [ ] **Step 2: Rewrite reset script**

Replace Redis/SQLite parts of `scripts/reset_and_seed_blacklist.py` with:

```python
from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from blacklist.milvus_client import MilvusConfig, create_milvus_client
from blacklist.stores.event_samples_store import EventSamplesStore
from blacklist.stores.factory import create_embedding_fn
from blacklist.stores.keywords_store import KeywordsStore
from blacklist.stores.persons_store import PersonsStore

COLLECTIONS = (
    "events",
    "review_actions",
    "blacklist_persons",
    "blacklist_keywords",
    "blacklist_event_samples",
)

PERSON_SEEDS = ["P05", "P105"]
KEYWORD_SEEDS = [
    "制裁",
    "爆炸",
    "裁员",
    "暴雷",
    "洗钱",
    "反洗钱",
    "分拆交易",
    "涉诈",
    "涉诈账户",
    "虚拟币",
    "保证金",
    "贷款欺诈",
    "包装流水",
    "冻结",
    "新设备",
    "境外 IP",
    "短信验证码",
    "支付通道",
    "投诉",
    "返利",
]
EVENT_SEEDS = [
    ("E-FIN-AML-001", "客户在短时间内向多个新开户账户转出接近阈值资金，随后资金归集至虚拟币平台，疑似分拆交易与洗钱。"),
    ("E-FIN-FRAUD-001", "客户向曾被投诉的涉诈账户转账虚拟币保证金，交易设备异常且登录地点偏离常驻城市。"),
    ("E-FIN-DEVICE-001", "客户账户在非常用设备和异常地理位置登录后立即发起大额转账，疑似账户盗用或电诈转账。"),
    ("E-FIN-MULE-001", "多个客户向同一新开户账户集中转账，资金随后快速出金至外部支付通道，疑似跑分或资金归集账户。"),
]


def reset_milvus_collections(client: Any, collections: tuple[str, ...] = COLLECTIONS) -> list[str]:
    dropped: list[str] = []
    for collection_name in sorted(collections):
        if client.has_collection(collection_name):
            client.drop_collection(collection_name)
            dropped.append(collection_name)
    return dropped


async def seed_blacklist_stores(client: Any, embedding_fn, embedding_dim: int = 1024) -> dict[str, int]:
    persons = PersonsStore(client, embedding_dim=embedding_dim)
    keywords = KeywordsStore(client, embedding_dim=embedding_dim)
    samples = EventSamplesStore(client, embedding_fn=embedding_fn, embedding_dim=embedding_dim)
    for person_id in PERSON_SEEDS:
        await persons.append_person(person_id)
    for keyword in KEYWORD_SEEDS:
        await keywords.append_keyword(keyword)
    for event_id, summary in EVENT_SEEDS:
        await samples.append_event(event_id, summary, summary)
    return {"persons": len(PERSON_SEEDS), "keywords": len(KEYWORD_SEEDS), "event_samples": len(EVENT_SEEDS)}


async def main() -> None:
    load_dotenv(dotenv_path=ROOT / ".env")
    client = create_milvus_client(
        MilvusConfig(
            uri=os.getenv("MILVUS_URI", "http://localhost:19530"),
            token=os.getenv("MILVUS_TOKEN", ""),
        )
    )
    embedding_fn = create_embedding_fn(
        {
            "model": os.getenv("EMBEDDER_MODEL") or "BAAI/bge-m3",
            "api_key": os.getenv("EMBEDDER_API_KEY") or os.getenv("LLM_API_KEY") or "",
            "api_base": os.getenv("EMBEDDER_API_BASE") or "https://api.openai.com/v1",
        }
    )
    dropped = reset_milvus_collections(client)
    seeded = await seed_blacklist_stores(
        client=client,
        embedding_fn=embedding_fn,
        embedding_dim=int(os.getenv("EMBEDDING_DIM") or "1024"),
    )
    print("Reset Milvus and seeded blacklist stores:")
    print(f"  Dropped collections: {dropped}")
    print(f"  Persons: {seeded['persons']}")
    print(f"  Keywords: {seeded['keywords']}")
    print(f"  Event samples: {seeded['event_samples']}")
    close = getattr(client, "close", None)
    if close is not None:
        close()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: Update demo runner**

Modify `scripts/run_blacklist_kv_demo.py`:

- Remove `from redis.asyncio import Redis`.
- Remove `from blacklist.store import BlacklistStore`.
- Import reset helpers:

```python
from scripts.reset_and_seed_blacklist import reset_milvus_collections, seed_blacklist_stores
from blacklist.milvus_client import MilvusConfig, create_milvus_client
from blacklist.stores.factory import create_embedding_fn
```

Replace `reset_demo_state_preserve_neo4j()` with:

```python
async def reset_demo_state_preserve_neo4j() -> None:
    load_dotenv(dotenv_path=ROOT / ".env")
    milvus_uri = os.getenv("MILVUS_URI", "http://localhost:19530")
    milvus_token = os.getenv("MILVUS_TOKEN", "")
    client = create_milvus_client(MilvusConfig(uri=milvus_uri, token=milvus_token))
    embedding_fn = create_embedding_fn(
        {
            "model": os.getenv("EMBEDDER_MODEL") or "BAAI/bge-m3",
            "api_key": os.getenv("EMBEDDER_API_KEY") or os.getenv("LLM_API_KEY") or "",
            "api_base": os.getenv("EMBEDDER_API_BASE") or "https://api.openai.com/v1",
        }
    )
    try:
        dropped = reset_milvus_collections(client)
        seeded = await seed_blacklist_stores(
            client=client,
            embedding_fn=embedding_fn,
            embedding_dim=int(os.getenv("EMBEDDING_DIM") or "1024"),
        )
        log_detail("Reset demo state and seeded Milvus blacklist stores:")
        log_detail("  Neo4j: preserved existing graph nodes")
        log_detail(f"  Dropped Milvus collections: {dropped}")
        log_detail(f"  Seeded blacklist stores: {seeded}")
    finally:
        close = getattr(client, "close", None)
        if close is not None:
            close()
```

Update user-facing text:

```python
print("[1/3] 保留 Neo4j，重置 Milvus 并预置黑名单测试数据...\n")
print("自动回放完成，请结合日志与 Milvus/Neo4j 检查结果")
```

- [ ] **Step 4: Update Milvus assertions and cleanup script**

In `scripts/blacklist_demo_assertions.py`, replace:

```python
from blacklist.milvus_stash import MilvusStashStore
```

with:

```python
from blacklist.milvus_client import MilvusConfig, create_milvus_client
from blacklist.stores.events_store import EventsStore
from blacklist.stores.factory import create_embedding_fn
```

Change the default collection string from `stashed_events` to `events` wherever it appears.

Build the inspector store as:

```python
def _default_events_store() -> EventsStore:
    client = create_milvus_client(
        MilvusConfig(
            uri=os.getenv("MILVUS_URI", "http://localhost:19530"),
            token=os.getenv("MILVUS_TOKEN", ""),
        )
    )
    embedding_fn = create_embedding_fn(
        {
            "model": os.getenv("EMBEDDER_MODEL") or "BAAI/bge-m3",
            "api_key": os.getenv("EMBEDDER_API_KEY") or os.getenv("LLM_API_KEY") or "",
            "api_base": os.getenv("EMBEDDER_API_BASE") or "https://api.openai.com/v1",
        }
    )
    return EventsStore(client=client, embedding_fn=embedding_fn, embedding_dim=int(os.getenv("EMBEDDING_DIM") or "1024"))
```

In `scripts/cleanup_milvus_duplicates.py`, replace `MilvusStashStore` with `EventsStore` and call:

```python
deleted = store.cleanup_duplicate_content(limit=args.limit)
```

- [ ] **Step 5: Run script tests**

Run:

```bash
uv run pytest tests/test_reset_and_seed_blacklist.py tests/test_blacklist_demo_assertions.py -q
```

Expected: PASS.

- [ ] **Step 6: Verify no script Redis imports remain**

Run:

```bash
rg -n "redis|Redis|blacklist\\.store|stashed_events|DATABASE_URL|sqlite" scripts tests/test_reset_and_seed_blacklist.py tests/test_blacklist_demo_assertions.py
```

Expected: no output except historical prose inside report docs outside these paths.

- [ ] **Step 7: Commit**

```bash
git add scripts/reset_and_seed_blacklist.py scripts/run_blacklist_kv_demo.py scripts/blacklist_demo_assertions.py scripts/cleanup_milvus_duplicates.py tests/test_reset_and_seed_blacklist.py tests/test_blacklist_demo_assertions.py
git commit -m "feat: seed and inspect demo state through milvus"
```

---

### Task 7: Remove SQLite/Redis Storage Modules and Old Tests

**Files:**
- Delete: `blacklist/store.py`
- Delete: `blacklist/sqlite_store.py`
- Delete: `blacklist/sqlite_stash.py`
- Delete: `blacklist/runtime_storage.py`
- Delete: `blacklist/milvus_stash.py`
- Delete: `backend/app/db/session.py`
- Delete: `tests/test_sqlite_blacklist_store.py`
- Delete: `tests/test_sqlite_stash_store.py`
- Delete: `tests/test_default_sqlite_api.py`
- Delete: `tests/test_default_sqlite_runtime.py`
- Delete: `tests/test_blacklist_manager.py`
- Modify: any tests still importing deleted modules.

- [ ] **Step 1: Confirm no production imports remain before deletion**

Run:

```bash
rg -n "blacklist\\.store|sqlite_store|sqlite_stash|runtime_storage|milvus_stash|backend\\.app\\.db\\.session" blacklist backend main.py scripts tests
```

Expected: output only from files listed for deletion or tests being replaced in this task.

- [ ] **Step 2: Delete old modules and tests**

Run:

```bash
rm -f blacklist/store.py blacklist/sqlite_store.py blacklist/sqlite_stash.py blacklist/runtime_storage.py blacklist/milvus_stash.py
rm -f backend/app/db/session.py
rmdir backend/app/db
rm -f tests/test_sqlite_blacklist_store.py tests/test_sqlite_stash_store.py tests/test_default_sqlite_api.py tests/test_default_sqlite_runtime.py tests/test_blacklist_manager.py
```

- [ ] **Step 3: Run import check**

Run:

```bash
uv run python -c "import main; import backend.app.main; from blacklist import BlacklistFilter, EventsStore; print('imports ok')"
```

Expected: prints `imports ok`.

- [ ] **Step 4: Run focused tests**

Run:

```bash
uv run pytest tests/test_milvus_store_base.py tests/test_events_store.py tests/test_blacklist_milvus_stores.py tests/test_blacklist_filter.py tests/test_default_milvus_runtime.py tests/test_default_milvus_api.py -q
```

Expected: PASS.

- [ ] **Step 5: Confirm deleted module names are gone**

Run:

```bash
rg -n "SQLiteBlacklistStore|SQLiteStashStore|BlacklistStore|MilvusStashStore|backend\\.app\\.db\\.session|DATABASE_URL|BLACKLIST_BACKEND|STASH_BACKEND" blacklist backend main.py scripts tests
```

Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add -A blacklist backend tests main.py scripts
git commit -m "refactor: remove sqlite and redis storage paths"
```

---

### Task 8: Compose and Dependency Cleanup

**Files:**
- Modify: `docker-compose.yaml`
- Modify: `compose/milvus.yaml`
- Modify: `pyproject.toml`
- Modify: `requirements.txt`
- Modify: `uv.lock`
- Modify: `consumer.py`
- Modify: `classifier.py`
- Modify: `graph_service.py`
- Modify: `models.py`

- [ ] **Step 1: Update dependency metadata**

Modify `pyproject.toml`:

```toml
[project]
name = "test-sentinel"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "crewai>=1.14.5",
    "fastapi>=0.136.3",
    "graphiti-core>=0.29.1",
    "httpx>=0.28.1",
    "jinja2>=3.1.6",
    "neo4j>=6.2.0",
    "playwright>=1.56.0",
    "plotly>=6.1.0",
    "pydantic>=2.12.5",
    "pymilvus>=3.0.0",
    "pyyaml>=6.0.2",
    "python-dotenv>=1.2.2",
    "ulid-py>=1.1.0",
    "uvicorn>=0.48.0",
]

[project.optional-dependencies]
legacy = [
    "pika>=1.4.1",
    "redis>=7.4.0",
]
```

Modify `requirements.txt` by removing `pika` and `redis`. Keep `pymilvus`.

Run:

```bash
uv lock
```

Expected: `uv.lock` updates without resolver errors.

- [ ] **Step 2: Guard legacy RabbitMQ imports**

At the top of `consumer.py`, `classifier.py`, and `graph_service.py`, replace direct `import pika` with:

```python
try:
    import pika
except ImportError:  # pragma: no cover - exercised only without legacy extra
    pika = None


def _require_pika() -> None:
    if pika is None:
        raise RuntimeError("RabbitMQ entrypoints are deprecated; install the legacy extra to run them: uv sync --extra legacy")
```

Call `_require_pika()` as the first line in each RabbitMQ connection function. Add this module-level comment near the imports:

```python
# DEPRECATED: RabbitMQ service entrypoint kept for legacy demos only.
```

In `models.py`, change the RabbitMQ section header/docstring to:

```python
# Legacy RabbitMQ message envelope
```

- [ ] **Step 3: Update Compose defaults**

Modify `docker-compose.yaml`:

```yaml
include:
  - compose/milvus.yaml
  - compose/neo4j.yaml

networks:
  devopsnetwork:
    driver: bridge
```

Modify `compose/milvus.yaml`:

- Remove `profiles: ["vector"]` from `etcd`.
- Remove `profiles: ["vector"]` from `minio`.
- Remove `profiles: ["vector"]` from `milvus`.
- Keep `profiles: ["vector"]` on `attu`.

- [ ] **Step 4: Verify dependency and compose references**

Run:

```bash
rg -n "\"redis|\"pika|redis>=|pika>=|compose/redis|compose/rabbitmq|profiles: \\[\"vector\"\\]" pyproject.toml requirements.txt docker-compose.yaml compose/milvus.yaml
```

Expected:

- `pyproject.toml` contains `redis` and `pika` only under `[project.optional-dependencies].legacy`.
- `requirements.txt` has no `redis` or `pika`.
- `docker-compose.yaml` has no `compose/redis.yaml` or `compose/rabbitmq.yaml`.
- `compose/milvus.yaml` shows `profiles: ["vector"]` only for `attu`.

- [ ] **Step 5: Run import check without legacy services**

Run:

```bash
uv run python -c "import main; import backend.app.main; import consumer; import classifier; import graph_service; print('imports ok')"
```

Expected: prints `imports ok`.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml requirements.txt uv.lock docker-compose.yaml compose/milvus.yaml consumer.py classifier.py graph_service.py models.py
git commit -m "chore: make redis and rabbitmq legacy dependencies"
```

---

### Task 9: Environment and Documentation Alignment

**Files:**
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/setup.md`
- Modify: `docs/env-vars.md`
- Modify: `docs/commands.md`
- Modify: `docs/testing.md`
- Modify: `docs/pitfalls.md`
- Modify: `docs/competition_plan.md`
- Modify: `docs/competition_paper_outline.md`
- Modify: `docs/competition_ppt_outline.md`
- Modify: `docs/demo_script.md`

- [ ] **Step 1: Update `.env.example`**

Remove these variables from `.env.example`:

```bash
DATABASE_URL
BLACKLIST_BACKEND
STASH_BACKEND
REDIS_HOST
REDIS_PORT
REDIS_PASSWORD
BLACKLIST_REDIS_DB
RABBITMQ_HOST
RABBITMQ_PORT
RABBITMQ_USER
RABBITMQ_PASSWORD
RABBITMQ_MANAGEMENT_PORT
```

Set the Milvus section to:

```bash
# ============ Milvus 存储配置 ============
MILVUS_URI=http://127.0.0.1:19530
MILVUS_TOKEN=
MILVUS_STASH_COLLECTION=events
EMBEDDING_DIM=1024
STASH_SEMANTIC_TOP_K=10
STASH_RERANK_ENABLED=true
STASH_RERANK_MIN_SCORE=0.7
BATCH_MAX_PER_PERSON=20
KV_TTL_DAYS=90
```

Keep embedder variables:

```bash
EMBEDDER_MODEL=BAAI/bge-m3
EMBEDDER_API_KEY=local-dev-key
EMBEDDER_API_BASE=http://127.0.0.1:1234/v1
```

- [ ] **Step 2: Update architecture docs**

In `docs/architecture.md`, replace the storage section with:

```markdown
### 存储边界

- Milvus 是默认业务存储，承担事件全量记录、审核日志、黑名单人员、黑名单关键词、黑名单事件样本和向量语义召回。
- Neo4j 仅承担 Graphiti 时序知识图谱。
- `events` collection 同时保存低风险暂存事件和已分析事件；高风险触发时从该 collection 同时执行同人员召回与语义向量召回。
- 语义向量由 `.env` 中的 `EMBEDDER_MODEL`、`EMBEDDER_API_KEY`、`EMBEDDER_API_BASE` 配置生成，SQLite 本地向量和 hash fallback 不属于当前方案。
- Redis、SQLite 不再是运行时存储后端；RabbitMQ 入口仅保留为 legacy 代码。
```

- [ ] **Step 3: Update setup and commands**

In `docs/setup.md`, make dependency startup:

```markdown
docker compose up -d
uv run uvicorn backend.app.main:app --reload --port 8000
```

Mention Attu as optional:

```markdown
docker compose --profile vector up -d attu
```

In `docs/commands.md`, remove Redis CLI commands and RabbitMQ startup. Add:

```markdown
### 重置 Milvus 演示数据

uv run python scripts/reset_and_seed_blacklist.py

### 清理 Milvus 重复事件

uv run python scripts/cleanup_milvus_duplicates.py --limit 10000
```

- [ ] **Step 4: Update env var docs**

In `docs/env-vars.md`, the storage table must include:

```markdown
| 变量 | 说明 | 默认值 |
|---|---|---|
| `MILVUS_URI` | Milvus SDK 连接地址 | `http://localhost:19530` |
| `MILVUS_TOKEN` | Milvus 鉴权 token，未启用鉴权时为空 | 空 |
| `MILVUS_STASH_COLLECTION` | 统一事件 collection 名称 | `events` |
| `EMBEDDING_DIM` | embedding 维度，需与 `EMBEDDER_MODEL` 输出一致 | `1024` |
| `STASH_SEMANTIC_TOP_K` | 高风险补图前语义召回候选数 | `10` |
| `BATCH_MAX_PER_PERSON` | 每个人员 ID 的同人历史召回上限 | `20` |
| `KV_TTL_DAYS` | 暂存事件保留天数 | `90` |
```

Add:

```markdown
`DATABASE_URL`、`BLACKLIST_BACKEND`、`STASH_BACKEND`、`REDIS_*`、`RABBITMQ_*` 不再参与默认运行路径。
```

- [ ] **Step 5: Update testing and pitfalls docs**

In `docs/testing.md`, replace the default test command with:

```markdown
uv run pytest tests/test_milvus_store_base.py tests/test_events_store.py tests/test_blacklist_milvus_stores.py tests/test_blacklist_filter.py tests/test_default_milvus_api.py tests/test_default_milvus_runtime.py -q
```

In `docs/pitfalls.md`, add:

```markdown
- Milvus 现在是默认依赖，`docker compose up -d` 会启动 etcd、MinIO、Milvus 和 Neo4j；Docker 内存建议至少 8GB。
- `EMBEDDING_DIM` 必须与 `EMBEDDER_MODEL` 输出维度一致，否则 Milvus collection schema 与写入向量维度不匹配。
- `MILVUS_STASH_COLLECTION` 默认是 `events`；旧的 `stashed_events` collection 不会被自动读取。
```

- [ ] **Step 6: Update competition/demo docs**

Replace phrases like `Redis 黑名单` with `Milvus 黑名单 stores`.

Replace phrases like `Milvus 暂存池` with `Milvus events collection`.

Use this pipeline phrase in `docs/competition_plan.md`, `docs/competition_paper_outline.md`, `docs/competition_ppt_outline.md`, and `docs/demo_script.md`:

```markdown
输入 → 标准化 → Milvus 黑名单三路过滤 → events collection 暂存/全量入库 → 本地 LLM 分类 → Graphiti+Neo4j 构图 → 混合检索 → 多维风险评分 → 超阈值则从 Milvus events 同人员+语义召回 → 批量补图 → 二次研判 → Dashboard Agent 摘要
```

- [ ] **Step 7: Verify docs no longer describe SQLite/Redis defaults**

Run:

```bash
rg -n "SQLite 默认|Web 默认.*SQLite|BLACKLIST_BACKEND|STASH_BACKEND|DATABASE_URL|Redis 黑名单|RabbitMQ.*必选|stashed_events" README.md docs .env.example
```

Expected: no output except historical report files under `docs/reports/` and the source spec under `docs/superpowers/specs/`.

- [ ] **Step 8: Commit**

```bash
git add .env.example README.md docs/architecture.md docs/setup.md docs/env-vars.md docs/commands.md docs/testing.md docs/pitfalls.md docs/competition_plan.md docs/competition_paper_outline.md docs/competition_ppt_outline.md docs/demo_script.md
git commit -m "docs: document milvus-only storage architecture"
```

---

### Task 10: Final Verification and Manual QA Gate

**Files:**
- No planned code edits.

- [ ] **Step 1: Run focused test suite**

Run:

```bash
uv run pytest tests/test_milvus_store_base.py tests/test_events_store.py tests/test_blacklist_milvus_stores.py tests/test_blacklist_filter.py tests/test_default_milvus_runtime.py tests/test_default_milvus_api.py tests/test_reset_and_seed_blacklist.py tests/test_blacklist_demo_assertions.py tests/test_run_blacklist_kv_demo.py -q
```

Expected: PASS.

- [ ] **Step 2: Run broader non-integration suite**

Run:

```bash
uv run pytest -m "not integration" -q
```

Expected: PASS. If a pre-existing unrelated test fails, capture the file, test name, and failure reason before continuing.

- [ ] **Step 3: Run lint and compile checks**

Run:

```bash
uv run ruff check blacklist backend scripts tests main.py consumer.py classifier.py graph_service.py models.py
uv run python -m compileall blacklist backend scripts tests main.py consumer.py classifier.py graph_service.py models.py
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 4: Run import boundary checks**

Run:

```bash
uv run python -c "import main; import backend.app.main; import consumer; import classifier; import graph_service; print('imports ok')"
rg -n "blacklist\\.store\\b|sqlite_store|sqlite_stash|runtime_storage|milvus_stash|backend\\.app\\.db\\.session|SQLiteBlacklistStore|SQLiteStashStore|BlacklistStore|MilvusStashStore" blacklist backend main.py scripts tests
rg -n "DATABASE_URL|BLACKLIST_BACKEND|STASH_BACKEND|REDIS_HOST|RABBITMQ_HOST|stashed_events" main.py blacklist backend scripts tests .env.example docker-compose.yaml compose docs README.md
```

Expected:

- First command prints `imports ok`.
- Second `rg` has no output.
- Third `rg` has no output except historical report docs under `docs/reports/`, source specs/plans under `docs/superpowers/`, and the explicit deprecation note in `docs/env-vars.md`.

- [ ] **Step 5: Manual QA with live Milvus/Neo4j**

Start dependencies:

```bash
docker compose up -d
docker compose ps
```

Expected services are up:

- `milvus-etcd`
- `milvus-minio`
- `milvus-standalone`
- `neo4j`

Seed data:

```bash
uv run python scripts/reset_and_seed_blacklist.py
```

Expected output includes:

```text
Reset Milvus and seeded blacklist stores:
  Persons: 2
  Keywords: 20
  Event samples: 4
```

Run a low-risk stash through the root path:

```bash
uv run python - <<'PY'
import asyncio
import main

async def run():
    result = await main.process_message_detailed("客户 P102 工资入账后日常消费，未出现异常设备或涉诈账户。")
    print(result["status"])
    print(result["storage"])
    print(result["event_id"])

asyncio.run(run())
PY
```

Expected:

```text
stashed
{'backend': 'milvus', 'events_collection': 'events'}
<non-empty event id>
```

Run a higher-risk semantic recall path:

```bash
uv run python - <<'PY'
import asyncio
import main

async def run():
    result = await main.process_message_detailed("客户 P102 在新设备登录后向多个新开户账户分拆转账，资金随后流向虚拟币平台。")
    print(result["status"])
    print(result["blacklist"]["decision"])
    print(result["second_risk_applied"])

asyncio.run(run())
PY
```

Expected:

- `status` is `analyzed`.
- `blacklist.decision` is `PASS`.
- The logs show `stash recall fetched_count=` with same-person or semantic candidates from Milvus `events`.

Start API:

```bash
uv run uvicorn backend.app.main:app --port 8000
```

In another shell:

```bash
curl -s http://127.0.0.1:8000/api/system/health
curl -s http://127.0.0.1:8000/api/events?page=1&page_size=5
curl -s http://127.0.0.1:8000/api/dashboard/overview
```

Expected:

- Health JSON has `api`, `milvus`, and `neo4j`.
- Events endpoint returns rows from Milvus.
- Dashboard metrics count Milvus events and blacklist items.

- [ ] **Step 6: Commit verification-only fixes if needed**

If Step 1 through Step 5 required small fixes, commit them:

```bash
git add -A
git commit -m "fix: stabilize milvus storage consolidation"
```

If no fixes were needed, do not create an empty commit.

- [ ] **Step 7: Final branch status**

Run:

```bash
git status --short --branch
git log --oneline --decorate -n 8
```

Expected: branch contains the atomic commits from Tasks 1-9, and working tree is clean.

---

## Self-Review

### Spec Coverage

- Remove SQLite dependency: covered by Tasks 5, 7, 8, and 9.
- Move Redis blacklist storage into Milvus: covered by Tasks 3, 4, 6, 7, 8, and 9.
- Remove RabbitMQ as default dependency while keeping legacy code: covered by Task 8.
- Preserve semantic recall: covered by Task 2 for `events` recall and Task 3 for blacklist event samples; both use the configured embedder.
- Reduce services to Neo4j + Milvus default Compose: covered by Task 8.
- Rename `stashed_events` default to `events`: covered by Tasks 2, 4, 6, 8, 9, and 10.
- Avoid import-breaking intermediate commits: every task includes import or focused tests before commit.

### Placeholder Scan

No placeholder markers, deferred implementation notes, vague validation steps, or unnamed tests remain. Each code step includes concrete code or exact replacement text.

### Type Consistency

The plan consistently uses:

- `StoreBundle.events`, `StoreBundle.persons`, `StoreBundle.keywords`, `StoreBundle.event_samples`, `StoreBundle.review_actions`
- `EventsStore.stash_event`, `EventsStore.fetch_related_events`, `EventsStore.mark_events_graph_built`
- `EventSamplesStore.find_best_match`
- `backend.app.services.store_provider.get_store_bundle`
