"""按推荐顺序自动回放 blacklist/Milvus/filter 功能测试样例。"""

import asyncio
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from redis.asyncio import Redis

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from blacklist.store import BlacklistStore  # noqa: E402
from scripts.blacklist_demo_cases import TEST_CASES  # noqa: E402
from scripts.blacklist_demo_assertions import (  # noqa: E402
    Neo4jCaseInspector,
    assert_case_state,
    collect_case_state_snapshot,
)
from scripts.reset_and_seed_blacklist import (  # noqa: E402
    EVENT_SEEDS,
    KEYWORD_SEEDS,
    PERSON_SEEDS,
)

PROMPT_TEXT = "请输入消息内容:"
WAIT_TIMEOUT_SECONDS = 300
SHUTDOWN_TIMEOUT_SECONDS = 10
EVENT_ID_PATTERN = re.compile(r"EVENT_ID:\s*([A-Za-z0-9_-]+)")


class DemoRunLogger:
    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.log_path.open("w", encoding="utf-8")

    def write(self, text: str) -> None:
        self._file.write(text)
        self._file.flush()

    def print(self, *args: object, sep: str = " ", end: str = "\n") -> None:
        text = sep.join(str(arg) for arg in args) + end
        print(text, end="")
        self.write(text)

    def close(self) -> None:
        self._file.close()


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


RUN_LOGGER: DemoRunLogger | None = None
CASE_LOGGER: DemoRunLogger | None = None


def log_print(*args: object, sep: str = " ", end: str = "\n") -> None:
    text = sep.join(str(arg) for arg in args) + end
    print(text, end="")
    if RUN_LOGGER is not None:
        RUN_LOGGER.write(text)
    if CASE_LOGGER is not None:
        CASE_LOGGER.write(text)


def print_case(case: dict) -> None:
    separator = "=" * 100
    log_print(separator)
    log_print(case["title"])
    log_print("- 输入文本:")
    log_print(case["text"])
    log_print("- 预期检查点:")
    for item in case["expect"]:
        log_print(f"  - {item}")


