from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from neo4j import AsyncGraphDatabase


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
        props.get("elementId"),
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
    props = dict(node)
    labels = list(getattr(node, "labels", []) or props.get("labels") or [])
    for label in labels:
        if label not in {"Entity"}:
            return label
    return labels[0] if labels else "Entity"


def _edge_id(rel: Any) -> str:
    if isinstance(rel, str):
        return ""
    if isinstance(rel, dict):
        return _first_text(rel.get("uuid"), rel.get("id"), rel.get("elementId"))
    props = dict(rel)
    return _first_text(
        props.get("uuid"),
        props.get("id"),
        getattr(rel, "element_id", None),
    )


def _edge_label(rel: Any) -> str:
    if isinstance(rel, str):
        return rel
    if isinstance(rel, dict):
        return _first_text(rel.get("name"), rel.get("fact"), rel.get("type"))
    props = dict(rel)
    return _first_text(
        props.get("name"),
        props.get("fact"),
        getattr(rel, "type", None),
        rel.type,
    )


def _serialize_node(node: Any, *, match_reason: str | None = None) -> dict:
    props = {str(key): _jsonable(value) for key, value in dict(node).items()}
    labels = list(getattr(node, "labels", []) or props.get("labels") or [])
    element_id = getattr(node, "element_id", None)
    node_id = _node_id(node) or _first_text(element_id, props.get("elementId"))
    return {
        "id": node_id,
        "neo4j_element_id": element_id,
        "label": _node_label(node),
        "type": _node_type(node),
        "labels": labels,
        "properties": {**props, "elementId": element_id, "labels": labels},
        "match_reason": match_reason,
    }


def _serialize_edge(rel: Any, source: Any, target: Any) -> dict:
    rel_type = (
        rel
        if isinstance(rel, str)
        else _first_text(rel.get("type"), rel.get("relationship_type"), rel.get("name"))
        if isinstance(rel, dict)
        else rel.type
    )
    element_id = rel.get("elementId") if isinstance(rel, dict) else getattr(rel, "element_id", None)
    props = (
        {"source": "path_list", "relationship_type": rel}
        if isinstance(rel, str)
        else {str(key): _jsonable(value) for key, value in rel.items()}
        if isinstance(rel, dict)
        else {str(key): _jsonable(value) for key, value in dict(rel).items()}
    )
    return {
        "id": _edge_id(rel),
        "neo4j_element_id": element_id,
        "source": _node_id(source),
        "target": _node_id(target),
        "label": _edge_label(rel),
        "type": rel_type,
        "properties": {
            **props,
            "elementId": element_id,
            "type": rel_type,
            "startNodeElementId": getattr(getattr(rel, "start_node", None), "element_id", None),
            "endNodeElementId": getattr(getattr(rel, "end_node", None), "element_id", None),
        },
    }


def _path_parts(path: Any) -> tuple[list[Any], list[Any]]:
    if hasattr(path, "nodes") and hasattr(path, "relationships"):
        return list(path.nodes), list(path.relationships)
    if isinstance(path, list):
        nodes = [item for item in path if isinstance(item, dict)]
        relationships = []
        for index, item in enumerate(path):
            if not isinstance(item, str):
                continue
            if index <= 0 or index >= len(path) - 1:
                continue
            source = path[index - 1]
            target = path[index + 1]
            if isinstance(source, dict) and isinstance(target, dict):
                relationships.append((item, source, target))
        return nodes, relationships
    return [], []


def _relationship_value(rel: Any) -> Any:
    if isinstance(rel, tuple) and len(rel) == 3:
        return {"type": rel[1], "source": "relationship_tuple"}
    return rel


def _relationship_nodes(rel: Any, nodes: list[Any]) -> tuple[Any | None, Any | None]:
    if isinstance(rel, tuple) and len(rel) == 3:
        # neo4j result.data() serializes relationships(p) as
        # (end_node_properties, relationship_type, start_node_properties).
        return rel[2], rel[0]

    start_node = getattr(rel, "start_node", None)
    end_node = getattr(rel, "end_node", None)
    if start_node is not None and end_node is not None:
        return start_node, end_node

    start_id = getattr(rel, "start_node_id", None)
    end_id = getattr(rel, "end_node_id", None)
    if start_id is None or end_id is None:
        return None, None

    source = next((node for node in nodes if getattr(node, "id", None) == start_id), None)
    target = next((node for node in nodes if getattr(node, "id", None) == end_id), None)
    return source, target


