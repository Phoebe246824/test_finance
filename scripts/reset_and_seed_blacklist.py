"""重置 Neo4j、Redis、Milvus 状态并重新写入黑名单测试种子数据。"""

import asyncio
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from redis.asyncio import Redis

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from blacklist.store import BlacklistStore  # noqa: E402

# P05 保留旧测试；P105 用于金融黑名单命中测试。
PERSON_SEEDS = [
    "P05",
    "P105",
]

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
    "刀具",
    "可燃液体",
    "危险化学品",
]

EVENT_SEEDS = [
    (
        "E-HIGH-RISK-001",
        "某人员携带刀具与可燃液体进入地下停车场并与他人发生冲突，存在严重公共安全风险。",
    ),
    (
        "E-HIGH-RISK-002",
        "仓库内发现大量危险化学品和疑似爆炸装置材料，现场情况紧急，警方和消防已介入。",
    ),
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
    """Delete all nodes and relationships from the configured Neo4j database."""
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
            if record is None:
                return 0
            return int(record["node_count"])
    finally:
        await driver.close()


def reset_milvus_collection(
    *,
    uri: str,
    token: str,
    collection_name: str,
    client_factory: Callable[..., Any] | None = None,
) -> bool:
    """Drop the Milvus stash collection if it exists."""
    if client_factory is None:
        from pymilvus import MilvusClient

        client_factory = MilvusClient

    client = client_factory(uri=uri, token=token or None)
    try:
        if not client.has_collection(collection_name):
            return False
        client.drop_collection(collection_name)
        return True
    finally:
        close = getattr(client, "close", None)
        if close is not None:
            close()


async def main() -> None:
    load_dotenv(dotenv_path=ROOT / ".env")

    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "password")
    neo4j_database = os.getenv("NEO4J_DATABASE", "neo4j")

    host = os.getenv("REDIS_HOST", "localhost")
    port = int(os.getenv("REDIS_PORT", "6379"))
    password = os.getenv("REDIS_PASSWORD") or None
    blacklist_db = int(os.getenv("BLACKLIST_REDIS_DB", "1"))

    milvus_uri = os.getenv("MILVUS_URI", "http://localhost:19530")
    milvus_token = os.getenv("MILVUS_TOKEN", "")
    milvus_collection = os.getenv("MILVUS_STASH_COLLECTION", "stashed_events")

    deleted_neo4j_nodes = await reset_neo4j_graph(
        uri=neo4j_uri,
        user=neo4j_user,
        password=neo4j_password,
        database=neo4j_database,
    )
    dropped_milvus_collection = reset_milvus_collection(
        uri=milvus_uri,
        token=milvus_token,
        collection_name=milvus_collection,
    )

    redis = Redis(host=host, port=port, password=password, db=blacklist_db)
    store = BlacklistStore(redis)

    try:
        before_blacklist = await redis.dbsize()
        await redis.flushdb()

        for person_id in PERSON_SEEDS:
            await store.append_person(person_id)

        for keyword in KEYWORD_SEEDS:
            await store.append_keyword(keyword)

        for event_id, summary in EVENT_SEEDS:
            await store.append_event(event_id, summary)

        person_stats = await store.get_person_stats()
        keyword_stats = await store.get_keyword_stats()
        event_count = await store.get_event_count()

        print("Reset databases and seeded blacklist Redis:")
        print(f"  Neo4j ({neo4j_database}): deleted {deleted_neo4j_nodes} graph nodes")
        print(
            f"  Blacklist DB ({blacklist_db}): cleared {before_blacklist} keys, seeded {len(PERSON_SEEDS)} persons, {len(KEYWORD_SEEDS)} keywords, {len(EVENT_SEEDS)} events"
        )
        milvus_status = "dropped" if dropped_milvus_collection else "not found"
        print(f"  Milvus stash ({milvus_collection}): collection {milvus_status}")
        print(f"  Persons : {sorted(person_stats.keys())}")
        print(f"  Keywords count: {len(keyword_stats)}")
        print(f"  Events  : {event_count}")
    finally:
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
