# PPT Evidence Collector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a PPT evidence collector that creates JSON/CSV plus PPT-ready PNG charts from existing Sentinel demo cases, hardware discovery, one-shot runtime sampling, and sidecar metrics.

**Architecture:** Add a focused `sentinel_edge/evidence/` package around the existing pipeline and demo case modules. The collector keeps business flow changes minimal: pure modules handle models, aggregation, sidecar merge, hardware sampling, charting, and file output; a thin CLI script wires them together.

**Tech Stack:** Python 3.13, dataclasses, pytest, matplotlib with Agg backend for PNG charts, PyYAML for sidecar files, existing `sentinel_edge.metrics`, `sentinel_edge.hardware`, and `scripts.finance_demo_cases`.

---

## File Structure

Create:

- `sentinel_edge/evidence/__init__.py` exports public collector primitives.
- `sentinel_edge/evidence/models.py` defines serializable evidence dataclasses.
- `sentinel_edge/evidence/aggregator.py` computes PPT metrics from cases, hardware samples, and sidecar data.
- `sentinel_edge/evidence/sidecar.py` loads and merges YAML/JSON manual evidence.
- `sentinel_edge/evidence/hardware_sampler.py` samples and parses ROCm hardware metrics.
- `sentinel_edge/evidence/writer.py` writes JSON and CSV output files.
- `sentinel_edge/evidence/charts.py` renders PNG charts.
- `sentinel_edge/evidence/case_runner.py` runs selected finance demo cases through `process_message_detailed()`.
- `scripts/collect_ppt_evidence.py` is the CLI entry point.
- `docs/competition/evidence_sidecar.example.yaml` documents manually filled fields.
- `tests/test_ppt_evidence_models.py`
- `tests/test_ppt_evidence_aggregator.py`
- `tests/test_ppt_evidence_sidecar.py`
- `tests/test_ppt_evidence_hardware_sampler.py`
- `tests/test_ppt_evidence_writer_charts.py`
- `tests/test_ppt_evidence_case_runner.py`
- `tests/test_collect_ppt_evidence_cli.py`

Modify:

- `pyproject.toml` add `matplotlib` and `pyyaml`.
- `requirements.txt` add `matplotlib` and `pyyaml`.
- `sentinel_edge/__init__.py` stays unchanged in this plan; evidence helpers are exported from `sentinel_edge/evidence/__init__.py`.

Do not modify:

- `graphiti_core/`
- Existing pipeline behavior in `main.py`, except a later follow-up if a separate plan adds fine-grained spans.

---

### Task 1: Add Evidence Dependencies

**Files:**
- Modify: `pyproject.toml`
- Modify: `requirements.txt`

- [ ] **Step 1: Add dependencies**

Edit `pyproject.toml` dependencies to include:

```toml
    "matplotlib>=3.10.0",
    "pyyaml>=6.0.2",
```

Edit `requirements.txt` to include:

```text
matplotlib
pyyaml
```

- [ ] **Step 2: Verify imports**

Run:

```bash
uv run python -c "import matplotlib; import yaml; print('evidence deps ok')"
```

Expected:

```text
evidence deps ok
```

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml requirements.txt uv.lock
git commit -m "chore: add evidence collection dependencies"
```

If `uv.lock` does not change because the environment is not locked in this run, omit it from `git add`.

---

### Task 2: Evidence Data Models

**Files:**
- Create: `tests/test_ppt_evidence_models.py`
- Create: `sentinel_edge/evidence/__init__.py`
- Create: `sentinel_edge/evidence/models.py`

- [ ] **Step 1: Write failing model tests**

Create `tests/test_ppt_evidence_models.py`:

```python
from sentinel_edge.evidence.models import (
    CaseEvidence,
    HardwareSample,
    MetricValue,
    Source,
    to_plain_data,
)


def test_metric_value_serializes_source_and_note():
    metric = MetricValue(value=123.4, unit="ms", source=Source.MEASURED, note="case run")

    assert to_plain_data(metric) == {
        "value": 123.4,
        "unit": "ms",
        "source": "measured",
        "note": "case run",
    }


def test_case_evidence_success_property():
    ok = CaseEvidence(case_id="finance_04", title="AML", elapsed_ms=10.0)
    failed = CaseEvidence(case_id="finance_05", title="Loan", error="RuntimeError: boom")

    assert ok.succeeded is True
    assert failed.succeeded is False


def test_hardware_sample_keeps_unavailable_reason():
    sample = HardwareSample(
        timestamp="2026-06-19T10:00:00",
        gpu_util_percent=MetricValue.not_available("%", "rocm-smi not found"),
    )

    data = to_plain_data(sample)
    assert data["gpu_util_percent"]["value"] is None
    assert data["gpu_util_percent"]["source"] == "not_available"
    assert data["gpu_util_percent"]["note"] == "rocm-smi not found"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_ppt_evidence_models.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'sentinel_edge.evidence'`.

- [ ] **Step 3: Implement models**

Create `sentinel_edge/evidence/models.py`:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from enum import StrEnum
from typing import Any


class Source(StrEnum):
    MEASURED = "measured"
    DERIVED = "derived"
    SIDECAR = "sidecar"
    NOT_AVAILABLE = "not_available"


@dataclass(slots=True)
class MetricValue:
    value: Any
    unit: str = ""
    source: Source = Source.MEASURED
    note: str = ""

    @classmethod
    def not_available(cls, unit: str = "", note: str = "") -> "MetricValue":
        return cls(value=None, unit=unit, source=Source.NOT_AVAILABLE, note=note)


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
    gpu_util_percent: MetricValue = field(default_factory=MetricValue.not_available)
    vram_used_mb: MetricValue = field(default_factory=MetricValue.not_available)
    power_watts: MetricValue = field(default_factory=MetricValue.not_available)
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
    if is_dataclass(value):
        return {key: to_plain_data(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: to_plain_data(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_plain_data(item) for item in value]
    return value
```

