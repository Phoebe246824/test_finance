"""
Sentinel Redis KV 暂存系统
========================
人员 → 事件列表的 CRUD + TTL 管理。

方案 A: 一人一链表
    KEY:   person:<id_number>
    VALUE: JSON 数组 [{event1}, {event2}, ...]
    TTL:   可配置，默认 90 天
"""

from kvstore.redis_store import EventKVStore

__all__ = ["EventKVStore"]
