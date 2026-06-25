"""Optional RAGFlow integration for financial knowledge retrieval."""

from ragflow.context import (
    append_knowledge_context,
    build_event_query,
    format_knowledge_for_prompt,
    knowledge_section_for_prompt,
    retrieve_financial_knowledge,
)

__all__ = [
    "build_event_query",
    "format_knowledge_for_prompt",
    "append_knowledge_context",
    "knowledge_section_for_prompt",
    "retrieve_financial_knowledge",
]