Create `sentinel_edge/evidence/__init__.py`:

```python
"""PPT evidence collection helpers for Sentinel competition materials."""

from sentinel_edge.evidence.models import (
    CaseEvidence,
    EvidencePack,
    HardwareSample,
    MetricValue,
    Source,
    to_plain_data,
)

__all__ = [
    "CaseEvidence",
    "EvidencePack",
    "HardwareSample",
    "MetricValue",
    "Source",
    "to_plain_data",
]
```

- [ ] **Step 4: Run model tests**

Run:

```bash
uv run pytest tests/test_ppt_evidence_models.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sentinel_edge/evidence/__init__.py sentinel_edge/evidence/models.py tests/test_ppt_evidence_models.py
git commit -m "feat: add PPT evidence data models"
```

---

### Task 3: Aggregation Logic

**Files:**
- Create: `tests/test_ppt_evidence_aggregator.py`
- Create: `sentinel_edge/evidence/aggregator.py`

- [ ] **Step 1: Write failing aggregation tests**

Create `tests/test_ppt_evidence_aggregator.py`:

```python
from sentinel_edge.evidence.aggregator import build_ppt_metrics, percentile
from sentinel_edge.evidence.models import CaseEvidence, HardwareSample, MetricValue, Source


def test_percentile_uses_nearest_rank():
    assert percentile([100.0, 200.0, 300.0, 400.0], 95) == 400.0
    assert percentile([100.0, 200.0, 300.0, 400.0], 50) == 200.0
    assert percentile([], 95) is None


def test_build_ppt_metrics_summarizes_cases_and_hardware():
    cases = [
        CaseEvidence(case_id="a", title="A", status="stashed", elapsed_ms=100.0, risk_level="low"),
        CaseEvidence(case_id="b", title="B", status="analyzed", elapsed_ms=300.0, risk_level="high"),
        CaseEvidence(case_id="c", title="C", elapsed_ms=900.0, error="boom"),
    ]
    samples = [
        HardwareSample(
            timestamp="2026-06-19T10:00:00",
            gpu_util_percent=MetricValue(12.0, "%", Source.MEASURED),
            vram_used_mb=MetricValue(4096, "MB", Source.MEASURED),
            power_watts=MetricValue(55.5, "W", Source.MEASURED),
        )
    ]

    metrics = build_ppt_metrics(cases=cases, hardware_samples=samples, sidecar={})

    assert metrics["p10"]["end_to_end_latency_mean_ms"]["value"] == 200.0
    assert metrics["p10"]["end_to_end_latency_p95_ms"]["value"] == 300.0
    assert metrics["p10"]["gpu_peak_util_percent"]["value"] == 12.0
    assert metrics["p10"]["vram_peak_mb"]["value"] == 4096
    assert metrics["p11"]["optimized"]["pass_rate"]["value"] == 2 / 3
    assert metrics["p13"]["case_count"]["value"] == 3
    assert metrics["p13"]["failed_case_count"]["value"] == 1


def test_build_ppt_metrics_marks_missing_runtime_values():
    metrics = build_ppt_metrics(cases=[], hardware_samples=[], sidecar={})

    assert metrics["p10"]["end_to_end_latency_mean_ms"]["source"] == "not_available"
    assert metrics["p10"]["ttft_ms"]["source"] == "not_available"
    assert metrics["p11"]["baseline"]["average_power_watts"]["source"] == "not_available"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_ppt_evidence_aggregator.py -v
```

Expected: FAIL with `ModuleNotFoundError` or missing `build_ppt_metrics`.

- [ ] **Step 3: Implement aggregation**

Create `sentinel_edge/evidence/aggregator.py`:

