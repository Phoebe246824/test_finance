from __future__ import annotations

from ragflow.client import _extract_chunks
from ragflow.context import append_knowledge_context, knowledge_section_for_prompt


def test_extract_chunks_supports_ragflow_retrieval_payload() -> None:
    chunks = _extract_chunks(
        {
            "code": 0,
            "data": {
                "chunks": [
                    {
                        "content_with_weight": "Virtual assets red flag indicators.",
                        "content_ltks": "virtual assets red flag indicators",
                        "docnm_kwd": "fatf.pdf",
                        "similarity": 0.88,
                        "vector_similarity": 0.91,
                        "term_similarity": 0.72,
                    }
                ],
                "total": 1,
            },
        }
    )

    assert chunks == [
        {
            "content": "Virtual assets red flag indicators.",
            "document_name": "fatf.pdf",
            "score": 0.88,
            "vector_score": 0.91,
            "term_score": 0.72,
            "page": None,
            "metadata": {
                "content_with_weight": "Virtual assets red flag indicators.",
                "content_ltks": "virtual assets red flag indicators",
                "docnm_kwd": "fatf.pdf",
                "similarity": 0.88,
                "vector_similarity": 0.91,
                "term_similarity": 0.72,
            },
        }
    ]


def test_append_knowledge_context_ignores_empty_knowledge() -> None:
    assert append_knowledge_context("existing graph context", "") == (
        "existing graph context"
    )


def test_append_knowledge_context_adds_ragflow_section_when_available() -> None:
    text = append_knowledge_context("existing graph context", "AML red flag")

    assert "existing graph context" in text
    assert "[RAGFlow financial knowledge]" in text
    assert "AML red flag" in text


def test_knowledge_section_for_prompt_ignores_empty_knowledge() -> None:
    assert knowledge_section_for_prompt("") == ""


def test_knowledge_section_for_prompt_formats_dashboard_section() -> None:
    text = knowledge_section_for_prompt(
        "CDD and STR red flags.",
        header="RAGFlow金融知识库参考:",
    )

    assert text.startswith("RAGFlow金融知识库参考:")
    assert "CDD and STR red flags." in text
