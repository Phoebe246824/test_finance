"""Generate a competition-ready Sentinel Edge demo report.

By default this script only profiles the local environment and writes a JSON
readiness report. Use --run-pipeline to execute selected demo cases through
the real Sentinel pipeline.
"""

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

from scripts.blacklist_demo_cases import CASES_BY_ID  # noqa: E402
from sentinel_edge import BenchmarkRecorder, collect_hardware_profile  # noqa: E402

DEFAULT_CASES = [
    "case_03_p01_stash",
    "case_07c_p06_high_risk",
    "case_10_keyword_no_person_pass",
]


async def _run_cases(case_ids: list[str], config: dict) -> list[dict]:
    from main import process_message

    results: list[dict] = []
    for case_id in case_ids:
        case = CASES_BY_ID[case_id]
        recorder = BenchmarkRecorder()
        event_id = None
        error = None
        try:
            with recorder.span("pipeline.process_message", case_id=case_id):
                event_id = await process_message(case["text"], config)
        except Exception as exc:  # noqa: BLE001 - report demo failures without hiding them
            error = f"{type(exc).__name__}: {exc}"
        results.append(
            {
                "case_id": case_id,
                "title": case["title"],
                "event_id": event_id,
                "error": error,
                "timing": recorder.to_dict(),
                "expected": case.get("expect", []),
            }
        )
    return results


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sentinel Edge competition demo report"
    )
    parser.add_argument(
        "--case",
        action="append",
        choices=sorted(CASES_BY_ID),
        help="Demo case id. Can be provided multiple times.",
    )
    parser.add_argument(
        "--run-pipeline",
        action="store_true",
        help="Execute selected cases through Redis/Milvus/Neo4j/LLM pipeline.",
    )
    parser.add_argument(
        "--output",
        default="output/competition/sentinel_edge_demo_report.json",
        help="Output JSON path.",
    )
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    case_ids = args.case or DEFAULT_CASES

    report = {
        "project": "Sentinel Edge",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "competition_track": "基于 AMD 锐龙 AI MAX+ 平台的端侧 AI 智能体与垂直行业创新应用",
        "scenario": "金融/企业本地风险研判智能体",
        "hardware_profile": collect_hardware_profile().to_dict(),
        "selected_cases": case_ids,
        "pipeline_executed": args.run_pipeline,
        "pipeline_results": [],
    }

    if args.run_pipeline:
        from log_utils import setup_file_logging
        from main import load_config

        setup_file_logging()
        config = load_config()
        report["pipeline_results"] = await _run_cases(case_ids, config)

    output_path = ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Competition report written: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
