from __future__ import annotations

from collections.abc import Iterable
from typing import Any


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
    return {
        "id": _node_id(node),
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
    element_id = (
        rel.get("elementId")
        if isinstance(rel, dict)
        else getattr(rel, "element_id", None)
    )
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
            "startNodeElementId": getattr(
                getattr(rel, "start_node", None), "element_id", None
            ),
            "endNodeElementId": getattr(
                getattr(rel, "end_node", None), "element_id", None
            ),
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
        return rel[2], rel[0]

    start_node = getattr(rel, "start_node", None)
    end_node = getattr(rel, "end_node", None)
    if start_node is not None and end_node is not None:
        return start_node, end_node

    start_id = getattr(rel, "start_node_id", None)
    end_id = getattr(rel, "end_node_id", None)
    if start_id is None or end_id is None:
        return None, None

    source = next(
        (node for node in nodes if getattr(node, "id", None) == start_id), None
    )
    target = next((node for node in nodes if getattr(node, "id", None) == end_id), None)
    return source, target


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
            edges[edge["id"] or f"{edge['source']}-{edge['target']}-{edge['type']}"] = (
                edge
            )
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
                key = f"{endpoints[0]}-{endpoints[1]}-{edge['type']}"
            edges[key] = edge
    return {"nodes": list(nodes.values()), "edges": list(edges.values())}
