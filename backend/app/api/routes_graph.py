from __future__ import annotations

import re

from fastapi import APIRouter, Query

from backend.app.repositories.events import EventRepository
from backend.app.services.neo4j_graph_service import Neo4jGraphService

router = APIRouter(prefix="/api/graph", tags=["graph"])

ENTITY_PATTERN = re.compile(r"【([A-Za-z]\d+)#\s*([^】]+)】")


def _node_type(entity_id: str) -> str:
    prefix = entity_id[:1].upper()
    return {
        "P": "Customer",
        "A": "Account",
        "C": "Merchant",
        "D": "Device",
        "M": "Merchant",
        "L": "Location",
    }.get(prefix, "Entity")


def _add_node(nodes_by_id: dict[str, dict], node: dict) -> None:
    if node["id"] not in nodes_by_id:
        nodes_by_id[node["id"]] = node


def _fallback_event_graph(event: dict) -> dict:
    event_id = event["event_id"]
    nodes_by_id: dict[str, dict] = {}
    _add_node(
        nodes_by_id,
        {
            "id": event_id,
            "label": event.get("title") or event_id,
            "type": "RiskEvent",
            "risk_level": event.get("risk_level"),
            "properties": event,
        },
    )
    edges = []
    seen_edges: set[tuple[str, str, str]] = set()

    for entity_id, label in ENTITY_PATTERN.findall(event.get("raw_content") or ""):
        entity_id = entity_id.strip()
        label = label.strip() or entity_id
        _add_node(
            nodes_by_id,
            {
                "id": entity_id,
                "label": label,
                "type": _node_type(entity_id),
                "risk_level": event.get("risk_level"),
                "properties": {"id_number": entity_id, "name": label},
            },
        )
        edge_key = (entity_id, event_id, "出现在事件中")
        if edge_key not in seen_edges:
            edges.append(
                {
                    "id": "-".join(edge_key),
                    "source": edge_key[0],
                    "target": edge_key[1],
                    "label": edge_key[2],
                    "type": "APPEARS_IN",
                    "properties": {"source": "text_fallback"},
                }
            )
            seen_edges.add(edge_key)

    for person_id in event.get("matched_persons") or []:
        _add_node(
            nodes_by_id,
            {
                "id": person_id,
                "label": person_id,
                "type": "Customer",
                "risk_level": event.get("risk_level"),
                "properties": {"id_number": person_id},
            },
        )
        edge_key = (person_id, event_id, "命中黑名单")
        if edge_key not in seen_edges:
            edges.append(
                {
                    "id": "-".join(edge_key),
                    "source": edge_key[0],
                    "target": edge_key[1],
                    "label": edge_key[2],
                    "type": "BLACKLIST_HIT",
                    "properties": {"source": "blacklist"},
                }
            )
            seen_edges.add(edge_key)

    return {"nodes": list(nodes_by_id.values()), "edges": edges, "source": "fallback"}


async def _try_neo4j_terms(terms: list[str], limit: int = 100) -> dict:
    service = Neo4jGraphService()
    try:
        graph = await service.graph_by_terms(terms, limit=limit)
        graph["source"] = "neo4j"
        return graph
    finally:
        await service.close()


@router.get("/events/{event_id}")
async def event_graph(event_id: str) -> dict:
    event = EventRepository().get_event(event_id)
    if not event:
        return {"nodes": [], "edges": []}

    terms = [event_id]
    terms.extend(match[0] for match in ENTITY_PATTERN.findall(event.get("raw_content") or ""))
    terms.extend(event.get("matched_persons") or [])

    try:
        graph = await _try_neo4j_terms(terms)
        if graph["nodes"]:
            return graph
    except Exception:
        pass

    return _fallback_event_graph(event)


@router.get("/persons")
async def person_graph(q: str = Query(..., min_length=1), limit: int = 100) -> dict:
    service = Neo4jGraphService()
    try:
        graph = await service.search_person(q, limit=limit)
        graph["source"] = "neo4j"
        return graph
    finally:
        await service.close()


@router.get("/nodes/{node_id}/expand")
async def expand_node(node_id: str, limit: int = 80) -> dict:
    service = Neo4jGraphService()
    try:
        graph = await service.expand_node(node_id, limit=limit)
        graph["source"] = "neo4j"
        return graph
    finally:
        await service.close()
