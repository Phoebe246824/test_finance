"""按推荐顺序自动回放 blacklist/Milvus/filter 功能测试样例。"""

import asyncio
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from blacklist.milvus_client import MilvusConfig, create_milvus_client  # noqa: E402
from blacklist.stores.factory import create_embedding_fn  # noqa: E402
from log_utils import get_logger, setup_file_logging  # noqa: E402
from scripts.blacklist_demo_cases import TEST_CASES  # noqa: E402
from scripts.blacklist_demo_assertions import (  # noqa: E402
    Neo4jCaseInspector,
    assert_case_state,
    collect_case_state_snapshot,
)
from scripts.demo_process_io import read_until_prompt  # noqa: E402
from scripts.demo_subprocess_report import (  # noqa: E402
    ReadPromptError,
    report_child_failure,
)
from scripts.reset_and_seed_blacklist import (  # noqa: E402
    reset_milvus_collections,
    seed_blacklist_stores,
)

PROMPT_TEXT = "请输入消息内容:"
WAIT_TIMEOUT_SECONDS = 300
SHUTDOWN_TIMEOUT_SECONDS = 10
EVENT_ID_PATTERN = re.compile(r"EVENT_ID:\s*([A-Za-z0-9_-]+)")


DETAIL_LOGGER = get_logger("scripts.blacklist_kv_demo")


def log_detail(*args: object, sep: str = " ", end: str = "\n") -> None:
    text = sep.join(str(arg) for arg in args) + end
    if text:
        DETAIL_LOGGER.info("%s", text.rstrip("\n"))


def print_case(case: dict) -> None:
    separator = "=" * 100
    print(separator)
    print(case["title"])
    print("- 输入文本:")
    print(case["text"])
    print("- 预期检查点:")
    for item in case["expect"]:
        print(f"  - {item}")


def extract_event_id(output: str) -> str | None:
    matches = EVENT_ID_PATTERN.findall(output)
    if not matches:
        return None
    return matches[-1]


async def collect_neo4j_baseline(cases: list[dict]) -> dict[str, int]:
    inspector = Neo4jCaseInspector()
    baseline = {}
    for case in cases:
        state = await inspector.inspect_case(case)
        baseline[case["id"]] = int(state.get("content_count") or 0)
    return baseline


async def validate_after_case(
    case: dict,
    processed_cases: list[dict],
    neo4j_baseline: dict[str, int],
) -> None:
    snapshot = await collect_case_state_snapshot(processed_cases)
    failures = assert_case_state(case, snapshot)
    filtered_failures = []
    neo4j_duplicate_failures = []

    for failure in failures:
        if not failure.path.startswith("neo4j."):
            filtered_failures.append(failure)
            continue

        case_state = snapshot["cases"].get(failure.case_id, {})
        neo4j_state = case_state.get("neo4j", {})
        before_count = neo4j_baseline.get(failure.case_id, 0)
        after_count = int(neo4j_state.get("content_count") or 0)
        expected_neo4j = failure.expected

        if before_count > 0:
            if after_count == before_count:
                log_detail(
                    f"- Neo4j baseline 校验通过 [{failure.case_id}]: "
                    f"before={before_count}, after={after_count}，未重复构图"
                )
            else:
                neo4j_duplicate_failures.append(
                    f"[{failure.case_id}] neo4j.content_count: before={before_count}, after={after_count}，疑似重复构图"
                )
            continue

        if failure.path == "neo4j.content_count" and expected_neo4j == 0:
            if after_count == before_count:
                continue
            neo4j_duplicate_failures.append(
                f"[{failure.case_id}] neo4j.content_count: expected no new graph, before={before_count}, after={after_count}"
            )
            continue

        filtered_failures.append(failure)

    state = snapshot["cases"].get(case["id"], {})
    log_detail("- 数据库状态快照:")
    log_detail(f"  Milvus: {state.get('milvus')}")
    log_detail(f"  Neo4j: {state.get('neo4j')}")
    if filtered_failures or neo4j_duplicate_failures:
        log_detail("- 校验结果: FAIL")
        for failure in filtered_failures:
            log_detail(
                f"  [{failure.case_id}] {failure.path}: "
                f"expected={failure.expected!r}, observed={failure.observed!r}"
            )
        for failure in neo4j_duplicate_failures:
            log_detail(f"  {failure}")
        raise AssertionError(f"case {case['id']} database validation failed")
    log_detail("- 校验结果: PASS")


