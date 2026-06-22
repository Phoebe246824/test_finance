"""
Sentinel 黑名单系统
==================
统一存储层 + 三合一 OR 匹配过滤器。

模块:
    sqlite_store.py — 默认 SQLite 黑名单 CRUD
    sqlite_stash.py — 默认 SQLite 事件暂存/回捞
    runtime_storage.py — 运行时存储后端选择
    store.py — 可选 Redis 黑名单 CRUD
    milvus_stash.py — 可选 Milvus 事件暂存/回捞
    filter.py — 对 NormalizedEvent 执行人员/敏感词/事件相似度 OR 匹配
"""

from blacklist.filter import BlacklistFilter
from blacklist.milvus_stash import MilvusStashStore
from blacklist.runtime_storage import (
    StashStore,
    create_blacklist_store,
    create_stash_store,
)
from blacklist.sqlite_stash import SQLiteStashStore
from blacklist.sqlite_store import SQLiteBlacklistStore
from blacklist.store import BlacklistStore

__all__ = [
    "BlacklistStore",
    "BlacklistFilter",
    "MilvusStashStore",
    "SQLiteBlacklistStore",
    "SQLiteStashStore",
    "StashStore",
    "create_blacklist_store",
    "create_stash_store",
]
