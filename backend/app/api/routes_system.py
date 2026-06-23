from __future__ import annotations

from fastapi import APIRouter

from backend.app.services import store_provider
from backend.app.services.neo4j_graph_service import Neo4jGraphService
from sentinel_edge import collect_hardware_profile

router = APIRouter(prefix="/api/system", tags=["system"])


def _milvus_ready() -> bool:
    try:
        stores = store_provider.get_store_bundle()
        stores.events.ensure_collection()
    except Exception:
        return False
    return True


async def _neo4j_ready() -> bool:
    service = Neo4jGraphService()
    try:
        await service.graph_by_terms(["health"], limit=1)
    except Exception:
        return False
    else:
        return True
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