async def read_until_prompt(process: asyncio.subprocess.Process, context: str) -> str:
    """读取子进程 stdout 直到看见 PROMPT_TEXT。"""
    assert process.stdout is not None
    output_parts: list[str] = []
    accumulated = ""
    try:
        while True:
            chunk = await asyncio.wait_for(
                process.stdout.read(1024), timeout=WAIT_TIMEOUT_SECONDS
            )
            if not chunk:
                try:
                    remaining = await asyncio.wait_for(
                        process.stdout.read(), timeout=1.0
                    )
                    if remaining:
                        text = remaining.decode("utf-8", errors="replace")
                        log_print(text, end="")
                        output_parts.append(text)
                        accumulated += text
                except (asyncio.TimeoutError, Exception):
                    pass

                exit_code: int | None = None
                try:
                    exit_code = await asyncio.wait_for(process.wait(), timeout=1.0)
                except (asyncio.TimeoutError, Exception):
                    pass
                raise ReadPromptError(
                    reason="child_stdout_closed",
                    context=context,
                    accumulated="".join(output_parts),
                    returncode=exit_code,
                )
            text = chunk.decode("utf-8", errors="replace")
            log_print(text, end="")
            output_parts.append(text)
            accumulated += text
            if PROMPT_TEXT in accumulated:
                break
    except asyncio.TimeoutError:
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
                log_print(
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
    log_print("- 数据库状态快照:")
    log_print(f"  Milvus: {state.get('milvus')}")
    log_print(f"  Neo4j: {state.get('neo4j')}")
    if filtered_failures or neo4j_duplicate_failures:
        log_print("- 校验结果: FAIL")
        for failure in filtered_failures:
            log_print(
                f"  [{failure.case_id}] {failure.path}: "
                f"expected={failure.expected!r}, observed={failure.observed!r}"
            )
        for failure in neo4j_duplicate_failures:
            log_print(f"  {failure}")
        raise AssertionError(f"case {case['id']} database validation failed")
    log_print("- 校验结果: PASS")


async def reset_demo_state_preserve_neo4j() -> None:
    load_dotenv(dotenv_path=ROOT / ".env")

    host = os.getenv("REDIS_HOST", "localhost")
    port = int(os.getenv("REDIS_PORT", "6379"))
    password = os.getenv("REDIS_PASSWORD") or None
    blacklist_db = int(os.getenv("BLACKLIST_REDIS_DB", "1"))

    milvus_uri = os.getenv("MILVUS_URI", "http://localhost:19530")
    milvus_token = os.getenv("MILVUS_TOKEN", "")
    milvus_collection = os.getenv("MILVUS_STASH_COLLECTION", "stashed_events")

    redis = Redis(host=host, port=port, password=password, db=blacklist_db)
    store = BlacklistStore(redis)

    try:
        before_blacklist = await redis.dbsize()
        await redis.flushdb()

        for person_id in PERSON_SEEDS:
            await store.append_person(person_id)
        for keyword in KEYWORD_SEEDS:
            await store.append_keyword(keyword)
        for event_id, summary in EVENT_SEEDS:
            await store.append_event(event_id, summary)

        dropped_milvus_collection = reset_milvus_collection(
            uri=milvus_uri,
            token=milvus_token,
            collection_name=milvus_collection,
        )

        log_print("Reset demo state and seeded blacklist Redis:")
        log_print("  Neo4j: preserved existing graph nodes")
        log_print(
            f"  Blacklist DB ({blacklist_db}): cleared {before_blacklist} keys, "
            f"seeded {len(PERSON_SEEDS)} persons, {len(KEYWORD_SEEDS)} keywords, {len(EVENT_SEEDS)} events"
        )
        milvus_status = "dropped" if dropped_milvus_collection else "not found"
        log_print(f"  Milvus stash ({milvus_collection}): collection {milvus_status}")
    finally:
        await redis.aclose()


def reset_milvus_collection(
    *,
    uri: str,
    token: str,
    collection_name: str,
) -> bool:
    from pymilvus import MilvusClient

    client = MilvusClient(uri=uri, token=token or None)
    try:
        if not client.has_collection(collection_name):
            return False
        client.drop_collection(collection_name)
        return True
    finally:
        close = getattr(client, "close", None)
        if close is not None:
            close()


async def main() -> int:
    global CASE_LOGGER, RUN_LOGGER

    logs_dir = ROOT / "logs"
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    demo_log_path = logs_dir / f"blacklist_kv_demo_{run_id}.log"
    case_log_dir = logs_dir / f"blacklist_kv_demo_cases_{run_id}"
    main_log_dir = logs_dir / "blacklist_kv_demo_main"
    RUN_LOGGER = DemoRunLogger(demo_log_path)

    process = None
    try:
        log_print(f"自动回放总览日志文件: {demo_log_path}")
        log_print(f"每条测试文本日志目录: {case_log_dir}")
        log_print(f"main.py 流程日志目录: {main_log_dir}")
        log_print("[1/3] 保留 Neo4j，重置 Redis、Milvus 并预置黑名单测试数据...\n")
        await reset_demo_state_preserve_neo4j()

        log_print("\n[2/3] 输出本次自动回放的测试数据与检查点\n")
        for case in TEST_CASES:
            print_case(case)

        log_print("\n记录 Neo4j 运行前 baseline，用于判断是否新增重复构图\n")
        neo4j_baseline = await collect_neo4j_baseline(TEST_CASES)
        for case in TEST_CASES:
            log_print(
                f"  [{case['id']}] neo4j.content_count.before={neo4j_baseline[case['id']]}"
            )

        log_print("\n[3/3] 启动 main.py 并按顺序自动写入测试数据\n")
        env = os.environ.copy()
        env.setdefault("PYTHONIOENCODING", "utf-8")

        process = await asyncio.create_subprocess_exec(
            sys.executable,
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

        await read_until_prompt(process, "initial startup")

        processed_cases: list[dict] = []
        for index, case in enumerate(TEST_CASES, start=1):
            assert process.stdin is not None
            case_log_path = case_log_dir / f"{index:02d}_{case['id']}.log"
            CASE_LOGGER = DemoRunLogger(case_log_path)
            try:
                log_print(f"单条测试文本日志文件: {case_log_path}")
                print_case(case)
                process.stdin.write((case["text"] + "\n").encode("utf-8"))
                await process.stdin.drain()
                output = await read_until_prompt(process, f"case {case['id']}")
                processed_case = {**case, "event_id": extract_event_id(output)}
                processed_cases.append(processed_case)
                await validate_after_case(processed_case, processed_cases, neo4j_baseline)
            finally:
                CASE_LOGGER.close()
                CASE_LOGGER = None

        assert process.stdin is not None
        process.stdin.write(b"exit\n")
        await process.stdin.drain()
        process.stdin.close()

        returncode = await process.wait()
        if returncode != 0:
            raise RuntimeError(f"main.py exited with code {returncode}")

        log_print("=" * 100)
        log_print("自动回放完成，请结合日志与 Redis 检查结果")
        log_print(f"自动回放总览日志文件: {demo_log_path}")
        log_print(f"每条测试文本日志目录: {case_log_dir}")
        log_print(f"main.py 流程日志目录: {main_log_dir}")
        log_print("=" * 100)
        return 0
    except ReadPromptError as e:
        if process is not None:
            _report_child_failure(e, process)
        return 1
    except RuntimeError as e:
        log_print(f"\n[ERROR] 子进程异常退出: {e}")
        return 1
    finally:
        if process is not None and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=SHUTDOWN_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
        if CASE_LOGGER is not None:
            CASE_LOGGER.close()
            CASE_LOGGER = None
        if RUN_LOGGER is not None:
            RUN_LOGGER.close()
            RUN_LOGGER = None


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
