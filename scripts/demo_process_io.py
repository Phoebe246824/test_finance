from __future__ import annotations

import asyncio

from scripts.demo_subprocess_report import ReadPromptError


async def read_until_prompt(
    process: asyncio.subprocess.Process,
    *,
    context: str,
    prompt_text: str,
    timeout_seconds: int,
) -> str:
    assert process.stdout is not None
    output_parts: list[str] = []
    accumulated = ""
    try:
        while True:
            chunk = await asyncio.wait_for(
                process.stdout.read(1024),
                timeout=timeout_seconds,
            )
            if not chunk:
                await _append_remaining_output(process, output_parts)
                exit_code = await _maybe_wait(process, timeout=1.0)
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
            if prompt_text in accumulated:
                break
    except asyncio.TimeoutError:
        exit_code = await _maybe_wait(process, timeout=0.1)
        raise ReadPromptError(
            reason="timeout",
            context=context,
            accumulated="".join(output_parts),
            returncode=exit_code,
        )
    return "".join(output_parts)


async def _append_remaining_output(
    process: asyncio.subprocess.Process,
    output_parts: list[str],
) -> None:
    if process.stdout is None:
        return
    try:
        remaining = await asyncio.wait_for(process.stdout.read(), timeout=1.0)
    except asyncio.TimeoutError:
        return
    if remaining:
        text = remaining.decode("utf-8", errors="replace")
        print(text, end="")
        output_parts.append(text)


async def _maybe_wait(
    process: asyncio.subprocess.Process,
    *,
    timeout: float,
) -> int | None:
    try:
        return await asyncio.wait_for(process.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        return None
