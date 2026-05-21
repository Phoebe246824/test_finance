"""
Sentinel 黑名单系统
==================
黑名单管理器 + 三合一 OR 匹配过滤器。

模块:
    manager.py  — 黑名单 CRUD (load/query/append)
    filter.py   — 对 NormalizedEvent 执行人员/敏感词/事件相似度 OR 匹配
"""

from blacklist.manager import BlacklistManager
from blacklist.filter import BlacklistFilter

__all__ = ["BlacklistManager", "BlacklistFilter"]