```python
from __future__ import annotations

from math import ceil
from statistics import mean
from typing import Any

from sentinel_edge.evidence.models import CaseEvidence, HardwareSample, MetricValue, Source, to_plain_data


def percentile(values: list[float], percent: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, ceil(len(ordered) * percent / 100) - 1)
    return ordered[index]


def _metric(value: Any, unit: str, source: Source, note: str = "") -> dict[str, Any]:
    return to_plain_data(MetricValue(value=value, unit=unit, source=source, note=note))


def _not_available(unit: str = "", note: str = "") -> dict[str, Any]:
    return to_plain_data(MetricValue.not_available(unit=unit, note=note))


def _measured_numbers(samples: list[HardwareSample], attr: str) -> list[float]:
    values: list[float] = []
    for sample in samples:
        metric = getattr(sample, attr)
        if metric.source == Source.MEASURED and metric.value is not None:
            values.append(float(metric.value))
    return values


def _sidecar_metric(sidecar: dict[str, Any], path: tuple[str, ...], unit: str) -> dict[str, Any]:
    current: Any = sidecar
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return _not_available(unit, f"sidecar missing {'.'.join(path)}")
        current = current[key]
    value = current.get("value") if isinstance(current, dict) else current
    note = current.get("note", "") if isinstance(current, dict) else ""
    return _metric(value, unit, Source.SIDECAR, note)


def build_ppt_metrics(
    *,
    cases: list[CaseEvidence],
    hardware_samples: list[HardwareSample],
    sidecar: dict[str, Any],
) -> dict[str, Any]:
    successful_cases = [case for case in cases if case.succeeded]
    elapsed = [
        float(case.elapsed_ms)
        for case in successful_cases
        if case.elapsed_ms is not None
    ]
    gpu_values = _measured_numbers(hardware_samples, "gpu_util_percent")
    vram_values = _measured_numbers(hardware_samples, "vram_used_mb")
    power_values = _measured_numbers(hardware_samples, "power_watts")

    return {
        "p5": {
            "finance_demo_case_count": _metric(len(cases), "case", Source.DERIVED),
        },
        "p8": {
            "hardware_sample_count": _metric(len(hardware_samples), "sample", Source.DERIVED),
            "gpu_peak_util_percent": (
                _metric(max(gpu_values), "%", Source.DERIVED)
                if gpu_values else _not_available("%", "no measured GPU samples")
            ),
            "vram_peak_mb": (
                _metric(max(vram_values), "MB", Source.DERIVED)
                if vram_values else _not_available("MB", "no measured VRAM samples")
            ),
            "llama_cpp_offload_log": _sidecar_metric(sidecar, ("p8", "llama_cpp_offload_log"), ""),
        },
        "p10": {
            "end_to_end_latency_mean_ms": (
                _metric(round(mean(elapsed), 2), "ms", Source.DERIVED)
                if elapsed else _not_available("ms", "no successful case timings")
            ),
            "end_to_end_latency_p95_ms": (
                _metric(percentile(elapsed, 95), "ms", Source.DERIVED)
                if elapsed else _not_available("ms", "no successful case timings")
            ),
            "ttft_ms": _sidecar_metric(sidecar, ("p10", "ttft_ms"), "ms"),
            "tokens_per_second": _sidecar_metric(sidecar, ("p10", "tokens_per_second"), "tokens/s"),
            "gpu_peak_util_percent": (
                _metric(max(gpu_values), "%", Source.DERIVED)
                if gpu_values else _not_available("%", "no measured GPU samples")
            ),
            "vram_peak_mb": (
                _metric(max(vram_values), "MB", Source.DERIVED)
                if vram_values else _not_available("MB", "no measured VRAM samples")
            ),
            "average_power_watts": (
                _metric(round(mean(power_values), 2), "W", Source.DERIVED)
                if power_values else _sidecar_metric(sidecar, ("p10", "average_power_watts"), "W")
            ),
        },
        "p11": {
            "baseline": {
                "pass_rate": _sidecar_metric(sidecar, ("p11", "baseline", "pass_rate"), ""),
                "average_power_watts": _sidecar_metric(sidecar, ("p11", "baseline", "average_power_watts"), "W"),
            },
            "optimized": {
                "pass_rate": _metric(
                    (len(successful_cases) / len(cases)) if cases else None,
                    "",
                    Source.DERIVED if cases else Source.NOT_AVAILABLE,
                    "" if cases else "no case results",
                ),
                "risk_level_consistency": _sidecar_metric(sidecar, ("p11", "optimized", "risk_level_consistency"), ""),
            },
        },
        "p12": {
            "privacy_evidence": _sidecar_metric(sidecar, ("p12", "privacy_evidence"), ""),
        },
        "p13": {
            "case_count": _metric(len(cases), "case", Source.DERIVED),
            "failed_case_count": _metric(len(cases) - len(successful_cases), "case", Source.DERIVED),
        },
        "p14": {
            "business_value": _sidecar_metric(sidecar, ("p14", "business_value"), ""),
        },
    }
```

- [ ] **Step 4: Run aggregation tests**

Run:

```bash
uv run pytest tests/test_ppt_evidence_aggregator.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sentinel_edge/evidence/aggregator.py tests/test_ppt_evidence_aggregator.py
git commit -m "feat: aggregate PPT evidence metrics"
```

---

### Task 4: Sidecar Loading and Merge Rules

**Files:**
- Create: `tests/test_ppt_evidence_sidecar.py`
- Create: `sentinel_edge/evidence/sidecar.py`
- Create: `docs/competition/evidence_sidecar.example.yaml`

- [ ] **Step 1: Write failing sidecar tests**

Create `tests/test_ppt_evidence_sidecar.py`:

```python
import pytest

from sentinel_edge.evidence.models import MetricValue, Source
from sentinel_edge.evidence.sidecar import load_sidecar, merge_metric


def test_load_sidecar_reads_yaml(tmp_path):
    path = tmp_path / "sidecar.yaml"
    path.write_text(
        """
p10:
  ttft_ms:
    value: 321
    note: llama.cpp log
""",
        encoding="utf-8",
    )

    data = load_sidecar(path)

    assert data["p10"]["ttft_ms"]["value"] == 321
    assert data["_meta"]["path"] == str(path)


def test_load_sidecar_rejects_non_mapping(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("- not\n- mapping\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must contain a mapping"):
        load_sidecar(path)


def test_merge_metric_prefers_measured_without_override():
    measured = MetricValue(10, "ms", Source.MEASURED, "auto")
    sidecar = {"value": 20, "note": "manual"}

    merged = merge_metric(measured, sidecar, unit="ms")

    assert merged.value == 10
    assert merged.source == Source.MEASURED


def test_merge_metric_fills_not_available_and_allows_override():
    missing = MetricValue.not_available("ms", "missing")
    filled = merge_metric(missing, {"value": 20, "note": "manual"}, unit="ms")
    overridden = merge_metric(MetricValue(10, "ms"), {"value": 30, "override": True}, unit="ms")

    assert filled.value == 20
    assert filled.source == Source.SIDECAR
    assert overridden.value == 30
    assert overridden.source == Source.SIDECAR
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_ppt_evidence_sidecar.py -v
```

