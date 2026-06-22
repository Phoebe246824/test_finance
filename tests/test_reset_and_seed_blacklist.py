import sqlite3

import pytest

from scripts.reset_and_seed_blacklist import (
    reset_milvus_collection,
    reset_neo4j_graph,
    reset_sqlite_event_tables,
)


class FakeNeo4jResult:
    def __init__(self, node_count: int) -> None:
        self._node_count = node_count

    async def single(self) -> dict[str, int]:
        return {"node_count": self._node_count}


class FakeNeo4jSession:
    def __init__(self, node_count: int) -> None:
        self.node_count = node_count
        self.query = ""

    async def __aenter__(self) -> "FakeNeo4jSession":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def run(self, query: str) -> FakeNeo4jResult:
        self.query = query
        return FakeNeo4jResult(self.node_count)


class FakeNeo4jDriver:
    def __init__(self, node_count: int) -> None:
        self.closed = False
        self.session_kwargs: dict[str, str] = {}
        self.session_obj = FakeNeo4jSession(node_count)

    def session(self, **kwargs: str) -> FakeNeo4jSession:
        self.session_kwargs = kwargs
        return self.session_obj

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_reset_neo4j_graph_deletes_all_nodes_and_closes_driver() -> None:
    driver = FakeNeo4jDriver(node_count=7)
    factory_calls: list[tuple[str, tuple[str, str]]] = []

    def driver_factory(uri: str, auth: tuple[str, str]) -> FakeNeo4jDriver:
        factory_calls.append((uri, auth))
        return driver

    deleted_count = await reset_neo4j_graph(
        uri="bolt://neo4j:7687",
        user="neo4j",
        password="password",
        database="neo4j",
        driver_factory=driver_factory,
    )

    assert deleted_count == 7
    assert factory_calls == [("bolt://neo4j:7687", ("neo4j", "password"))]
    assert driver.session_kwargs == {"database": "neo4j"}
    assert "DETACH DELETE" in driver.session_obj.query
    assert driver.closed is True


class FakeMilvusClient:
    def __init__(self, *, uri: str, token: str | None) -> None:
        self.uri = uri
        self.token = token
        self.collections = {"stashed_events"}
        self.dropped: list[str] = []
        self.closed = False

    def has_collection(self, collection_name: str) -> bool:
        return collection_name in self.collections

    def drop_collection(self, collection_name: str) -> None:
        self.collections.remove(collection_name)
        self.dropped.append(collection_name)

    def close(self) -> None:
        self.closed = True


def test_reset_milvus_collection_drops_existing_collection() -> None:
    clients: list[FakeMilvusClient] = []

    def client_factory(*, uri: str, token: str | None) -> FakeMilvusClient:
        client = FakeMilvusClient(uri=uri, token=token)
        clients.append(client)
        return client

    dropped = reset_milvus_collection(
        uri="http://localhost:19530",
        token="",
        collection_name="stashed_events",
        client_factory=client_factory,
    )

    assert dropped is True
    assert clients[0].token is None
    assert clients[0].dropped == ["stashed_events"]
    assert clients[0].closed is True


def test_reset_sqlite_event_tables_clears_events_and_reviews_only(tmp_path) -> None:
    db_path = tmp_path / "sentinel_edge.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE financial_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT UNIQUE NOT NULL,
                raw_content TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE review_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                comment TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE blacklist_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_type TEXT NOT NULL,
                value TEXT NOT NULL
            );
            INSERT INTO financial_events (
                event_id, raw_content, status, created_at, updated_at
            ) VALUES ('evt-1', 'raw', 'analyzed', '2026-06-20T10:00:00', '2026-06-20T10:00:00');
            INSERT INTO review_actions (
                event_id, action_type, comment, created_at
            ) VALUES ('evt-1', 'reviewed', 'ok', '2026-06-20T10:01:00');
            INSERT INTO blacklist_items (item_type, value) VALUES ('person', 'P105');
            """
        )

    deleted = reset_sqlite_event_tables(f"sqlite:///{db_path}")

    with sqlite3.connect(db_path) as conn:
        event_count = conn.execute(
            "SELECT COUNT(*) FROM financial_events"
        ).fetchone()[0]
        review_count = conn.execute(
            "SELECT COUNT(*) FROM review_actions"
        ).fetchone()[0]
        blacklist_count = conn.execute(
            "SELECT COUNT(*) FROM blacklist_items"
        ).fetchone()[0]

    assert deleted == {"financial_events": 1, "review_actions": 1}
    assert event_count == 0
    assert review_count == 0
    assert blacklist_count == 1
