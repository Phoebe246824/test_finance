"""Run finance demo cases and collect PPT evidence records."""

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
    """Run selected finance demo cases and return per-case evidence.

    Args:
        case_ids: Finance case IDs from ``scripts.finance_demo_cases``.
        config: Optional pipeline configuration passed to the processor.
        process_message: Optional async processor for tests or alternate runners.

    Returns:
        CaseEvidence records preserving success and per-case failure details.

    Raises:
        KeyError: If any requested case ID is unknown.
    """
    if process_message is None:
        from main import process_message_detailed

        process_message = process_message_detailed

    results: list[CaseEvidence] = []
    for case_id in case_ids:
        case = FINANCE_CASES_BY_ID[case_id]
        started_at = time.perf_counter()
        event_id = None
        status = "unknown"
        risk_level = None
        risk_score = None
        error = None

        try:
            payload = await process_message(case["text"], config)
        except Exception as exc:  # noqa: BLE001 - failures are evidence, not fatal.
            status = "error"
            error = f"{type(exc).__name__}: {exc}"
        else:
            event_id = payload.get("event_id")
            status = payload.get("status", status)
            risk_level = payload.get("risk_level")
            risk_score = payload.get("risk_score")

        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
        results.append(
            CaseEvidence(
                case_id=case_id,
                title=case["title"],
                event_id=event_id,
                status=status,
                risk_level=risk_level,
                risk_score=risk_score,
                elapsed_ms=elapsed_ms,
                error=error,
                expected=list(case.get("expect", [])),
            )
        )

    return results
