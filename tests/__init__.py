"""
Sentinel 黑名单 + Milvus 暂存系统 — 单元测试
=========================================
测试范围:
    - utils/text.py: extract_subject_id_numbers()
    - blacklist/store.py: BlacklistStore 黑名单 CRUD
    - blacklist/filter.py: BlacklistFilter 三合一 OR 匹配
    - blacklist/milvus_stash.py: Milvus 暂存/回捞/标记已构图
"""