def _merge_graph(records: Iterable[Any], *, match_reason: str | None = None) -> dict:
    nodes: dict[str, dict] = {}
    edges: dict[str, dict] = {}
    for record in records:
        node = record.get("n") or record.get("seed")
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


def _merge_paths(records: Iterable[Any], *, match_reason: str | None = None) -> dict:
    nodes: dict[str, dict] = {}
    edges: dict[str, dict] = {}
    for record in records:
        path_nodes = record.get("nodes")
        path_relationships = record.get("relationships")
        if path_nodes is None or path_relationships is None:
            path = record.get("p")
            if path is None:
                continue
            path_nodes, path_relationships = _path_parts(path)
        for node in path_nodes:
            serialized = _serialize_node(node, match_reason=match_reason)
            nodes[serialized["id"]] = serialized
        for rel in path_relationships:
            source_node, target_node = _relationship_nodes(rel, path_nodes)
            if source_node is None or target_node is None:
                continue
            rel_value = _relationship_value(rel)
            edge = _serialize_edge(rel_value, source_node, target_node)
            if edge["id"]:
                key = edge["id"]
            else:
                endpoints = sorted([edge["source"], edge["target"]])
                key = f'{endpoints[0]}-{endpoints[1]}-{edge["type"]}'
            edges[key] = edge
    return {"nodes": list(nodes.values()), "edges": list(edges.values())}


def _combine_graphs(*graphs: dict) -> dict:
    nodes: dict[str, dict] = {}
    edges: dict[str, dict] = {}
    for graph in graphs:
        for node in graph.get("nodes") or []:
            node_id = str(node.get("id") or "")
            if node_id:
                nodes[node_id] = node
        for edge in graph.get("edges") or []:
            edge_id = str(
                edge.get("id")
                or f'{edge.get("source")}-{edge.get("target")}-{edge.get("type") or edge.get("label")}'
            )
            if edge_id:
                edges[edge_id] = edge
    return {"nodes": list(nodes.values()), "edges": list(edges.values())}


class Neo4jGraphService:
    def __init__(self) -> None:
        from main import load_config

        config = load_config()
        neo4j = config["neo4j"]
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
        async with self._driver.session(database="neo4j") as session:
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
            OR toLower(toString(coalesce(n.id, ''))) = toLower(term)
            OR toLower(elementId(n)) = toLower(term)
            OR toLower(toString(coalesce(n.content, ''))) CONTAINS toLower(term)
            OR toLower(toString(coalesce(n.summary, ''))) CONTAINS toLower(term)
        )
        RETURN n, null AS r, null AS m
        LIMIT 30
        """
        async with self._driver.session(database="neo4j") as session:
            result = await session.run(query, terms=terms)
            records = [record async for record in result]
        return _merge_graph(records, match_reason="seed_only")

    async def expand_node(self, node_id: str, limit: int = 60) -> dict:
        query = """
        MATCH (n)
        WHERE n.id_number = $node_id
            OR n.uuid = $node_id
            OR n.id = $node_id
            OR n.name = $node_id
            OR elementId(n) = $node_id
        WITH n
        MATCH p = (n)-[*1..2]-(m)
        RETURN nodes(p) AS nodes, relationships(p) AS relationships
        LIMIT $limit
        """
        async with self._driver.session(database="neo4j") as session:
            result = await session.run(query, node_id=node_id, limit=limit)
            records = [record async for record in result]
        graph = _merge_paths(records, match_reason="node_expand")
        if graph["nodes"]:
            return graph
        return await self._seed_nodes([node_id])

    async def search_person(self, keyword: str, limit: int = 100) -> dict:
        term = keyword.strip()
        if not term:
            return {"nodes": [], "edges": []}
        query = """
        MATCH (n)
        WHERE any(value IN [
            n.id_number,
            n.name,
            n.uuid,
            n.id,
            elementId(n),
            n.content,
            n.summary,
            n.title,
            n.description
        ] WHERE toLower(toString(coalesce(value, ''))) CONTAINS toLower($term))
        WITH collect(DISTINCT n)[0..16] AS seeds
        UNWIND seeds AS seed
        OPTIONAL MATCH p = (seed)-[*1..2]-(m)
        RETURN seed AS seed, null AS r, null AS m, nodes(p) AS nodes, relationships(p) AS relationships
        LIMIT $limit
        """
        async with self._driver.session(database="neo4j") as session:
            result = await session.run(query, term=term, limit=limit)
            records = [record async for record in result]
        graph = _combine_graphs(
            _merge_graph(records, match_reason="person_search"),
            _merge_paths(records, match_reason="person_search"),
        )
        if graph["nodes"]:
            return graph
        return await self._seed_nodes([term])
