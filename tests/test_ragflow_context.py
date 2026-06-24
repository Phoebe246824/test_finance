from __future__ import annotations

import pytest

from ragflow.client import RagflowConfig
from ragflow.context import format_knowledge_for_prompt


def test_ragflow_config_is_not_ready_without_credentials() -> None:
    config = RagflowConfig(
        enabled=True,
        base_url="http://127.0.0.1:9380",
        api_key="",
        dataset_ids=["dataset"],
    )

    assert not config.ready


def test_format_knowledge_for_prompt_includes_sources_and_text() -> None:
    text = format_knowledge_for_prompt(
        {
            "chunks": [
                {
                    "content": "AML rules require enhanced review for mule-account patterns.",
                    "document_name": "aml.pdf",
                    "score": 0.91,
                    "page": 12,
                }
            ]
        }
    )

    assert "aml.pdf" in text
    assert "mule-account patterns" in text
    assert "score=0.91" in text


def test_format_knowledge_for_prompt_handles_empty_results() -> None:
    assert format_knowledge_for_prompt({"chunks": []}) == ""


@pytest.mark.asyncio
async def test_client_returns_empty_result_when_not_ready() -> None:
    from ragflow.client import RagflowClient

    result = await RagflowClient(
        RagflowConfig(
            enabled=False,
            base_url="",
            api_key="",
            dataset_ids=[],
        )
    ).retrieve("query")

    assert result["ready"] is False
    assert result["chunks"] == []
