from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from threading import RLock
from typing import Any


@dataclass(slots=True)
class RuntimeState:
    audit_logs: list[dict[str, Any]] = field(default_factory=list)
    settings: dict[str, Any] | None = None
    settings_updated_at: str = ""
    risk_rules: dict[str, Any] | None = None
    risk_rules_updated_at: str = ""
    tasks: dict[str, dict[str, Any]] = field(default_factory=dict)
    _next_audit_id: int = 1
    _lock: RLock = field(default_factory=RLock)

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


runtime_state = RuntimeState()
