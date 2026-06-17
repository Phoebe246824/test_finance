"""Simple benchmark recording utilities for competition evidence."""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterator


@dataclass
class BenchmarkRecord:
    name: str
    started_at: str
    elapsed_ms: float
    metadata: dict = field(default_factory=dict)


class BenchmarkRecorder:
    """Collects stage timings and writes a compact JSON report."""

    def __init__(self) -> None:
        self.records: list[BenchmarkRecord] = []

    @contextmanager
    def span(self, name: str, **metadata) -> Iterator[None]:
        started_at = datetime.now().isoformat(timespec="seconds")
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            self.records.append(
                BenchmarkRecord(
                    name=name,
                    started_at=started_at,
                    elapsed_ms=elapsed_ms,
                    metadata={k: v for k, v in metadata.items() if v is not None},
                )
            )

    def to_dict(self) -> dict:
        total_ms = round(sum(record.elapsed_ms for record in self.records), 2)
        return {
            "total_measured_ms": total_ms,
            "records": [asdict(record) for record in self.records],
        }

    def write_json(self, path: str | Path, extra: dict | None = None) -> Path:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = self.to_dict()
        if extra:
            payload.update(extra)
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return output_path
