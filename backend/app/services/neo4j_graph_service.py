from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from neo4j import AsyncGraphDatabase

from main import load_config


def _jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if hasattr(value, "iso_format"):
        return value.iso_format()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _first_text(*values: Any) -> str:
    for value in values:
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _node_id(node: Any) -> str:
    props = dict(node)
    return _first_text(
        props.get("id_number"),
        props.get("uuid"),
        props.get("id"),
        props.get("name"),
        getattr(node, "element_id", None),
    )


def _node_label(node: Any) -> str:
    props = dict(node)
    return _first_text(
        props.get("name"),
        props.get("id_number"),
        props.get("summary"),
        props.get("content"),
        _node_id(node),
    )


def _node_type(node: Any) -> str:
    labels = list(getattr(node, "labels", []))
    for label in labels:
        if label not in {"Entity"}:
            return label
    return labels[0] if labels else "Entity"


def _edge_id(rel: Any) -> str:
    props = dict(rel)
    return _first_text(
        props.get("uuid"),
        props.get("id"),
        getattr(rel, "element_id", None),
    )


def _edge_label(rel: Any) -> str:
    props = dict(rel)
    return _first_text(
        props.get("name"),
        props.get("fact"),
        getattr(rel, "type", None),
        rel.type,
    )


def _serialize_node(node: Any, *, match_reason: str | None = None) -> dict:
    props = {str(key): _jsonable(value) for key, value in dict(node).items()}
    labels = list(getattr(node, "labels", []))
    return {
        "id": _node_id(node),
        "neo4j_element_id": getattr(node, "element_id", None),
        "label": _node_label(node),
        "type": _node_type(node),
        "labels": labels,
        "properties": props,
        "match_reason": match_reason,
    }


def _serialize_edge(rel: Any, source: Any, target: Any) -> dict:
    props = {str(key): _jsonable(value) for key, value in dict(rel).items()}
    return {
        "id": _edge_id(rel),
        "neo4j_element_id": getattr(rel, "element_id", None),
        "source": _node_id(source),
        "target": _node_id(target),
        "label": _edge_label(rel),
        "type": rel.type,
        "properties": props,
    }


def _merge_graph(records: Iterable[Any], *, match_reason: str | None = None) -> dict:
    nodes: dict[str, dict] = {}
    edges: dict[str, dict] = {}
    for record in records:
        node = record.get("n")
        related = record.get("m")
        rel = record.get("r")
        if node is not None:
            serialized = _serialize_node(node, match_reason=match_reason)
            nodes[serialized["id"]] = serialized
        if related is not None:
            serialized = _serialize_node(related)
            nodes[serialized["id"]] = serialized
        if rel is not None and node is not None and related is not None:
            edge = _serialize_edge(rel, node, related)
            edges[edge["id"] or f'{edge["source"]}-{edge["target"]}-{edge["type"]}'] = edge
    return {"nodes": list(nodes.values()), "edges": list(edges.values())}


class Neo4jGraphService:
    def __init__(self) -> None:
        config = load_config()
        neo4j = config["neo4j"]
        self._driver = AsyncGraphDatabase.driver(
            neo4j["uri"],
            auth=(neo4j["user"], neo4j["password"]),
        )

    async def close(self) -> None:
        await self._driver.close()

    async def graph_by_terms(self, terms: list[str], limit: int = 80) -> dict:
        clean_terms = [term.strip() for term in terms if term and term.strip()]
        if not clean_terms:
            return {"nodes": [], "edges": []}
        query = """
        MATCH (n)
        WHERE any(term IN $terms WHERE
            toLower(toString(coalesce(n.name, ''))) CONTAINS toLower(term)
            OR toLower(toString(coalesce(n.id_number, ''))) = toLower(term)
            OR toLower(toString(coalesce(n.uuid, ''))) = toLower(term)
            OR toLower(toString(coalesce(n.content, ''))) CONTAINS toLower(term)
            OR toLower(toString(coalesce(n.summary, ''))) CONTAINS toLower(term)
        )
        OPTIONAL MATCH (n)-[r]-(m)
        RETURN n, r, m
        LIMIT $limit
        """
        async with self._driver.session(database="neo4j") as session:
            result = await session.run(query, terms=clean_terms, limit=limit)
            records = await result.data()
        return _merge_graph(records, match_reason="term_search")

    async def expand_node(self, node_id: str, limit: int = 60) -> dict:
        query = """
        MATCH (n)
        WHERE n.id_number = $node_id
            OR n.uuid = $node_id
            OR n.name = $node_id
            OR elementId(n) = $node_id
        OPTIONAL MATCH (n)-[r]-(m)
        RETURN n, r, m
        LIMIT $limit
        """
        async with self._driver.session(database="neo4j") as session:
            result = await session.run(query, node_id=node_id, limit=limit)
            records = await result.data()
        return _merge_graph(records, match_reason="node_expand")

    async def search_person(self, keyword: str, limit: int = 100) -> dict:
        return await self.graph_by_terms([keyword], limit=limit)
