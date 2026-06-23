from __future__ import annotations

import asyncio
import sys


class ReadPromptError(Exception):
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


def report_child_failure(
    err: ReadPromptError,
    process: asyncio.subprocess.Process,
    logger,
) -> None:
    del process
    exit_str = str(err.returncode) if err.returncode is not None else "仍在运行 (timeout)"
    report_lines = [
        "\n" + "!" * 70,
        f"[ERROR] 子进程异常 — {err.reason}",
        f"[ERROR] 上下文: {err.context}",
        f"[ERROR] 子进程状态: {exit_str}",
    ]
    if err.accumulated:
        summary = err.accumulated
        if len(summary) > 3000:
            summary = "(最后 3000 字符)\n" + summary[-3000:]
        report_lines.append(f"[ERROR] 子进程最后输出 ({len(err.accumulated)} chars):")
        report_lines.append(summary)
    report_lines.append("!" * 70)
    report = "\n".join(report_lines) + "\n"
    print(report, end="", file=sys.stderr)
    logger.error("%s", report.rstrip("\n"))
