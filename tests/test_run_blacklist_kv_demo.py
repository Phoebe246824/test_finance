import asyncio

import pytest

from scripts import run_blacklist_kv_demo as demo


class FakeStdin:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.closed = False

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class FakeProcess:
    def __init__(self) -> None:
        self.stdin = FakeStdin()
        self.stdout = object()
        self.returncode = None
        self.terminated = False
        self.killed = False

    async def wait(self) -> int:
        self.returncode = 0
        return 0

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9


@pytest.mark.asyncio
async def test_main_catches_assertion_failure(monkeypatch, capsys):
    fake_process = FakeProcess()
    prompts_seen = 0

    async def fake_create_subprocess_exec(*args, **kwargs):
        return fake_process

    async def fake_read_until_prompt(process, context):
        nonlocal prompts_seen
        prompts_seen += 1
        return "EVENT_ID: E001\n"

    async def fake_validate_after_case(case, processed_cases, neo4j_baseline):
        raise AssertionError("case case_01 database validation failed")

    monkeypatch.setattr(
        demo,
        "TEST_CASES",
        [{"id": "case_01", "title": "Case", "text": "hello", "expect": []}],
    )
    monkeypatch.setattr(
        demo,
        "reset_demo_state_preserve_neo4j",
        lambda: asyncio.sleep(0),
    )
    monkeypatch.setattr(
        demo,
        "collect_neo4j_baseline",
        lambda cases: asyncio.sleep(0, result={"case_01": 0}),
    )
    monkeypatch.setattr(demo, "validate_after_case", fake_validate_after_case)
    monkeypatch.setattr(demo, "read_until_prompt", fake_read_until_prompt)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    assert await demo.main() == 1

    captured = capsys.readouterr()
    assert "[ERROR] 数据库校验失败: case case_01 database validation failed" in captured.out
    assert "Traceback" not in captured.err
    assert prompts_seen == 2


def test_child_failure_report_writes_to_configured_logs(tmp_path, capsys):
    run_log_path = tmp_path / "run.log"
    case_log_path = tmp_path / "case.log"
    demo.RUN_LOGGER = demo.DemoRunLogger(run_log_path)
    demo.CASE_LOGGER = demo.DemoRunLogger(case_log_path)
    try:
        err = demo.ReadPromptError(
            reason="timeout",
            context="case case_01",
            accumulated="child output",
            returncode=None,
        )

        demo._report_child_failure(err, FakeProcess())
    finally:
        demo.CASE_LOGGER.close()
        demo.CASE_LOGGER = None
        demo.RUN_LOGGER.close()
        demo.RUN_LOGGER = None

    captured = capsys.readouterr()
    assert "[ERROR] 子进程异常 — timeout" in captured.err
    assert "child output" in captured.err
    assert "[ERROR] 子进程异常 — timeout" in run_log_path.read_text(encoding="utf-8")
    assert "child output" in case_log_path.read_text(encoding="utf-8")
