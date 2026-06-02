"""按推荐顺序自动回放 blacklist/Milvus/filter 功能测试样例。"""

import asyncio
import os
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
    assert process.stdout is not None
    output_parts: list[str] = []
    accumulated = ""
    try:
        while True:
            chunk = await asyncio.wait_for(
                process.stdout.read(1024), timeout=WAIT_TIMEOUT_SECONDS
            )
            if not chunk:
                raise RuntimeError(
                    f"等待输入提示超时/中断: {context}; main.py stdout closed"
                )
            text = chunk.decode("utf-8", errors="replace")
            print(text, end="")
            output_parts.append(text)
            accumulated += text
            if PROMPT_TEXT in accumulated:
                break
    except asyncio.TimeoutError as exc:
        raise TimeoutError(
            f"等待输入提示超时: {context}; {WAIT_TIMEOUT_SECONDS}s 内未看到 {PROMPT_TEXT!r}"
        ) from exc
    return "".join(output_parts)


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


async def main() -> None:
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
            await read_until_prompt(process, f"case {case['id']}")
            processed_cases.append(case)
            await validate_after_case(case, processed_cases)

        assert process.stdin is not None
        process.stdin.write(b"exit\n")
        await process.stdin.drain()
        process.stdin.close()

        returncode = await process.wait()
        if returncode != 0:
            raise RuntimeError(f"main.py exited with code {returncode}")
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


if __name__ == "__main__":
    asyncio.run(main())