Expected: FAIL with missing `sentinel_edge.evidence.sidecar`.

- [ ] **Step 3: Implement sidecar loader**

Create `sentinel_edge/evidence/sidecar.py`:

```python
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from sentinel_edge.evidence.models import MetricValue, Source


def load_sidecar(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    sidecar_path = Path(path)
    if not sidecar_path.exists():
        raise FileNotFoundError(f"sidecar file not found: {sidecar_path}")
    text = sidecar_path.read_text(encoding="utf-8")
    if sidecar_path.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        data = yaml.safe_load(text)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError(f"sidecar file must contain a mapping: {sidecar_path}")
    data["_meta"] = {
        "path": str(sidecar_path),
        "loaded_at": datetime.now().isoformat(timespec="seconds"),
    }
    return data


def merge_metric(
    measured: MetricValue,
    sidecar_value: dict[str, Any] | Any | None,
    *,
    unit: str = "",
) -> MetricValue:
    if sidecar_value is None:
        return measured
    if isinstance(sidecar_value, dict):
        value = sidecar_value.get("value")
        note = sidecar_value.get("note", "")
        override = bool(sidecar_value.get("override", False))
    else:
        value = sidecar_value
        note = ""
        override = False

    if measured.source != Source.NOT_AVAILABLE and not override:
        return measured
    return MetricValue(value=value, unit=unit or measured.unit, source=Source.SIDECAR, note=note)
```

- [ ] **Step 4: Add sidecar example**

Create `docs/competition/evidence_sidecar.example.yaml`:

```yaml
p8:
  llama_cpp_offload_log:
    value: "logs/llama_cpp_offload.log"
    note: "Path to llama.cpp startup log showing ROCm offload layers."
p10:
  ttft_ms:
    value: null
    note: "Copied sidecar should replace null with measured TTFT from local llama.cpp run."
  tokens_per_second:
    value: null
    note: "Copied sidecar should replace null with measured generation throughput."
  average_power_watts:
    value: null
    note: "Copied sidecar should replace null with external power meter or ROCm sampling value."
p11:
  baseline:
    pass_rate:
      value: null
      note: "Copied sidecar should replace null with baseline model pass rate."
    average_power_watts:
      value: null
      note: "Copied sidecar should replace null with baseline power measurement."
  optimized:
    risk_level_consistency:
      value: null
      note: "Copied sidecar should replace null with repeated-run consistency."
p12:
  privacy_evidence:
    value: "docs/screenshots/privacy-log-masking.png"
    note: "Path to privacy or log masking screenshot."
p14:
  business_value:
    value: null
    note: "Record source document or calculation basis."
```

- [ ] **Step 5: Run sidecar tests**

Run:

```bash
uv run pytest tests/test_ppt_evidence_sidecar.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add sentinel_edge/evidence/sidecar.py tests/test_ppt_evidence_sidecar.py docs/competition/evidence_sidecar.example.yaml
git commit -m "feat: load PPT evidence sidecar data"
```

---

### Task 5: Hardware Sampling

**Files:**
- Create: `tests/test_ppt_evidence_hardware_sampler.py`
- Create: `sentinel_edge/evidence/hardware_sampler.py`

- [ ] **Step 1: Write failing hardware sampler tests**

Create `tests/test_ppt_evidence_hardware_sampler.py`:

```python
from sentinel_edge.evidence.hardware_sampler import parse_rocm_smi_output, sample_once


def test_parse_rocm_smi_output_extracts_numbers():
    output = """
GPU[0]          : GPU use (%)           : 87
GPU[0]          : GPU Memory Allocated (VRAM%) : 42
GPU[0]          : Average Graphics Package Power (W) : 58.0
"""

    parsed = parse_rocm_smi_output(output)

    assert parsed["gpu_util_percent"] == 87.0
    assert parsed["vram_used_mb"] is None
    assert parsed["power_watts"] == 58.0


def test_sample_once_returns_not_available_when_command_missing():
    sample = sample_once(command_runner=lambda _command: "")

    assert sample.gpu_util_percent.source == "not_available"
    assert sample.vram_used_mb.source == "not_available"
    assert sample.power_watts.source == "not_available"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_ppt_evidence_hardware_sampler.py -v
```

Expected: FAIL with missing `sentinel_edge.evidence.hardware_sampler`.

- [ ] **Step 3: Implement hardware sampler**

Create `sentinel_edge/evidence/hardware_sampler.py`:

