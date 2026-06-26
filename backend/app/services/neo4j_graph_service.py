from __future__ import annotations

from neo4j import AsyncGraphDatabase

from backend.app.services.neo4j_graph_serialization import _merge_graph, _merge_paths
from backend.app.services.web_runtime_config import load_web_runtime_config


class Neo4jGraphService:
    def __init__(self) -> None:
        config = load_web_runtime_config()
        neo4j = config["neo4j"]
        self._database = neo4j.get("database") or "neo4j"
        self._driver = AsyncGraphDatabase.driver(
            neo4j["uri"],
            auth=(neo4j["user"], neo4j["password"]),
        )

    async def close(self) -> None:
        await self._driver.close()

    async def graph_by_terms(
        self, terms: list[str], limit: int = 160, depth: int = 2
    ) -> dict:
        clean_terms = [term.strip() for term in terms if term and term.strip()]
        if not clean_terms:
            return {"nodes": [], "edges": []}
        max_depth = max(1, min(depth, 3))
        query = """
        MATCH (n)
        WHERE any(term IN $terms WHERE
            toLower(toString(coalesce(n.name, ''))) CONTAINS toLower(term)
            OR toLower(toString(coalesce(n.id_number, ''))) = toLower(term)
            OR toLower(toString(coalesce(n.uuid, ''))) = toLower(term)
            OR toLower(toString(coalesce(n.content, ''))) CONTAINS toLower(term)
            OR toLower(toString(coalesce(n.summary, ''))) CONTAINS toLower(term)
        )
        WITH collect(DISTINCT n)[0..20] AS seeds
        UNWIND seeds AS seed
        MATCH p = (seed)-[*1..%d]-(m)
        RETURN nodes(p) AS nodes, relationships(p) AS relationships
        LIMIT $limit
        """ % max_depth
        async with self._driver.session(database=self._database) as session:
            result = await session.run(query, terms=clean_terms, limit=limit)
            records = [record async for record in result]
        graph = _merge_paths(records, match_reason="term_search")
        if graph["nodes"]:
            return graph
        return await self._seed_nodes(clean_terms)

    async def _seed_nodes(self, terms: list[str]) -> dict:
        query = """
        MATCH (n)
        WHERE any(term IN $terms WHERE
            toLower(toString(coalesce(n.name, ''))) CONTAINS toLower(term)
            OR toLower(toString(coalesce(n.id_number, ''))) = toLower(term)
            OR toLower(toString(coalesce(n.uuid, ''))) = toLower(term)
        )
        RETURN n, null AS r, null AS m
        LIMIT 30
        """
        async with self._driver.session(database=self._database) as session:
            result = await session.run(query, terms=terms)
            records = [record async for record in result]
        return _merge_graph(records, match_reason="seed_only")

    async def expand_node(self, node_id: str, limit: int = 60) -> dict:
        query = """
        MATCH (n)
        WHERE n.id_number = $node_id
            OR n.uuid = $node_id
            OR n.name = $node_id
            OR elementId(n) = $node_id
        WITH n
        MATCH p = (n)-[*1..2]-(m)
        RETURN nodes(p) AS nodes, relationships(p) AS relationships
        LIMIT $limit
        """
        async with self._driver.session(database=self._database) as session:
            result = await session.run(query, node_id=node_id, limit=limit)
            records = [record async for record in result]
        graph = _merge_paths(records, match_reason="node_expand")
        if graph["nodes"]:
            return graph
        return await self._seed_nodes([node_id])

    async def search_person(self, keyword: str, limit: int = 100) -> dict:
        return await self.graph_by_terms([keyword], limit=limit)