async def reset_demo_state_preserve_neo4j() -> None:
    load_dotenv(dotenv_path=ROOT / ".env")
    milvus_uri = os.getenv("MILVUS_URI", "http://localhost:19530")
    milvus_token = os.getenv("MILVUS_TOKEN", "")
    client = create_milvus_client(MilvusConfig(uri=milvus_uri, token=milvus_token))
    embedding_fn = create_embedding_fn(
        {
            "model": os.getenv("EMBEDDER_MODEL") or "BAAI/bge-m3",
            "api_key": os.getenv("EMBEDDER_API_KEY")
            or os.getenv("LLM_API_KEY")
            or "",
            "api_base": os.getenv("EMBEDDER_API_BASE")
            or "https://api.openai.com/v1",
        }
    )

    try:
        dropped = reset_milvus_collections(client)
        seeded = await seed_blacklist_stores(
            client=client,
            embedding_fn=embedding_fn,
            embedding_dim=int(os.getenv("EMBEDDING_DIM") or "1024"),
        )

        log_detail("Reset demo state and seeded Milvus blacklist stores:")
        log_detail("  Neo4j: preserved existing graph nodes")
        log_detail(f"  Dropped Milvus collections: {dropped}")
        log_detail(f"  Seeded blacklist stores: {seeded}")
    finally:
        close = getattr(client, "close", None)
        if close is not None:
            close()


async def main() -> int:
    logs_dir = ROOT / "logs"
    detail_log_dir = logs_dir / "blacklist_kv_demo"
    main_log_dir = logs_dir / "blacklist_kv_demo_main"
    detail_log_path = setup_file_logging(str(detail_log_dir))

    process = None
    try:
        print(f"自动回放详细日志文件: {detail_log_path}")
        print(f"main.py 流程日志目录: {main_log_dir}")
        print("[1/3] 保留 Neo4j，重置 Milvus 并预置黑名单测试数据...\n")
        await reset_demo_state_preserve_neo4j()

        print("\n[2/3] 输出本次自动回放的测试数据与检查点\n")
        for case in TEST_CASES:
            print_case(case)

        print("\n记录 Neo4j 运行前 baseline，用于判断是否新增重复构图\n")
        neo4j_baseline = await collect_neo4j_baseline(TEST_CASES)
        for case in TEST_CASES:
            log_detail(
                f"  [{case['id']}] neo4j.content_count.before={neo4j_baseline[case['id']]}"
            )

        print("\n[3/3] 启动 main.py 并按顺序自动写入测试数据\n")
        env = os.environ.copy()
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("PYTHONUNBUFFERED", "1")

        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-u",
            str(ROOT / "main.py"),
            "--log-dir",
            str(main_log_dir),
            cwd=str(ROOT),
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        assert process.stdin is not None
        assert process.stdout is not None

        await read_until_prompt(
            process,
            context="initial startup",
            prompt_text=PROMPT_TEXT,
            timeout_seconds=WAIT_TIMEOUT_SECONDS,
        )

        processed_cases: list[dict] = []
        for index, case in enumerate(TEST_CASES, start=1):
            assert process.stdin is not None
            print(f"[{index}/{len(TEST_CASES)}] 运行 {case['id']}")
            print_case(case)
            process.stdin.write((case["text"] + "\n").encode("utf-8"))
            await process.stdin.drain()
            output = await read_until_prompt(
                process,
                context=f"case {case['id']}",
                prompt_text=PROMPT_TEXT,
                timeout_seconds=WAIT_TIMEOUT_SECONDS,
            )
            processed_case = {**case, "event_id": extract_event_id(output)}
            processed_cases.append(processed_case)
            await validate_after_case(processed_case, processed_cases, neo4j_baseline)

        assert process.stdin is not None
        process.stdin.write(b"exit\n")
        await process.stdin.drain()
        process.stdin.close()

        returncode = await process.wait()
        if returncode != 0:
            raise RuntimeError(f"main.py exited with code {returncode}")

        print("=" * 100)
        print("自动回放完成，请结合日志与 Milvus/Neo4j 检查结果")
        print("=" * 100)
        return 0
    except ReadPromptError as e:
        if process is not None:
            report_child_failure(e, process, DETAIL_LOGGER)
        return 1
    except AssertionError as e:
        print(f"\n[ERROR] 数据库校验失败: {e}")
        return 1
    except RuntimeError as e:
        print(f"\n[ERROR] 子进程异常退出: {e}")
        return 1
    finally:
        if process is not None and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=SHUTDOWN_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