```python
from __future__ import annotations

import re
import shutil
import subprocess
from datetime import datetime
from typing import Callable

from sentinel_edge.evidence.models import HardwareSample, MetricValue, Source

CommandRunner = Callable[[list[str]], str]


def _default_runner(command: list[str]) -> str:
    if shutil.which(command[0]) is None:
        return ""
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=5.0,
    )
    return "\n".join(part.strip() for part in (completed.stdout, completed.stderr) if part.strip())


def _first_number(patterns: list[str], text: str) -> float | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def parse_rocm_smi_output(output: str) -> dict[str, float | None]:
    return {
        "gpu_util_percent": _first_number(
            [r"GPU use \(%\)\s*:\s*([0-9.]+)", r"GPU\s*use.*?([0-9.]+)\s*%"],
            output,
        ),
        "vram_used_mb": _first_number(
            [r"VRAM.*?([0-9.]+)\s*MB", r"Memory Used.*?([0-9.]+)\s*MB"],
            output,
        ),
        "power_watts": _first_number(
            [r"Power \(W\)\s*:\s*([0-9.]+)", r"Package Power.*?\(W\)\s*:\s*([0-9.]+)"],
            output,
        ),
    }


def _metric(value: float | None, unit: str, unavailable_note: str) -> MetricValue:
    if value is None:
        return MetricValue.not_available(unit=unit, note=unavailable_note)
    return MetricValue(value=value, unit=unit, source=Source.MEASURED)


def sample_once(command_runner: CommandRunner = _default_runner) -> HardwareSample:
    command = ["rocm-smi", "--showuse", "--showmemuse", "--showpower"]
    output = command_runner(command)
    parsed = parse_rocm_smi_output(output) if output else {}
    note = "rocm-smi output missing or unsupported"
    return HardwareSample(
        timestamp=datetime.now().isoformat(timespec="seconds"),
        gpu_util_percent=_metric(parsed.get("gpu_util_percent"), "%", note),
        vram_used_mb=_metric(parsed.get("vram_used_mb"), "MB", note),
        power_watts=_metric(parsed.get("power_watts"), "W", note),
        raw_output=output,
    )
```

- [ ] **Step 4: Run hardware sampler tests**

Run:

```bash
uv run pytest tests/test_ppt_evidence_hardware_sampler.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sentinel_edge/evidence/hardware_sampler.py tests/test_ppt_evidence_hardware_sampler.py
git commit -m "feat: sample ROCm hardware evidence"
```

---

### Task 6: Evidence Writer and Charts

**Files:**
- Create: `tests/test_ppt_evidence_writer_charts.py`
- Create: `sentinel_edge/evidence/writer.py`
- Create: `sentinel_edge/evidence/charts.py`

- [ ] **Step 1: Write failing writer and chart tests**

Create `tests/test_ppt_evidence_writer_charts.py`:

```python
import json

from sentinel_edge.evidence.charts import write_case_latency_chart
from sentinel_edge.evidence.models import CaseEvidence, EvidencePack
from sentinel_edge.evidence.writer import write_evidence_pack


def test_write_evidence_pack_outputs_json_and_csv(tmp_path):
    pack = EvidencePack(
        project="Sentinel Edge",
        generated_at="2026-06-19T10:00:00",
        pipeline_executed=True,
        hardware_profile={"gpu_detected": False},
        cases=[CaseEvidence(case_id="finance_01", title="Salary", elapsed_ms=123.0)],
        ppt_metrics={"p13": {"case_count": {"value": 1}}},
    )

    write_evidence_pack(pack, tmp_path)

    assert json.loads((tmp_path / "evidence.json").read_text(encoding="utf-8"))["project"] == "Sentinel Edge"
    assert (tmp_path / "ppt_metrics.json").exists()
    assert "finance_01" in (tmp_path / "case_results.csv").read_text(encoding="utf-8")
    assert (tmp_path / "hardware_samples.csv").exists()


def test_write_case_latency_chart_creates_png(tmp_path):
    output = tmp_path / "chart.png"

    write_case_latency_chart(
        [CaseEvidence(case_id="a", title="A", elapsed_ms=100.0)],
        output,
    )

    assert output.exists()
    assert output.stat().st_size > 100
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_ppt_evidence_writer_charts.py -v
```

Expected: FAIL with missing writer/charts modules.

- [ ] **Step 3: Implement writer**

Create `sentinel_edge/evidence/writer.py`:

```python
from __future__ import annotations

import csv
import json
from pathlib import Path

from sentinel_edge.evidence.models import EvidencePack, to_plain_data


def write_evidence_pack(pack: EvidencePack, output_dir: str | Path) -> Path:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    (root / "charts").mkdir(exist_ok=True)
    (root / "logs").mkdir(exist_ok=True)

    data = to_plain_data(pack)
    (root / "evidence.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (root / "ppt_metrics.json").write_text(
        json.dumps(pack.ppt_metrics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with (root / "case_results.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["case_id", "title", "event_id", "status", "risk_level", "risk_score", "elapsed_ms", "error", "case_log_path"],
        )
        writer.writeheader()
        for case in pack.cases:
            writer.writerow({
                "case_id": case.case_id,
                "title": case.title,
                "event_id": case.event_id or "",
                "status": case.status,
                "risk_level": case.risk_level or "",
                "risk_score": "" if case.risk_score is None else case.risk_score,
                "elapsed_ms": "" if case.elapsed_ms is None else case.elapsed_ms,
                "error": case.error or "",
                "case_log_path": case.case_log_path or "",
            })

    with (root / "hardware_samples.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["timestamp", "gpu_util_percent", "vram_used_mb", "power_watts", "raw_output"],
        )
        writer.writeheader()
        for sample in pack.hardware_samples:
            writer.writerow({
                "timestamp": sample.timestamp,
                "gpu_util_percent": sample.gpu_util_percent.value,
                "vram_used_mb": sample.vram_used_mb.value,
                "power_watts": sample.power_watts.value,
                "raw_output": sample.raw_output,
            })

    (root / "stage_timings.csv").write_text("case_id,stage,elapsed_ms,source\n", encoding="utf-8")
    return root
```

