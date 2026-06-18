"""Generate a competition-ready Sentinel Edge demo report.

By default this script only profiles the local environment and writes a JSON
readiness report. Use --run-pipeline to execute selected demo cases through
the real Sentinel pipeline.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path
from typing import TextIO

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.finance_demo_cases import FINANCE_CASES_BY_ID  # noqa: E402
from sentinel_edge import BenchmarkRecorder, collect_hardware_profile  # noqa: E402

DEFAULT_CASES = [
    "finance_01_low_risk_salary_stash",
    "finance_02_structuring_history_stash",
    "finance_04_aml_high_risk_recall",
]

ANSI_ESCAPE_RE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


class PlainLogStream:
    def __init__(self, stream: TextIO) -> None:
        self._stream = stream

    def write(self, data: str) -> int:
        self._stream.write(ANSI_ESCAPE_RE.sub("", data))
        return len(data)

    def flush(self) -> None:
        self._stream.flush()

    def isatty(self) -> bool:
        return False


class TeeStream:
    def __init__(self, *streams: TextIO) -> None:
        self._streams = streams

    def write(self, data: str) -> int:
        for stream in self._streams:
            stream.write(data)
        return len(data)

    def flush(self) -> None:
        for stream in self._streams:
            stream.flush()

    def isatty(self) -> bool:
        return any(getattr(stream, "isatty", lambda: False)() for stream in self._streams)


async def _run_cases(case_ids: list[str], config: dict) -> list[dict]:
    from main import process_message

    results: list[dict] = []
    for case_id in case_ids:
        case = FINANCE_CASES_BY_ID[case_id]
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


async def _build_report(args: argparse.Namespace) -> None:
    load_dotenv(ROOT / ".env")
    case_ids = args.case or DEFAULT_CASES

    report = {
        "project": "Sentinel Edge",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "competition_track": "基于 AMD 锐龙 AI MAX+ 平台的端侧 AI 智能体与垂直行业创新应用",
        "scenario": "银行零售业务端侧反欺诈与反洗钱预警助手",
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


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sentinel Edge competition demo report"
    )
    parser.add_argument(
        "--case",
        action="append",
        choices=sorted(FINANCE_CASES_BY_ID),
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
    parser.add_argument(
        "--log-output",
        default=None,
        help="Terminal output log path. Defaults to logs/sentinel_competition_demo_<timestamp>.log.",
    )
    args = parser.parse_args()

    log_path = ROOT / args.log_output if args.log_output else ROOT / "logs" / (
        f"sentinel_competition_demo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with log_path.open("w", encoding="utf-8") as log_file:
        plain_log_file = PlainLogStream(log_file)
        stdout = TeeStream(sys.stdout, plain_log_file)
        stderr = TeeStream(sys.stderr, plain_log_file)
        with redirect_stdout(stdout), redirect_stderr(stderr):
            print(f"Terminal output is also being written to: {log_path}")
            await _build_report(args)


if __name__ == "__main__":
    asyncio.run(main())
