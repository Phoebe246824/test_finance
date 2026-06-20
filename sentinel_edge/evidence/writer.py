"""Write collected evidence artifacts for PPT production."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from sentinel_edge.evidence.models import EvidencePack, to_plain_data

CASE_RESULT_COLUMNS = [
    "case_id",
    "title",
    "event_id",
    "status",
    "risk_level",
    "risk_score",
    "elapsed_ms",
    "error",
    "case_log_path",
]
HARDWARE_SAMPLE_COLUMNS = [
    "timestamp",
    "gpu_util_percent",
    "vram_used_mb",
    "power_watts",
    "raw_output",
]
STAGE_TIMING_COLUMNS = ["case_id", "stage", "elapsed_ms", "source"]


def write_evidence_pack(pack: EvidencePack, output_dir: str | Path) -> Path:
    """Write JSON, CSV, and chart output directories for an evidence pack."""
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    (root / "charts" / "html").mkdir(parents=True, exist_ok=True)
    (root / "charts" / "png").mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(parents=True, exist_ok=True)

    (root / "evidence.json").write_text(
        json.dumps(to_plain_data(pack), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (root / "ppt_metrics.json").write_text(
        json.dumps(to_plain_data(pack.ppt_metrics), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_case_results_csv(root / "case_results.csv", pack)
    _write_hardware_samples_csv(root / "hardware_samples.csv", pack)
    _write_stage_timings_csv(root / "stage_timings.csv")
    return root


def _write_case_results_csv(path: Path, pack: EvidencePack) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CASE_RESULT_COLUMNS)
        writer.writeheader()
        for case in pack.cases:
            writer.writerow(
                {
                    "case_id": case.case_id,
                    "title": case.title,
                    "event_id": _blank_none(case.event_id),
                    "status": case.status,
                    "risk_level": _blank_none(case.risk_level),
                    "risk_score": _blank_none(case.risk_score),
                    "elapsed_ms": _blank_none(case.elapsed_ms),
                    "error": _blank_none(case.error),
                    "case_log_path": _blank_none(case.case_log_path),
                }
            )


def _write_hardware_samples_csv(path: Path, pack: EvidencePack) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=HARDWARE_SAMPLE_COLUMNS)
        writer.writeheader()
        for sample in pack.hardware_samples:
            writer.writerow(
                {
                    "timestamp": sample.timestamp,
                    "gpu_util_percent": _blank_none(sample.gpu_util_percent.value),
                    "vram_used_mb": _blank_none(sample.vram_used_mb.value),
                    "power_watts": _blank_none(sample.power_watts.value),
                    "raw_output": sample.raw_output,
                }
            )


def _write_stage_timings_csv(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(STAGE_TIMING_COLUMNS)


def _blank_none(value: object | None) -> object:
    return "" if value is None else value