- [ ] **Step 4: Implement charts**

Create `sentinel_edge/evidence/charts.py`:

```python
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

from matplotlib import pyplot as plt  # noqa: E402

from sentinel_edge.evidence.models import CaseEvidence


def _save_empty_chart(output_path: Path, title: str, message: str) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.set_title(title)
    ax.text(0.5, 0.5, message, ha="center", va="center", transform=ax.transAxes)
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def write_case_latency_chart(cases: list[CaseEvidence], output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    measured = [case for case in cases if case.elapsed_ms is not None and case.succeeded]
    if not measured:
        _save_empty_chart(output, "Case Latency", "No successful case timings available")
        return output

    labels = [case.case_id.replace("finance_", "f") for case in measured]
    seconds = [float(case.elapsed_ms) / 1000 for case in measured]
    fig, ax = plt.subplots(figsize=(10, 5.6))
    ax.bar(labels, seconds, color="#4C78A8")
    ax.set_title("End-to-End Case Latency")
    ax.set_ylabel("seconds")
    ax.tick_params(axis="x", labelrotation=35)
    fig.tight_layout()
    fig.savefig(output, dpi=160)
    plt.close(fig)
    return output


def write_stage_breakdown_chart(output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    _save_empty_chart(output, "Stage Breakdown", "Detailed stage spans not collected in this run")
    return output


def write_baseline_comparison_chart(output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    _save_empty_chart(output, "Baseline Comparison", "Baseline sidecar metrics not available")
    return output
```

- [ ] **Step 5: Run writer and chart tests**

Run:

```bash
uv run pytest tests/test_ppt_evidence_writer_charts.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add sentinel_edge/evidence/writer.py sentinel_edge/evidence/charts.py tests/test_ppt_evidence_writer_charts.py
git commit -m "feat: write PPT evidence files and charts"
```

---

### Task 7: Case Runner

**Files:**
- Create: `tests/test_ppt_evidence_case_runner.py`
- Create: `sentinel_edge/evidence/case_runner.py`

- [ ] **Step 1: Write failing case runner tests**

Create `tests/test_ppt_evidence_case_runner.py`:

```python
import pytest

from sentinel_edge.evidence.case_runner import run_cases


@pytest.mark.asyncio
async def test_run_cases_records_success():
    async def fake_process(_text, _config):
        return {
            "event_id": "evt-1",
            "status": "stashed",
            "risk_level": "low",
            "risk_score": 0.0,
        }

    results = await run_cases(
        ["finance_01_low_risk_salary_stash"],
        config={},
        process_message=fake_process,
    )

    assert len(results) == 1
    assert results[0].case_id == "finance_01_low_risk_salary_stash"
    assert results[0].event_id == "evt-1"
    assert results[0].succeeded is True
    assert results[0].elapsed_ms is not None


@pytest.mark.asyncio
async def test_run_cases_records_failure_without_raising():
    async def fake_process(_text, _config):
        raise RuntimeError("service down")

    results = await run_cases(
        ["finance_04_aml_high_risk_recall"],
        config={},
        process_message=fake_process,
    )

    assert results[0].succeeded is False
    assert results[0].status == "error"
    assert results[0].error == "RuntimeError: service down"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_ppt_evidence_case_runner.py -v
```

Expected: FAIL with missing `sentinel_edge.evidence.case_runner`.

- [ ] **Step 3: Implement testable case runner**

Create `sentinel_edge/evidence/case_runner.py`:

```python
from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from scripts.finance_demo_cases import FINANCE_CASES_BY_ID
from sentinel_edge.evidence.models import CaseEvidence

ProcessMessage = Callable[[str, dict | None], Awaitable[dict]]


async def run_cases(
    case_ids: list[str],
    config: dict | None,
    process_message: ProcessMessage | None = None,
) -> list[CaseEvidence]:
    if process_message is None:
        from main import process_message_detailed

        process_message = process_message_detailed

    results: list[CaseEvidence] = []
    for case_id in case_ids:
        case = FINANCE_CASES_BY_ID[case_id]
        started = time.perf_counter()
        error: str | None = None
        payload: dict = {}
        try:
            payload = await process_message(case["text"], config)
        except Exception as exc:  # noqa: BLE001 - evidence report must preserve per-case failures
            error = f"{type(exc).__name__}: {exc}"
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        results.append(
            CaseEvidence(
                case_id=case_id,
                title=case["title"],
                event_id=payload.get("event_id"),
                status=payload.get("status", "error" if error else "unknown"),
                risk_level=payload.get("risk_level"),
                risk_score=payload.get("risk_score"),
                elapsed_ms=elapsed_ms,
                error=error,
                expected=case.get("expect", []),
            )
        )
    return results
```

- [ ] **Step 4: Run case runner tests**

