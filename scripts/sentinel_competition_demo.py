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
    "finance_03_blacklist_account_pass",
    "finance_04_aml_high_risk_recall",
    "finance_05_loan_fraud_pass",
    "finance_06_duplicate_low_risk_no_repeat",
    "finance_07_no_person_keyword_pass",
    "finance_08_device_geo_anomaly_pass",
    "finance_09_many_to_one_mule_account_pass",
    "finance_10_chargeback_complaint_similarity_pass",
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
        return any(
            getattr(stream, "isatty", lambda: False)() for stream in self._streams
        )


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")


async def _run_cases(
    case_ids: list[str],
    config: dict,
    *,
    run_log_dir: Path | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> list[dict]:
    from main import process_message

    results: list[dict] = []
    for index, case_id in enumerate(case_ids, start=1):
        case = FINANCE_CASES_BY_ID[case_id]
        recorder = BenchmarkRecorder()
        event_id = None
        error = None
        case_log_path = None
        if run_log_dir is not None:
            case_log_path = run_log_dir / f"{index:02d}_{_safe_filename(case_id)}.log"

        async def _run_one_case() -> None:
            nonlocal event_id, error
            print("=" * 100)
            print(f"CASE {index:02d}: {case_id}")
            print(case["title"])
            print("- 输入文本:")
            print(case["text"])
            print("- 预期:")
            for item in case.get("expect", []):
                print(f"  - {item}")
            print("- 执行输出:")
            try:
                with recorder.span("pipeline.process_message", case_id=case_id):
                    event_id = await process_message(case["text"], config)
            except Exception as exc:  # noqa: BLE001 - report demo failures without hiding them
                error = f"{type(exc).__name__}: {exc}"
                print(f"CASE ERROR: {error}")

        if case_log_path is None:
            await _run_one_case()
        else:
            case_log_path.parent.mkdir(parents=True, exist_ok=True)
            with case_log_path.open("w", encoding="utf-8") as case_log_file:
                plain_case_log = PlainLogStream(case_log_file)
                case_stdout = (
                    TeeStream(stdout, plain_case_log) if stdout else plain_case_log
                )
                case_stderr = (
                    TeeStream(stderr, plain_case_log) if stderr else plain_case_log
                )
                with redirect_stdout(case_stdout), redirect_stderr(case_stderr):
                    await _run_one_case()

        results.append(
            {
                "case_id": case_id,
                "title": case["title"],
                "event_id": event_id,
                "error": error,
                "case_log_path": str(case_log_path) if case_log_path else None,
                "timing": recorder.to_dict(),
                "expected": case.get("expect", []),
            }
        )
    return results


async def _build_report(
    args: argparse.Namespace,
    *,
    run_log_dir: Path,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> None:
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

        setup_file_logging(str(run_log_dir))
        config = load_config()
        report["pipeline_results"] = await _run_cases(
            case_ids,
            config,
            run_log_dir=run_log_dir,
            stdout=stdout,
            stderr=stderr,
        )

    output_path = (
        ROOT / args.output
        if args.output
        else run_log_dir / "sentinel_edge_demo_report.json"
    )
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
        default=None,
        help="Output JSON path. Defaults to the per-run log folder.",
    )
    parser.add_argument(
        "--log-output",
        default=None,
        help="Run log directory. Defaults to logs/sentinel_competition_demo_<timestamp>/.",
    )
    args = parser.parse_args()

    run_log_dir = (
        ROOT / args.log_output
        if args.log_output
        else ROOT
        / "logs"
        / f"sentinel_competition_demo_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    run_log_dir.mkdir(parents=True, exist_ok=True)
    run_log_path = run_log_dir / "00_run.log"

    with run_log_path.open("w", encoding="utf-8") as log_file:
        plain_log_file = PlainLogStream(log_file)
        stdout = TeeStream(sys.stdout, plain_log_file)
        stderr = TeeStream(sys.stderr, plain_log_file)
        with redirect_stdout(stdout), redirect_stderr(stderr):
            print(f"Run logs are being written to: {run_log_dir}")
            print(f"Combined terminal log: {run_log_path}")
            await _build_report(
                args,
                run_log_dir=run_log_dir,
                stdout=stdout,
                stderr=stderr,
            )


if __name__ == "__main__":
    asyncio.run(main())
