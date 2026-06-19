"""Serializable evidence models for competition PPT generation."""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from enum import StrEnum
from typing import Any


class Source(StrEnum):
    MEASURED = "measured"
    DERIVED = "derived"
    SIDECAR = "sidecar"
    NOT_AVAILABLE = "not_available"


@dataclass(slots=True)
class MetricValue:
    value: Any | None
    unit: str = ""
    source: Source = Source.MEASURED
    note: str = ""

    @classmethod
    def not_available(cls, unit: str = "", note: str = "") -> "MetricValue":
        return cls(
            value=None,
            unit=unit,
            source=Source.NOT_AVAILABLE,
            note=note,
        )


@dataclass(slots=True)
class CaseEvidence:
    case_id: str
    title: str
    event_id: str | None = None
    status: str = "unknown"
    risk_level: str | None = None
    risk_score: float | None = None
    elapsed_ms: float | None = None
    error: str | None = None
    case_log_path: str | None = None
    expected: list[str] = field(default_factory=list)

    @property
    def succeeded(self) -> bool:
        return self.error is None


@dataclass(slots=True)
class HardwareSample:
    timestamp: str
    gpu_util_percent: MetricValue = field(
        default_factory=lambda: MetricValue.not_available("%")
    )
    vram_used_mb: MetricValue = field(
        default_factory=lambda: MetricValue.not_available("MB")
    )
    power_watts: MetricValue = field(
        default_factory=lambda: MetricValue.not_available("W")
    )
    raw_output: str = ""


@dataclass(slots=True)
class EvidencePack:
    project: str
    generated_at: str
    pipeline_executed: bool
    hardware_profile: dict[str, Any]
    cases: list[CaseEvidence] = field(default_factory=list)
    hardware_samples: list[HardwareSample] = field(default_factory=list)
    sidecar: dict[str, Any] = field(default_factory=dict)
    ppt_metrics: dict[str, Any] = field(default_factory=dict)


def to_plain_data(value: Any) -> Any:
    if isinstance(value, Source):
        return value.value

    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: to_plain_data(getattr(value, item.name))
            for item in fields(value)
        }

    if isinstance(value, dict):
        return {
            to_plain_data(item_key): to_plain_data(item_value)
            for item_key, item_value in value.items()
        }

    if isinstance(value, list):
        return [to_plain_data(item) for item in value]

    return value