Run:

```bash
uv run pytest tests/test_ppt_evidence_case_runner.py -v
```

Expected: PASS.

- [ ] **Step 5: Verify import does not load `main.py` eagerly**

Run:

```bash
uv run python -c "from sentinel_edge.evidence.case_runner import run_cases; print(run_cases.__name__)"
```

Expected:

```text
run_cases
```

- [ ] **Step 6: Commit**

```bash
git add sentinel_edge/evidence/case_runner.py tests/test_ppt_evidence_case_runner.py
git commit -m "feat: run finance cases for PPT evidence"
```

---

### Task 8: CLI Integration

**Files:**
- Create: `tests/test_collect_ppt_evidence_cli.py`
- Create: `scripts/collect_ppt_evidence.py`

- [ ] **Step 1: Write failing CLI unit tests**

Create `tests/test_collect_ppt_evidence_cli.py`:

```python
from scripts.collect_ppt_evidence import build_output_dir, parse_args


def test_parse_args_accepts_sidecar_and_case():
    args = parse_args([
        "--case",
        "finance_04_aml_high_risk_recall",
        "--sidecar",
        "docs/competition/evidence_sidecar.example.yaml",
        "--sample-interval",
        "2.5",
    ])

    assert args.case == ["finance_04_aml_high_risk_recall"]
    assert args.sidecar == "docs/competition/evidence_sidecar.example.yaml"
    assert args.sample_interval == 2.5


def test_build_output_dir_uses_explicit_path(tmp_path):
    output = build_output_dir(str(tmp_path / "manual"))

    assert output == tmp_path / "manual"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_collect_ppt_evidence_cli.py -v
```

Expected: FAIL with missing `scripts.collect_ppt_evidence`.

- [ ] **Step 3: Implement CLI**

Create `scripts/collect_ppt_evidence.py`:

```python
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.finance_demo_cases import FINANCE_CASES_BY_ID  # noqa: E402
from sentinel_edge import collect_hardware_profile  # noqa: E402
from sentinel_edge.evidence.aggregator import build_ppt_metrics  # noqa: E402
from sentinel_edge.evidence.case_runner import run_cases  # noqa: E402
from sentinel_edge.evidence.charts import (  # noqa: E402
    write_baseline_comparison_chart,
    write_case_latency_chart,
    write_stage_breakdown_chart,
)
from sentinel_edge.evidence.hardware_sampler import sample_once  # noqa: E402
from sentinel_edge.evidence.models import EvidencePack  # noqa: E402
from sentinel_edge.evidence.sidecar import load_sidecar  # noqa: E402
from sentinel_edge.evidence.writer import write_evidence_pack  # noqa: E402


DEFAULT_CASES = list(FINANCE_CASES_BY_ID)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect PPT-ready Sentinel evidence")
    parser.add_argument("--run-pipeline", action="store_true", help="Run selected cases through the real pipeline")
    parser.add_argument("--case", action="append", choices=sorted(FINANCE_CASES_BY_ID), help="Case id; can be repeated")
    parser.add_argument("--sidecar", default=None, help="YAML or JSON sidecar evidence file")
    parser.add_argument("--sample-interval", type=float, default=1.0, help="Reserved hardware sampling interval in seconds")
    parser.add_argument("--output-dir", default=None, help="Evidence output directory")
    return parser.parse_args(argv)


def build_output_dir(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return ROOT / "output" / "competition" / "evidence" / stamp


async def main_async(args: argparse.Namespace) -> Path:
    load_dotenv(ROOT / ".env")
    sidecar = load_sidecar(args.sidecar)
    hardware_profile = collect_hardware_profile().to_dict()
    cases = []
    hardware_samples = [sample_once()]

    if args.run_pipeline:
        from main import load_config

        cases = await run_cases(args.case or DEFAULT_CASES, load_config())

    ppt_metrics = build_ppt_metrics(
        cases=cases,
        hardware_samples=hardware_samples,
        sidecar=sidecar,
    )
    pack = EvidencePack(
        project="Sentinel Edge",
        generated_at=datetime.now().isoformat(timespec="seconds"),
        pipeline_executed=args.run_pipeline,
        hardware_profile=hardware_profile,
        cases=cases,
        hardware_samples=hardware_samples,
        sidecar=sidecar,
        ppt_metrics=ppt_metrics,
    )
    output_dir = write_evidence_pack(pack, build_output_dir(args.output_dir))
    write_case_latency_chart(cases, output_dir / "charts" / "case_latency.png")
    write_stage_breakdown_chart(output_dir / "charts" / "stage_breakdown.png")
    write_baseline_comparison_chart(output_dir / "charts" / "baseline_comparison.png")
    print(json.dumps({"output_dir": str(output_dir)}, ensure_ascii=False))
    return output_dir


def main() -> None:
    asyncio.run(main_async(parse_args()))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run CLI unit tests**

Run:

```bash
uv run pytest tests/test_collect_ppt_evidence_cli.py -v
```

Expected: PASS.

- [ ] **Step 5: Run CLI smoke test without pipeline**

Run:

```bash
uv run python scripts/collect_ppt_evidence.py --sidecar docs/competition/evidence_sidecar.example.yaml --output-dir output/competition/evidence/smoke
```

Expected: command exits 0 and prints JSON containing:

```json
{"output_dir": "output/competition/evidence/smoke"}
```

Then verify:

```bash
test -f output/competition/evidence/smoke/evidence.json
test -f output/competition/evidence/smoke/ppt_metrics.json
test -f output/competition/evidence/smoke/charts/case_latency.png
```

Expected: all `test -f` commands exit 0.

- [ ] **Step 6: Commit**

```bash
git add scripts/collect_ppt_evidence.py tests/test_collect_ppt_evidence_cli.py
git commit -m "feat: add PPT evidence collector CLI"
```

---

### Task 9: Public Exports and Focused Test Run

**Files:**
- Modify: `sentinel_edge/evidence/__init__.py`

- [ ] **Step 1: Export useful helpers**

Update `sentinel_edge/evidence/__init__.py`:

```python
"""PPT evidence collection helpers for Sentinel competition materials."""

