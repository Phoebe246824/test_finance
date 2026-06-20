"""Aggregate collected evidence into PPT-ready metrics."""

from __future__ import annotations

from copy import deepcopy
from math import ceil
import re
from statistics import mean
from typing import Any

from sentinel_edge.evidence.models import (
    CaseEvidence,
    HardwareSample,
    MetricValue,
    Source,
    to_plain_data,
)
from sentinel_edge.evidence.sidecar import merge_metric

_RISK_EXPECTATION_RE = re.compile(
    r"(?:expected[_\s-]*risk[_\s-]*level|risk[_\s-]*level|风险等级)\s*[:：=]\s*"
    r"([A-Za-z\u4e00-\u9fff_-]+)",
    flags=re.IGNORECASE,
)
_RISK_LEVEL_ALIASES = {
    "high": "high",
    "highrisk": "high",
    "high-risk": "high",
    "高": "high",
    "高风险": "high",
    "medium": "medium",
    "mid": "medium",
    "middle": "medium",
    "mediumrisk": "medium",
    "medium-risk": "medium",
    "中": "medium",
    "中风险": "medium",
    "low": "low",
    "lowrisk": "low",
    "low-risk": "low",
    "低": "low",
    "低风险": "low",
}


def percentile(values: list[float], percent: int) -> float | None:
    """Return the nearest-rank percentile value.

    Args:
        values: Numeric values to rank.
        percent: Percentile between 0 and 100.

    Returns:
        The nearest-rank percentile as a float, or None when values is empty.
    """
    if not values:
        return None

    ordered = sorted(float(value) for value in values)
    rank = ceil(len(ordered) * percent / 100)
    index = min(max(rank - 1, 0), len(ordered) - 1)
    return float(ordered[index])


def build_ppt_metrics(
    *,
    cases: list[CaseEvidence],
    hardware_samples: list[HardwareSample],
    sidecar: dict[str, Any],
) -> dict[str, Any]:
    """Build a page-keyed metrics dictionary for competition PPT material.

    Args:
        cases: Per-case runtime evidence.
        hardware_samples: Runtime hardware measurements.
        sidecar: Supplemental manually collected evidence.

    Returns:
        Plain dictionaries with serialized MetricValue payloads.
    """
    successful_cases = [case for case in cases if case.succeeded]
    elapsed_ms = [
        float(case.elapsed_ms)
        for case in successful_cases
        if case.elapsed_ms is not None
    ]
    gpu_values = _measured_numbers(hardware_samples, "gpu_util_percent")
    vram_values = _measured_numbers(hardware_samples, "vram_used_mb")
    power_values = _measured_numbers(hardware_samples, "power_watts")

    case_count = len(cases)
    successful_case_count = len(successful_cases)
    failed_case_count = case_count - successful_case_count
    completion_rate = (
        _metric(
            successful_case_count / case_count,
            "",
            Source.DERIVED,
            "cases without pipeline errors",
        )
        if case_count
        else _not_available("", "no cases collected")
    )
    pass_rate = _expected_pass_rate(cases)

    latency_mean = (
        _metric(round(mean(elapsed_ms), 2), "ms", Source.DERIVED)
        if elapsed_ms
        else _not_available("ms", "no successful case timings")
    )
    latency_p95 = (
        _metric(percentile(elapsed_ms, 95), "ms", Source.DERIVED)
        if elapsed_ms
        else _not_available("ms", "no successful case timings")
    )
    gpu_peak = _peak_metric(gpu_values, "%", "no measured GPU samples")
    vram_peak = _peak_metric(vram_values, "MB", "no measured VRAM samples")
    measured_power_average = (
        MetricValue(round(mean(power_values), 2), "W", Source.DERIVED)
        if power_values
        else MetricValue.not_available("W", "no measured power samples")
    )
    measured_power_average_metric = to_plain_data(measured_power_average)
    p10_power_average = to_plain_data(
        merge_metric(
            measured_power_average,
            _sidecar_value(sidecar, ("p10", "average_power_watts")),
            unit="W",
            label="sidecar p10.average_power_watts",
        )
    )

    return {
        "p5": {
            "finance_demo_case_count": _metric(case_count, "case", Source.DERIVED),
            "successful_case_count": _metric(
                successful_case_count,
                "case",
                Source.DERIVED,
            ),
        },
        "p8": {
            "hardware_sample_count": _metric(
                len(hardware_samples),
                "sample",
                Source.DERIVED,
            ),
            "gpu_peak_util_percent": _copy_metric(gpu_peak),
            # Keep both keys because older PPT templates referenced vram_peak_mb,
            # while newer chart specs use the explicit vram_peak_used_mb name.
            "vram_peak_mb": _copy_metric(vram_peak),
            "vram_peak_used_mb": _copy_metric(vram_peak),
            "average_power_watts": _copy_metric(measured_power_average_metric),
            "llama_cpp_offload_log": _sidecar_metric(
                sidecar,
                ("p8", "llama_cpp_offload_log"),
            ),
        },
        "p10": {
            "end_to_end_latency_mean_ms": latency_mean,
            "end_to_end_latency_p95_ms": latency_p95,
            "ttft_ms": _sidecar_metric(sidecar, ("p10", "ttft_ms"), "ms"),
            "tokens_per_second": _sidecar_metric(
                sidecar,
                ("p10", "tokens_per_second"),
                "tokens/s",
            ),
            "gpu_peak_util_percent": _copy_metric(gpu_peak),
            "vram_peak_mb": _copy_metric(vram_peak),
            "vram_peak_used_mb": _copy_metric(vram_peak),
            "average_power_watts": _copy_metric(p10_power_average),
        },
        "p11": {
            "baseline": {
                "pass_rate": _sidecar_metric(
                    sidecar,
                    ("p11", "baseline", "pass_rate"),
                    "",
                ),
                "risk_level_consistency": _sidecar_metric(
                    sidecar,
                    ("p11", "baseline", "risk_level_consistency"),
                    "",
                ),
                "average_latency_ms": _sidecar_metric(
                    sidecar,
                    ("p11", "baseline", "average_latency_ms"),
                    "ms",
                ),
                "average_power_watts": _sidecar_metric(
                    sidecar,
                    ("p11", "baseline", "average_power_watts"),
                    "W",
                ),
            },
            "optimized": {
                "pass_rate": pass_rate,
                "completion_rate": _copy_metric(completion_rate),
                "average_latency_ms": _copy_metric(latency_mean),
                "average_power_watts": _copy_metric(measured_power_average_metric),
                "risk_level_consistency": _sidecar_metric(
                    sidecar,
                    ("p11", "optimized", "risk_level_consistency"),
                    "",
                ),
            },
        },
        "p12": {
            "privacy_evidence": _sidecar_metric(
                sidecar,
                ("p12", "privacy_evidence"),
            ),
            "review_material_path": _sidecar_metric(
                sidecar,
                ("p12", "review_material_path"),
            ),
            "manual_review_acceptance_rate": _sidecar_metric(
                sidecar,
                ("p12", "manual_review_acceptance_rate"),
                "%",
            ),
        },
        "p13": {
            "case_count": _metric(case_count, "case", Source.DERIVED),
            "successful_case_count": _metric(
                successful_case_count,
                "case",
                Source.DERIVED,
            ),
            "failed_case_count": _metric(
                failed_case_count,
                "case",
                Source.DERIVED,
            ),
        },
        "p14": {
            "business_value": _sidecar_metric(
                sidecar,
                ("p14", "business_value"),
            ),
            "manual_investigation_time_minutes": _sidecar_metric(
                sidecar,
                ("p14", "manual_investigation_time_minutes"),
                "min",
            ),
            "sentinel_investigation_time_minutes": _sidecar_metric(
                sidecar,
                ("p14", "sentinel_investigation_time_minutes"),
                "min",
            ),
            "portfolio_risk_discovery_rate": _sidecar_metric(
                sidecar,
                ("p14", "portfolio_risk_discovery_rate"),
                "%",
            ),
        },
    }


