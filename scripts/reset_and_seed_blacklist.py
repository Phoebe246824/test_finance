"""清空黑名单 Redis DB 并重新写入测试种子数据。"""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from redis.asyncio import Redis

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from blacklist.store import BlacklistStore

PERSON_SEEDS = [
    "P05",
]

KEYWORD_SEEDS = [
    "制裁",
    "爆炸",
    "裁员",
    "暴雷",
    "洗钱",
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
]


async def main() -> None:
    load_dotenv(dotenv_path=ROOT / ".env")

    host = os.getenv("REDIS_HOST", "localhost")
    port = int(os.getenv("REDIS_PORT", "6379"))
    password = os.getenv("REDIS_PASSWORD") or None
    blacklist_db = int(os.getenv("BLACKLIST_REDIS_DB", "1"))
    stash_db = int(os.getenv("REDIS_DB", "0"))

    redis = Redis(host=host, port=port, password=password, db=blacklist_db)
    stash_redis = Redis(host=host, port=port, password=password, db=stash_db)
    store = BlacklistStore(redis)

    try:
        before_blacklist = await redis.dbsize()
        await redis.flushdb()
        before_stash = await stash_redis.dbsize()
        await stash_redis.flushdb()

        for person_id in PERSON_SEEDS:
            await store.append_person(person_id)

        for keyword in KEYWORD_SEEDS:
            await store.append_keyword(keyword)

        for event_id, summary in EVENT_SEEDS:
            await store.append_event(event_id, summary)

        person_stats = await store.get_person_stats()
        keyword_stats = await store.get_keyword_stats()
        event_count = await store.get_event_count()

        print(f"Reset and seeded Redis:")
        print(f"  Blacklist DB ({blacklist_db}): cleared {before_blacklist} keys, seeded {len(PERSON_SEEDS)} persons, {len(KEYWORD_SEEDS)} keywords, {len(EVENT_SEEDS)} events")
        print(f"  Stash DB ({stash_db}): cleared {before_stash} keys")
        print(f"  Persons : {sorted(person_stats.keys())}")
        print(f"  Keywords count: {len(keyword_stats)}")
        print(f"  Events  : {event_count}")
    finally:
        await redis.aclose()
        await stash_redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
