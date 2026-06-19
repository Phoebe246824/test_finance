"""Collect PPT-ready competition evidence artifacts."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

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
    write_hardware_timeseries_chart,
    write_stage_breakdown_chart,
)
from sentinel_edge.evidence.hardware_sampler import sample_once  # noqa: E402
from sentinel_edge.evidence.models import EvidencePack  # noqa: E402
from sentinel_edge.evidence.sidecar import load_sidecar  # noqa: E402
from sentinel_edge.evidence.writer import write_evidence_pack  # noqa: E402

DEFAULT_CASES = list(FINANCE_CASES_BY_ID)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect PPT-ready Sentinel Edge evidence"
    )
    parser.add_argument(
        "--run-pipeline",
        action="store_true",
        help="Run selected cases through the real pipeline",
    )
    parser.add_argument(
        "--case",
        action="append",
        choices=sorted(FINANCE_CASES_BY_ID),
        help="Finance case id; can be repeated",
    )
    parser.add_argument(
        "--sidecar",
        default=None,
        help="YAML or JSON sidecar evidence file",
    )
    parser.add_argument(
        "--sample-interval",
        type=float,
        default=1.0,
        help="Reserved hardware sampling interval in seconds",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Evidence output directory",
    )
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
    hardware_samples = [sample_once()]
    cases = []

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
    chart_errors = await _write_charts(
        output_dir=output_dir,
        cases=cases,
        hardware_samples=hardware_samples,
        ppt_metrics=ppt_metrics,
    )
    if chart_errors:
        (output_dir / "chart_render_errors.json").write_text(
            json.dumps(chart_errors, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    else:
        (output_dir / "chart_render_errors.json").unlink(missing_ok=True)

    print(json.dumps({"output_dir": str(output_dir)}, ensure_ascii=False))
    return output_dir


def main() -> None:
    asyncio.run(main_async(parse_args()))


async def _write_charts(
    *,
    output_dir: Path,
    cases: list[Any],
    hardware_samples: list[Any],
    ppt_metrics: dict[str, Any],
) -> list[dict[str, str]]:
    chart_specs = [
        ("case_latency", write_case_latency_chart, cases),
        ("stage_breakdown", write_stage_breakdown_chart, []),
        ("hardware_timeseries", write_hardware_timeseries_chart, hardware_samples),
        ("baseline_comparison", write_baseline_comparison_chart, ppt_metrics),
    ]
    errors: list[dict[str, str]] = []
    for key, writer, data in chart_specs:
        html_path = output_dir / "charts" / "html" / f"{key}.html"
        png_path = output_dir / "charts" / "png" / f"{key}.png"
        try:
            await asyncio.to_thread(
                writer,
                data,
                html_path,
                png_path,
                render_png=True,
            )
        except Exception as exc:  # noqa: BLE001 - chart failures should not abort evidence.
            errors.append(
                {
                    "chart": key,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    return errors


if __name__ == "__main__":
    main()