def _metric(
    value: Any,
    unit: str = "",
    source: Source = Source.MEASURED,
    note: str = "",
) -> dict[str, Any]:
    return to_plain_data(MetricValue(value=value, unit=unit, source=source, note=note))


def _not_available(unit: str = "", note: str = "") -> dict[str, Any]:
    return to_plain_data(MetricValue.not_available(unit=unit, note=note))


def _copy_metric(metric: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(metric)


def _peak_metric(values: list[float], unit: str, missing_note: str) -> dict[str, Any]:
    if not values:
        return _not_available(unit, missing_note)
    return _metric(max(values), unit, Source.DERIVED)


def _expected_pass_rate(cases: list[CaseEvidence]) -> dict[str, Any]:
    checkable: list[tuple[CaseEvidence, set[str]]] = []
    for case in cases:
        expected_levels = _expected_risk_levels(case)
        if expected_levels:
            checkable.append((case, expected_levels))

    if not checkable:
        return _not_available("", "no checkable expected risk levels")

    passed = sum(
        1
        for case, expected_levels in checkable
        if case.error is None
        and _normalize_risk_level(case.risk_level) in expected_levels
    )
    note = f"risk_level expectation matches {passed}/{len(checkable)} checkable cases"
    return _metric(passed / len(checkable), "", Source.DERIVED, note)


def _expected_risk_levels(case: CaseEvidence) -> set[str]:
    levels: set[str] = set()
    for expectation in case.expected:
        match = _RISK_EXPECTATION_RE.search(str(expectation))
        if not match:
            continue
        normalized = _normalize_risk_level(match.group(1))
        if normalized is not None:
            levels.add(normalized)
    return levels


def _normalize_risk_level(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower().replace(" ", "").replace("_", "-")
    return _RISK_LEVEL_ALIASES.get(normalized)


def _measured_numbers(samples: list[HardwareSample], attr: str) -> list[float]:
    values: list[float] = []
    for sample in samples:
        metric = getattr(sample, attr)
        if metric.source not in {Source.MEASURED, Source.MEASURED.value}:
            continue
        if metric.value is None:
            continue
        try:
            values.append(float(metric.value))
        except (TypeError, ValueError):
            continue
    return values


def _sidecar_metric(
    sidecar: dict[str, Any],
    path: tuple[str, ...],
    unit: str = "",
) -> dict[str, Any]:
    label = f"sidecar {'.'.join(path)}"
    missing_note = f"sidecar missing {'.'.join(path)}"
    current = _sidecar_value(sidecar, path)
    if current is None:
        return _not_available(unit, missing_note)

    if isinstance(current, dict) and "value" not in current and "path" not in current:
        return _not_available(
            current.get("unit", unit),
            f"{label} missing value",
        )

    return to_plain_data(
        merge_metric(
            MetricValue.not_available(unit, missing_note),
            current,
            unit=unit,
            label=label,
        )
    )


def _sidecar_value(sidecar: dict[str, Any], path: tuple[str, ...]) -> Any | None:
    current: Any = sidecar
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current
