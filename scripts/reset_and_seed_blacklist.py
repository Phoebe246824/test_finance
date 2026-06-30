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

from blacklist.milvus_client import MilvusConfig, create_milvus_client  # noqa: E402
from blacklist.stores.event_samples_store import EventSamplesStore  # noqa: E402
from blacklist.stores.factory import (  # noqa: E402
    create_embedding_fn,
    milvus_collection_names,
)
from blacklist.stores.keywords_store import KeywordsStore  # noqa: E402
from blacklist.stores.persons_store import PersonsStore  # noqa: E402

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
    (
        "E-FIN-AML-001",
        "客户在短时间内向多个新开户账户转出接近阈值资金，随后资金归集至虚拟币平台，疑似分拆交易与洗钱。",
    ),
    (
        "E-FIN-FRAUD-001",
        "客户向曾被投诉的涉诈账户转账虚拟币保证金，交易设备异常且登录地点偏离常驻城市。",
    ),
    (
        "E-FIN-DEVICE-001",
        "客户账户在非常用设备和异常地理位置登录后立即发起大额转账，疑似账户盗用或电诈转账。",
    ),
    (
        "E-FIN-MULE-001",
        "多个客户向同一新开户账户集中转账，资金随后快速出金至外部支付通道，疑似跑分或资金归集账户。",
    ),
]


async def reset_neo4j_graph(
    *,
    uri: str,
    user: str,
    password: str,
    database: str,
    driver_factory: Callable[..., Any] | None = None,
) -> int:
    if driver_factory is None:
        from neo4j import AsyncGraphDatabase

        driver_factory = AsyncGraphDatabase.driver

    driver = driver_factory(uri, auth=(user, password))
    try:
        async with driver.session(database=database) as session:
            result = await session.run(
                """
                MATCH (node)
                WITH collect(node) AS nodes, count(node) AS node_count
                FOREACH (node IN nodes | DETACH DELETE node)
                RETURN node_count
                """
            )
            record = await result.single()
            return 0 if record is None else int(record["node_count"])
    finally:
        await driver.close()


def reset_milvus_collections(
    client: Any,
    collections: tuple[str, ...] | None = None,
) -> list[str]:
    collection_names = milvus_collection_names() if collections is None else collections
    dropped: list[str] = []
    for collection_name in sorted(collection_names):
        if client.has_collection(collection_name):
            client.drop_collection(collection_name)
            dropped.append(collection_name)
    return dropped


async def seed_blacklist_stores(
    client: Any,
    embedding_fn: Any,
    embedding_dim: int = 1024,
) -> dict[str, int]:
    persons = PersonsStore(client, embedding_dim=embedding_dim)
    keywords = KeywordsStore(client, embedding_dim=embedding_dim)
    samples = EventSamplesStore(
        client,
        embedding_fn=embedding_fn,
        embedding_dim=embedding_dim,
    )
    now = persons.now_iso()
    persons.upsert_rows(
        [
            {
                "person_id": person_id.upper(),
                "summary": "",
                "description": "",
                "hit_count": 1,
                "enabled": True,
                "created_at": now,
                "updated_at": now,
            }
            for person_id in PERSON_SEEDS
        ]
    )
    keywords.upsert_rows(
        [
            {
                "keyword_id": keywords.keyword_id(keyword),
                "keyword": keyword,
                "summary": "",
                "description": "",
                "hit_count": 1,
                "enabled": True,
                "created_at": now,
                "updated_at": now,
            }
            for keyword in KEYWORD_SEEDS
        ]
    )
    samples.upsert_rows(
        [
            {
                "sample_id": event_id,
                "summary": summary,
                "description": summary,
                "embedding": await samples.resolve_embedding(embedding_fn, summary),
                "enabled": True,
                "created_at": now,
                "updated_at": now,
            }
            for event_id, summary in EVENT_SEEDS
        ]
    )
    return {
        "persons": len(PERSON_SEEDS),
        "keywords": len(KEYWORD_SEEDS),
        "event_samples": len(EVENT_SEEDS),
    }


async def main() -> None:
    load_dotenv(dotenv_path=ROOT / ".env")
    milvus_config = {
        "stash_collection": os.getenv("MILVUS_STASH_COLLECTION") or "stashed_events",
    }
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
    try:
        dropped = reset_milvus_collections(
            client,
            collections=milvus_collection_names({"milvus": milvus_config}),
        )
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
    finally:
        close = getattr(client, "close", None)
        if close is not None:
            close()


if __name__ == "__main__":
    asyncio.run(main())
