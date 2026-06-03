"""按推荐顺序自动回放 blacklist/Milvus/filter 功能测试样例。"""

import asyncio
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.blacklist_demo_cases import TEST_CASES  # noqa: E402
from scripts.blacklist_demo_assertions import (  # noqa: E402
    assert_case_state,
    collect_case_state_snapshot,
)
from scripts.reset_and_seed_blacklist import main as reset_blacklist_main  # noqa: E402

PROMPT_TEXT = "请输入消息内容:"
WAIT_TIMEOUT_SECONDS = 300
SHUTDOWN_TIMEOUT_SECONDS = 10
EVENT_ID_PATTERN = re.compile(r"EVENT_ID:\s*([A-Za-z0-9_-]+)")


class ReadPromptError(Exception):
    """子进程提示等待失败 — 携带已缓冲的子进程输出。"""

    def __init__(
        self,
        reason: str,
        context: str,
        accumulated: str,
        returncode: int | None = None,
    ):
        self.reason = reason
        self.context = context
        self.accumulated = accumulated
        self.returncode = returncode
        parts = [f"read_until_prompt {reason}: {context}"]
        if returncode is not None:
            parts.append(f"(exit code {returncode})")
        super().__init__("; ".join(parts))


def print_case(case: dict) -> None:
    separator = "=" * 100
    print(separator)
    print(case["title"])
    print("- 输入文本:")
    print(case["text"])
    print("- 预期检查点:")
    for item in case["expect"]:
        print(f"  - {item}")


async def read_until_prompt(process: asyncio.subprocess.Process, context: str) -> str:
    """读取子进程 stdout 直到看见 PROMPT_TEXT。

    Returns
    -------
    累积的 stdout 输出文本。

    Raises
    ------
    ReadPromptError
        当子进程关闭 stdout (EOF) 或读取超时时抛出。
        ``.accumulated`` 字段携带抛出前已读到的全部输出。
    """
    assert process.stdout is not None
    output_parts: list[str] = []
    accumulated = ""
    try:
        while True:
            chunk = await asyncio.wait_for(
                process.stdout.read(1024), timeout=WAIT_TIMEOUT_SECONDS
            )
            if not chunk:
                # 子进程已关闭 stdout（可能崩溃或正常退出）。
                # 尝试读取管道中残留的字节。
                try:
                    remaining = await asyncio.wait_for(
                        process.stdout.read(), timeout=1.0
                    )
                    if remaining:
                        text = remaining.decode("utf-8", errors="replace")
                        print(text, end="")
                        output_parts.append(text)
                        accumulated += text
                except (asyncio.TimeoutError, Exception):
                    pass
                # 获取子进程退出码（如果有的话）
                exit_code: int | None = None
                try:
                    exit_code = await asyncio.wait_for(
                        process.wait(), timeout=1.0
                    )
                except (asyncio.TimeoutError, Exception):
                    pass
                raise ReadPromptError(
                    reason="child_stdout_closed",
                    context=context,
                    accumulated="".join(output_parts),
                    returncode=exit_code,
                )
            text = chunk.decode("utf-8", errors="replace")
            print(text, end="")
            output_parts.append(text)
            accumulated += text
            if PROMPT_TEXT in accumulated:
                break
    except asyncio.TimeoutError:
        # 超时时尝试获取退出码（非阻塞）
        exit_code: int | None = None
        try:
            exit_code = await asyncio.wait_for(process.wait(), timeout=0.1)
        except (asyncio.TimeoutError, Exception):
            pass
        raise ReadPromptError(
            reason="timeout",
            context=context,
            accumulated="".join(output_parts),
            returncode=exit_code,
        )
    return "".join(output_parts)


def extract_event_id(output: str) -> str | None:
    matches = EVENT_ID_PATTERN.findall(output)
    if not matches:
        return None
    return matches[-1]


async def validate_after_case(case: dict, processed_cases: list[dict]) -> None:
    snapshot = await collect_case_state_snapshot(processed_cases)
    failures = assert_case_state(case, snapshot)
    state = snapshot["cases"].get(case["id"], {})
    print("- 数据库状态快照:")
    print(f"  Milvus: {state.get('milvus')}")
    print(f"  Neo4j: {state.get('neo4j')}")
    if failures:
        print("- 校验结果: FAIL")
        for failure in failures:
            print(
                f"  [{failure.case_id}] {failure.path}: "
                f"expected={failure.expected!r}, observed={failure.observed!r}"
            )
        raise AssertionError(f"case {case['id']} database validation failed")
    print("- 校验结果: PASS")


async def main() -> int:
    """Run the full demo harness.

    Returns
    -------
    0 on success (all cases passed, child exited cleanly).
    1 on subprocess failure (crash / timeout / unexpected exit).

    On failure the error reason and preserved child output are printed
    to stderr before returning.
    """
    print("[1/3] 先重置 Neo4j、Redis、Milvus 并预置黑名单测试数据...\n")
    await reset_blacklist_main()

    print("\n[2/3] 输出本次自动回放的测试数据与检查点\n")
    for case in TEST_CASES:
        print_case(case)

    print("\n[3/3] 启动 main.py 并按顺序自动写入测试数据\n")
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")

    process = await asyncio.create_subprocess_exec(
        "uv",
        "run",
        str(ROOT / "main.py"),
        cwd=str(ROOT),
        env=env,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    try:
        assert process.stdin is not None
        assert process.stdout is not None

        await read_until_prompt(process, "initial startup")

        processed_cases: list[dict] = []
        for case in TEST_CASES:
            assert process.stdin is not None
            print_case(case)
            process.stdin.write((case["text"] + "\n").encode("utf-8"))
            await process.stdin.drain()
            output = await read_until_prompt(process, f"case {case['id']}")
            processed_cases.append({**case, "event_id": extract_event_id(output)})
            await validate_after_case(processed_cases[-1], processed_cases)

        assert process.stdin is not None
        process.stdin.write(b"exit\n")
        await process.stdin.drain()
        process.stdin.close()

        returncode = await process.wait()
        if returncode != 0:
            raise RuntimeError(f"main.py exited with code {returncode}")

    except ReadPromptError as e:
        _report_child_failure(e, process)
        return 1
    except RuntimeError as e:
        print(f"\n[ERROR] 子进程异常退出: {e}")
        return 1
    finally:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=SHUTDOWN_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()

    print("=" * 100)
    print("自动回放完成，请结合日志与 Redis 检查结果")
    print("=" * 100)
    return 0


def _report_child_failure(err: ReadPromptError, process: asyncio.subprocess.Process) -> None:
    """Print a structured failure report for a subprocess crash / timeout."""
    exit_str = str(err.returncode) if err.returncode is not None else "仍在运行 (timeout)"
    print("\n" + "!" * 70, file=sys.stderr)
    print(f"[ERROR] 子进程异常 — {err.reason}", file=sys.stderr)
    print(f"[ERROR] 上下文: {err.context}", file=sys.stderr)
    print(f"[ERROR] 子进程状态: {exit_str}", file=sys.stderr)
    if err.accumulated:
        summary = err.accumulated
        if len(summary) > 3000:
            summary = "(最后 3000 字符)\n" + summary[-3000:]
        print(f"[ERROR] 子进程最后输出 ({len(err.accumulated)} chars):", file=sys.stderr)
        print(summary, file=sys.stderr)
    print("!" * 70, file=sys.stderr)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
