"""
Sentinel 黑名单 + KV 暂存系统 — 单元测试
======================================
测试范围:
    - utils/text.py: extract_subject_id_numbers()
    - blacklist/manager.py: BlacklistManager CRUD
    - blacklist/filter.py: BlacklistFilter 三合一 OR 匹配
    - kvstore/redis_store.py: EventKVStore 暂存/取回/删除
"""
