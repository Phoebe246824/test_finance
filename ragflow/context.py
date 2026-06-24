from __future__ import annotations

from typing import Any

from models import NormalizedEvent

from ragflow.client import RagflowClient


def build_event_query(event: NormalizedEvent, *, stage: str) -> str:
    return "\n".join(
        part
        for part in [
            f"stage: {stage}",
            f"event_type: {event.event_type}",
            f"summary: {event.summary}",
            f"risk_level: {event.risk_level}",
            f"raw_content: {event.raw_content}",
        ]
        if part and not part.endswith(": None")
    )


async def retrieve_financial_knowledge(
    config: dict[str, Any],
    event: NormalizedEvent,
    *,
    stage: str,
) -> dict[str, Any]:
    ragflow_config = config.get("ragflow", {})
    client_config = ragflow_config.get("client")
    if client_config is None:
        return {"enabled": False, "ready": False, "chunks": []}
    query = build_event_query(event, stage=stage)
    return await RagflowClient(client_config).retrieve(query)


def format_knowledge_for_prompt(
    result: dict[str, Any] | None,
    *,
    max_chars: int = 4000,
) -> str:
    if not result or not result.get("chunks"):
        return ""

    parts = []
    total = 0
    for index, chunk in enumerate(result.get("chunks", []), start=1):
        source = chunk.get("document_name") or "unknown source"
        score = chunk.get("score")
        page = chunk.get("page")
        header = f"[{index}] source={source}"
        if page:
            header += f", page={page}"
        if score is not None:
            header += f", score={score}"
        text = str(chunk.get("content") or "").strip()
        if not text:
            continue
        block = f"{header}\n{text}"
        if total + len(block) > max_chars:
            remaining = max_chars - total
            if remaining <= 0:
                break
            block = block[:remaining]
        parts.append(block)
        total += len(block)
        if total >= max_chars:
            break

    if not parts:
        return ""
    return "\n\n".join(parts)


def append_knowledge_context(
    existing_context: str,
    knowledge_text: str,
    *,
    header: str = "[RAGFlow financial knowledge]",
) -> str:
    knowledge_text = knowledge_text.strip()
    if not knowledge_text:
        return existing_context
    if existing_context:
        return f"{existing_context}\n\n{header}\n{knowledge_text}"
    return f"{header}\n{knowledge_text}"


def knowledge_section_for_prompt(
    knowledge_text: str,
    *,
    header: str = "RAGFlow financial knowledge reference:",
) -> str:
    knowledge_text = knowledge_text.strip()
    if not knowledge_text:
        return ""
    return f"{header}\n{knowledge_text}\n"
