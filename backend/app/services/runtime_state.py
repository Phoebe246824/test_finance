from __future__ import annotations

import asyncio
import logging
import time
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from threading import RLock
from typing import Any

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = frozenset({"success", "failed"})
_TASK_TTL_SECONDS = 3600
_STUCK_TASK_TIMEOUT = 600


@dataclass(slots=True)
class RuntimeState:
    """Global runtime state for tasks, audit logs, and settings.

    Note: asyncio.Queue is used for SSE subscriber notification. This is safe
    because all callers (FastAPI request handlers, BackgroundTasks) run on the
    same event loop thread. Do not call update_task/subscribe_task from
    different threads or event loops.
    """
    audit_logs: list[dict[str, Any]] = field(default_factory=list)
    settings: dict[str, Any] | None = None
    settings_updated_at: str = ""
    risk_rules: dict[str, Any] | None = None
    risk_rules_updated_at: str = ""
    tasks: dict[str, dict[str, Any]] = field(default_factory=dict)
    _next_audit_id: int = 1
    _lock: RLock = field(default_factory=RLock)
    _subscribers: dict[str, list[asyncio.Queue[dict[str, Any] | None]]] = field(
        default_factory=dict
    )
    _task_finished_at: dict[str, float] = field(default_factory=dict)

    def now_text(self) -> str:
        return datetime.now().isoformat(timespec="seconds")

    def append_audit_log(self, row: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            stored = {**deepcopy(row), "id": self._next_audit_id}
            self._next_audit_id += 1
            self.audit_logs.append(stored)
            return deepcopy(stored)

    def list_audit_logs(self, *, page: int, page_size: int) -> dict[str, Any]:
        with self._lock:
            rows = sorted(
                self.audit_logs,
                key=lambda item: (str(item.get("created_at") or ""), int(item.get("id") or 0)),
                reverse=True,
            )
            offset = (page - 1) * page_size
            return {
                "total": len(rows),
                "page": page,
                "page_size": page_size,
                "items": deepcopy(rows[offset : offset + page_size]),
            }

    def load_settings(self, default_value: dict[str, Any]) -> tuple[dict[str, Any], str]:
        with self._lock:
            return deepcopy(self.settings or default_value), self.settings_updated_at

    def save_settings(self, value: dict[str, Any]) -> tuple[dict[str, Any], str]:
        with self._lock:
            self.settings = deepcopy(value)
            self.settings_updated_at = self.now_text()
            return deepcopy(self.settings), self.settings_updated_at

    def load_risk_rules(self, default_value: dict[str, Any]) -> tuple[dict[str, Any], str]:
        with self._lock:
            return deepcopy(self.risk_rules or default_value), self.risk_rules_updated_at

    def save_risk_rules(self, value: dict[str, Any]) -> tuple[dict[str, Any], str]:
        with self._lock:
            self.risk_rules = deepcopy(value)
            self.risk_rules_updated_at = self.now_text()
            return deepcopy(self.risk_rules), self.risk_rules_updated_at

    def create_task(self, task_id: str, row: dict[str, Any]) -> None:
        with self._lock:
            self.tasks[task_id] = deepcopy(row)
            if task_id not in self._subscribers:
                self._subscribers[task_id] = []
            self._task_finished_at.pop(task_id, None)

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            task = self.tasks.get(task_id)
            return deepcopy(task) if task is not None else None

    def update_task(self, task_id: str, values: dict[str, Any]) -> None:
        with self._lock:
            task = self.tasks.get(task_id)
            if task is None:
                return
            task.update(deepcopy(values))
            snapshot = deepcopy(task)
            if task.get("status") in _TERMINAL_STATUSES:
                self._task_finished_at[task_id] = time.monotonic()
            for q in self._subscribers.get(task_id, ()):
                try:
                    q.put_nowait(snapshot)
                except asyncio.QueueFull:
                    try:
                        q.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                    q.put_nowait(snapshot)

    def subscribe_task(self, task_id: str) -> asyncio.Queue[dict[str, Any] | None]:
        with self._lock:
            q: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=1)
            self._subscribers.setdefault(task_id, []).append(q)
            task = self.tasks.get(task_id)
            if task is not None:
                try:
                    q.put_nowait(deepcopy(task))
                except asyncio.QueueFull:
                    pass
            return q

    def unsubscribe_task(self, task_id: str, q: asyncio.Queue[dict[str, Any] | None]) -> None:
        with self._lock:
            subs = self._subscribers.get(task_id)
            if subs is not None:
                try:
                    subs.remove(q)
                except ValueError:
                    pass
                if not subs:
                    self._subscribers.pop(task_id, None)

    def cleanup_stale_tasks(self, ttl: float = _TASK_TTL_SECONDS) -> int:
        now = time.monotonic()
        now_epoch = time.time()
        removed: list[str] = []
        notify: list[tuple[str, asyncio.Queue[dict[str, Any] | None]]] = []
        with self._lock:
            for tid, finished in list(self._task_finished_at.items()):
                if now - finished > ttl:
                    removed.append(tid)
            for tid, task in list(self.tasks.items()):
                if task.get("status") not in _TERMINAL_STATUSES:
                    created_at = task.get("created_at", "")
                    if created_at:
                        try:
                            created_ts = datetime.fromisoformat(created_at).timestamp()
                            if now_epoch - created_ts > _STUCK_TASK_TIMEOUT:
                                removed.append(tid)
                        except (ValueError, TypeError):
                            pass
            removed = list(dict.fromkeys(removed))
            for tid in removed:
                for q in self._subscribers.pop(tid, ()):
                    notify.append((tid, q))
                self.tasks.pop(tid, None)
                self._task_finished_at.pop(tid, None)
        for _tid, q in notify:
            try:
                q.put_nowait(None)
            except asyncio.QueueFull:
                pass
        if removed:
            logger.info("Cleaned up %d stale tasks: %s", len(removed), removed)
        return len(removed)


runtime_state = RuntimeState()
