"""Load supplemental PPT evidence and merge manual metrics."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from sentinel_edge.evidence.models import MetricValue, Source


def load_sidecar(path: str | Path | None) -> dict[str, Any]:
    """Load supplemental evidence from JSON or YAML sidecar files.

    Args:
        path: Optional path to the sidecar file.

    Returns:
        Loaded sidecar mapping with provenance metadata, or an empty mapping.

    Raises:
        FileNotFoundError: If the configured sidecar path does not exist.
        ValueError: If the sidecar top-level value is not a mapping.
    """
    if path is None:
        return {}

    sidecar_path = Path(path)
    if not sidecar_path.exists():
        raise FileNotFoundError(str(sidecar_path))

    raw_text = sidecar_path.read_text(encoding="utf-8")
    if not raw_text.strip():
        return {}

    try:
        if sidecar_path.suffix.lower() == ".json":
            loaded = json.loads(raw_text)
        else:
            loaded = yaml.safe_load(raw_text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"{sidecar_path} could not be parsed: {exc}") from exc

    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError(f"{sidecar_path} must contain a mapping")

    sidecar = dict(loaded)
    sidecar["_meta"] = {
        "path": str(sidecar_path),
        "loaded_at": datetime.now().isoformat(timespec="seconds"),
    }
    return sidecar


def merge_metric(
    measured: MetricValue,
    sidecar_value: dict[str, Any] | Any | None,
    *,
    unit: str = "",
) -> MetricValue:
    """Merge a measured metric with supplemental sidecar evidence.

    Args:
        measured: Runtime-measured or derived metric.
        sidecar_value: Manual sidecar value or metric dictionary.
        unit: Preferred unit for the sidecar value.

    Returns:
        The measured metric unless it is unavailable or explicitly overridden.
    """
    if sidecar_value is None:
        return measured

    note = ""
    override = False
    if isinstance(sidecar_value, dict):
        value = sidecar_value.get("value")
        note = sidecar_value.get("note", "")
        override_value = sidecar_value.get("override", False)
        if not isinstance(override_value, bool):
            raise ValueError("override must be a boolean")
        override = override_value is True
    else:
        value = sidecar_value

    if value is None:
        return _merge_null_sidecar(measured, unit=unit, note=note)

    if measured.source not in {Source.NOT_AVAILABLE, Source.NOT_AVAILABLE.value}:
        if not override:
            return measured

    return MetricValue(
        value=value,
        unit=unit or measured.unit,
        source=Source.SIDECAR,
        note=note,
    )


def _merge_null_sidecar(measured: MetricValue, *, unit: str, note: str) -> MetricValue:
    if (
        measured.source not in {Source.NOT_AVAILABLE, Source.NOT_AVAILABLE.value}
        and measured.value is not None
    ):
        return measured

    detail = "sidecar value is null"
    if note:
        detail = f"{detail}: {note}"
    return MetricValue.not_available(unit=unit or measured.unit, note=detail)
