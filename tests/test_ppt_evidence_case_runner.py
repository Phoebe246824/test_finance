"""Tests for running finance demo cases into PPT evidence records."""

from __future__ import annotations

import importlib
import sys
from typing import Any

import pytest

from scripts.finance_demo_cases import FINANCE_CASES_BY_ID


async def test_run_cases_records_successful_case_evidence():
    from sentinel_edge.evidence.case_runner import run_cases

    case_id = "finance_03_blacklist_account_pass"
    case = FINANCE_CASES_BY_ID[case_id]

    async def fake_process(message: str, config: dict | None) -> dict[str, Any]:
        assert message == case["text"]
        assert config == {}
        return {
            "event_id": "EV-FIN-003",
            "status": "review_required",
            "risk_level": "high",
            "risk_score": 0.91,
        }

    results = await run_cases([case_id], config={}, process_message=fake_process)

    assert len(results) == 1
    result = results[0]
    assert result.case_id == case_id
    assert result.title == case["title"]
    assert result.event_id == "EV-FIN-003"
    assert result.status == "review_required"
    assert result.risk_level == "high"
    assert result.risk_score == 0.91
    assert result.elapsed_ms is not None
    assert result.error is None
    assert result.case_log_path is None
    assert result.expected == case["expect"]
    assert result.succeeded is True


async def test_run_cases_records_failure_without_raising():
    from sentinel_edge.evidence.case_runner import run_cases

    case_id = "finance_04_aml_high_risk_recall"
    case = FINANCE_CASES_BY_ID[case_id]

    async def fake_process(message: str, config: dict | None) -> dict[str, Any]:
        assert message == case["text"]
        assert config == {"mode": "demo"}
        raise RuntimeError("service down")

    results = await run_cases(
        [case_id],
        config={"mode": "demo"},
        process_message=fake_process,
    )

    assert len(results) == 1
    result = results[0]
    assert result.case_id == case_id
    assert result.title == case["title"]
    assert result.event_id is None
    assert result.status == "error"
    assert result.risk_level is None
    assert result.risk_score is None
    assert result.elapsed_ms is not None
    assert result.error == "RuntimeError: service down"
    assert result.expected == case["expect"]
    assert result.succeeded is False


async def test_run_cases_raises_key_error_for_unknown_case_id():
    from sentinel_edge.evidence.case_runner import run_cases

    async def fake_process(message: str, config: dict | None) -> dict[str, Any]:
        raise AssertionError("unknown cases should fail before processing")

    with pytest.raises(KeyError):
        await run_cases(
            ["finance_missing"],
            config={},
            process_message=fake_process,
        )


def test_importing_case_runner_does_not_import_main_eagerly():
    sys.modules.pop("sentinel_edge.evidence.case_runner", None)
    sys.modules.pop("main", None)

    module = importlib.import_module("sentinel_edge.evidence.case_runner")

    assert module.run_cases.__name__ == "run_cases"
    assert "main" not in sys.modules
