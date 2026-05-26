import pytest

from scripts.reset_and_seed_blacklist import (
    reset_milvus_collection,
    reset_neo4j_graph,
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
