from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import yaml

from ragflow.client import _extract_chunks
from ragflow.context import append_knowledge_context, knowledge_section_for_prompt
from ragflow.upload_docs import (
    RagflowUploadError,
    _env_dataset_ids,
    _pdf_paths,
    parse_documents,
    upload_document,
)


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


def test_env_dataset_ids_prefers_plural_dataset_ids(
    monkeypatch,
) -> None:
    monkeypatch.setenv("RAGFLOW_DATASET_ID", "single")
    monkeypatch.setenv("RAGFLOW_DATASET_IDS", "first, second")

    assert _env_dataset_ids() == ["first", "second"]


def test_pdf_paths_rejects_non_pdf_files(tmp_path) -> None:
    text_path = tmp_path / "notes.txt"
    text_path.write_text("not a pdf", encoding="utf-8")

    try:
        _pdf_paths([str(text_path)])
    except SystemExit as exc:
        assert "Only PDF files are supported" in str(exc)
    else:
        raise AssertionError("non-PDF upload should be rejected")


@pytest.mark.asyncio
async def test_upload_document_raises_error_envelope(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "risk.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    async def fake_post(*args: object, **kwargs: object) -> httpx.Response:
        request = httpx.Request(
            "POST",
            "http://ragflow.example/api/v1/datasets/dataset/documents",
        )
        return httpx.Response(
            200,
            json={"code": 102, "message": "dataset not found", "data": False},
            request=request,
        )

    async with httpx.AsyncClient() as client:
        monkeypatch.setattr(client, "post", fake_post)

        with pytest.raises(RagflowUploadError, match="dataset not found"):
            await upload_document(
                client=client,
                base_url="http://ragflow.example",
                api_key="secret",
                dataset_id="dataset",
                path=pdf_path,
            )


@pytest.mark.asyncio
async def test_parse_documents_raises_error_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_post(*args: object, **kwargs: object) -> httpx.Response:
        request = httpx.Request(
            "POST",
            "http://ragflow.example/api/v1/datasets/dataset/chunks",
        )
        return httpx.Response(
            200,
            json={"code": 102, "message": "document parse failed", "data": False},
            request=request,
        )

    async with httpx.AsyncClient() as client:
        monkeypatch.setattr(client, "post", fake_post)

        with pytest.raises(RagflowUploadError, match="document parse failed"):
            await parse_documents(
                client=client,
                base_url="http://ragflow.example",
                api_key="secret",
                dataset_id="dataset",
                document_ids=["doc-1"],
            )


def test_ragflow_compose_binds_public_services_to_loopback() -> None:
    with open("compose/ragflow.yaml", encoding="utf-8") as file_obj:
        config = yaml.safe_load(file_obj)

    published_ports: list[str] = []
    for service in config["services"].values():
        published_ports.extend(str(port) for port in service.get("ports", []))

    assert published_ports
    assert all(port.startswith("127.0.0.1:") for port in published_ports)
    assert not any("RAGFLOW_ADMIN_API_PORT" in port for port in published_ports)


def test_ragflow_compose_waits_for_dependency_healthchecks() -> None:
    with open("compose/ragflow.yaml", encoding="utf-8") as file_obj:
        config = yaml.safe_load(file_obj)

    services = config["services"]
    dependencies = [
        "ragflow-mysql",
        "ragflow-redis",
        "ragflow-minio",
        "ragflow-es",
    ]

    for dependency in dependencies:
        assert "healthcheck" in services[dependency]

    depends_on = services["ragflow"]["depends_on"]
    assert isinstance(depends_on, dict)
    for dependency in dependencies:
        assert depends_on[dependency]["condition"] == "service_healthy"