from sentinel_edge.evidence.aggregator import build_ppt_metrics
from sentinel_edge.evidence.hardware_sampler import sample_once
from sentinel_edge.evidence.models import (
    CaseEvidence,
    EvidencePack,
    HardwareSample,
    MetricValue,
    Source,
    to_plain_data,
)
from sentinel_edge.evidence.sidecar import load_sidecar
from sentinel_edge.evidence.writer import write_evidence_pack

__all__ = [
    "CaseEvidence",
    "EvidencePack",
    "HardwareSample",
    "MetricValue",
    "Source",
    "build_ppt_metrics",
    "load_sidecar",
    "sample_once",
    "to_plain_data",
    "write_evidence_pack",
]
```

Leave `sentinel_edge/__init__.py` unchanged.

- [ ] **Step 2: Run focused evidence test suite**

Run:

```bash
uv run pytest \
  tests/test_ppt_evidence_models.py \
  tests/test_ppt_evidence_aggregator.py \
  tests/test_ppt_evidence_sidecar.py \
  tests/test_ppt_evidence_hardware_sampler.py \
  tests/test_ppt_evidence_writer_charts.py \
  tests/test_ppt_evidence_case_runner.py \
  tests/test_collect_ppt_evidence_cli.py \
  -v
```

Expected: all selected tests PASS.

- [ ] **Step 3: Commit**

```bash
git add sentinel_edge/evidence/__init__.py
git commit -m "chore: export PPT evidence helpers"
```

---

### Task 10: Documentation and Final Verification

**Files:**
- Modify: `docs/commands.md`

- [ ] **Step 1: Document commands**

Add this section to `docs/commands.md` near the competition/demo commands:

````markdown
### PPT 证据采集

```bash
# 不运行真实 pipeline，只生成环境画像、sidecar 合并结果、CSV 和 PNG 图表
uv run python scripts/collect_ppt_evidence.py \
  --sidecar docs/competition/evidence_sidecar.example.yaml \
  --output-dir output/competition/evidence/smoke

# 运行单条金融用例，适合先验证 finance_04 回捞链路
uv run python scripts/collect_ppt_evidence.py \
  --run-pipeline \
  --case finance_04_aml_high_risk_recall

# 在 AMD 实测环境运行完整 10 条金融用例
uv run python scripts/collect_ppt_evidence.py \
  --run-pipeline \
  --sidecar docs/competition/evidence_sidecar.example.yaml
```
````

- [ ] **Step 2: Run docs and code checks**

Run:

```bash
uv run pytest \
  tests/test_ppt_evidence_models.py \
  tests/test_ppt_evidence_aggregator.py \
  tests/test_ppt_evidence_sidecar.py \
  tests/test_ppt_evidence_hardware_sampler.py \
  tests/test_ppt_evidence_writer_charts.py \
  tests/test_ppt_evidence_case_runner.py \
  tests/test_collect_ppt_evidence_cli.py \
  -v
```

Expected: all selected tests PASS.

Run:

```bash
uv run python scripts/collect_ppt_evidence.py \
  --sidecar docs/competition/evidence_sidecar.example.yaml \
  --output-dir output/competition/evidence/smoke
```

Expected: exits 0 and writes:

- `output/competition/evidence/smoke/evidence.json`
- `output/competition/evidence/smoke/ppt_metrics.json`
- `output/competition/evidence/smoke/case_results.csv`
- `output/competition/evidence/smoke/hardware_samples.csv`
- `output/competition/evidence/smoke/charts/case_latency.png`
- `output/competition/evidence/smoke/charts/stage_breakdown.png`
- `output/competition/evidence/smoke/charts/baseline_comparison.png`

- [ ] **Step 3: Inspect generated metrics**

Run:

```bash
uv run python - <<'PY'
import json
from pathlib import Path

metrics = json.loads(Path("output/competition/evidence/smoke/ppt_metrics.json").read_text(encoding="utf-8"))
required = {"p5", "p8", "p10", "p11", "p12", "p13", "p14"}
missing = required - set(metrics)
if missing:
    raise SystemExit(f"missing PPT pages: {sorted(missing)}")
print("ppt metric pages ok")
PY
```

Expected:

```text
ppt metric pages ok
```

- [ ] **Step 4: Commit docs**

```bash
git add docs/commands.md
git commit -m "docs: document PPT evidence collection commands"
```

- [ ] **Step 5: Final status check**

Run:

```bash
git status --short --branch
git log --oneline -8
```

Expected: working tree has only intentionally ignored/generated output, or is clean after removing smoke output if it is untracked.
