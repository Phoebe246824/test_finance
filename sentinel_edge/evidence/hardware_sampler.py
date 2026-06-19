"""Best-effort ROCm hardware sampling for PPT evidence."""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Callable
from datetime import datetime

from sentinel_edge.evidence.models import HardwareSample, MetricValue

CommandRunner = Callable[[list[str]], str]

_COMMAND = [
    "rocm-smi",
    "--showuse",
    "--showmemuse",
    "--showpower",
    "--showmeminfo",
    "vram",
]
_MISSING_NOTE = "rocm-smi output missing or unsupported"
_NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")
_BYTES_PER_MEGABYTE = 1024 * 1024


def _default_runner(command: list[str]) -> str:
    """Run a hardware sampling command and return combined terminal output.

    Args:
        command: Executable and arguments to run.

    Returns:
        Joined stdout/stderr text, or an empty string when the binary is not
        available or the command cannot complete.
    """
    if not command or shutil.which(command[0]) is None:
        return ""

    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=5.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""

    return "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
    ).strip()


def parse_rocm_smi_output(output: str) -> dict[str, float | None]:
    """Extract GPU utilization, VRAM MB, and package power from rocm-smi text.

    Args:
        output: Raw rocm-smi stdout/stderr text.

    Returns:
        Parsed metric values. Unsupported or missing metrics are returned as
        ``None``. VRAM percentage fields are intentionally ignored because they
        are not usable as megabyte measurements.
    """
    parsed: dict[str, float | None] = {
        "gpu_util_percent": None,
        "vram_used_mb": None,
        "power_watts": None,
    }

    for line in output.splitlines():
        normalized = " ".join(line.strip().lower().split())
        if not normalized:
            continue

        if parsed["gpu_util_percent"] is None and _is_gpu_use_line(normalized):
            parsed["gpu_util_percent"] = _metric_value(line, "%")
            continue

        if parsed["vram_used_mb"] is None and _is_vram_mb_line(normalized):
            parsed["vram_used_mb"] = _metric_value(line, "mb")
            continue

        if parsed["vram_used_mb"] is None and _is_vram_bytes_line(normalized):
            parsed["vram_used_mb"] = _vram_bytes_to_megabytes(line)
            continue

        if parsed["power_watts"] is None and _is_power_watts_line(normalized):
            parsed["power_watts"] = _metric_value(line, "w")

    return parsed


def sample_once(command_runner: CommandRunner = _default_runner) -> HardwareSample:
    """Collect one ROCm hardware sample for competition evidence.

    Args:
        command_runner: Injectable runner used by tests or alternate command
            execution layers.

    Returns:
        Hardware sample with measured metrics where parsing succeeded and
        explicit ``not_available`` metrics otherwise.
    """
    raw_output = command_runner(_COMMAND)
    parsed = parse_rocm_smi_output(raw_output)

    return HardwareSample(
        timestamp=datetime.now().isoformat(timespec="seconds"),
        gpu_util_percent=_metric_or_not_available(
            parsed["gpu_util_percent"],
            "%",
        ),
        vram_used_mb=_metric_or_not_available(parsed["vram_used_mb"], "MB"),
        power_watts=_metric_or_not_available(parsed["power_watts"], "W"),
        raw_output=raw_output,
    )


def _metric_or_not_available(value: float | None, unit: str) -> MetricValue:
    if value is None:
        return MetricValue.not_available(unit, _MISSING_NOTE)
    return MetricValue(value=value, unit=unit)


def _last_number(text: str) -> float | None:
    matches = _NUMBER_RE.findall(text)
    if not matches:
        return None
    return float(matches[-1])


def _metric_value(line: str, unit: str) -> float | None:
    if ":" in line:
        value = _last_number(line.rsplit(":", maxsplit=1)[-1])
        if value is not None:
            return value

    return _number_adjacent_to_unit(line, unit)


def _number_adjacent_to_unit(line: str, unit: str) -> float | None:
    escaped_unit = re.escape(unit)
    unit_boundary = r"\b" if unit.isalpha() else ""
    patterns = (
        rf"([-+]?\d+(?:\.\d+)?)\s*{escaped_unit}{unit_boundary}",
        rf"{escaped_unit}\)?\s*:?\s*([-+]?\d+(?:\.\d+)?)",
    )
    for pattern in patterns:
        match = re.search(pattern, line, flags=re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def _vram_bytes_to_megabytes(line: str) -> float | None:
    value = _metric_value(line, "b")
    if value is None:
        return None
    return value / _BYTES_PER_MEGABYTE


def _is_gpu_use_line(line: str) -> bool:
    return "gpu" in line and "use" in line and "memory" not in line and "%" in line


def _is_vram_mb_line(line: str) -> bool:
    has_memory_label = "vram" in line or "memory" in line
    if not has_memory_label or "mb" not in line:
        return False
    if "vram%" in line or "vram %" in line:
        return False
    return "used" in line or "use" in line or "allocated" in line


def _is_vram_bytes_line(line: str) -> bool:
    has_memory_label = "vram" in line or "memory" in line
    has_byte_unit = "(b)" in line or " b" in line or line.endswith("b")
    if not has_memory_label or not has_byte_unit or "mb" in line:
        return False
    if "vram%" in line or "vram %" in line:
        return False
    return "used" in line or "use" in line or "allocated" in line


def _is_power_watts_line(line: str) -> bool:
    return "power" in line and ("(w)" in line or " w" in line or line.endswith("w"))
