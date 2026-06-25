from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass(frozen=True, slots=True)
class RagflowUploadError(Exception):
    code: int | str
    message: str

    def __str__(self) -> str:
        return f"RAGFlow upload API error {self.code}: {self.message}"


def _env_dataset_ids() -> list[str]:
    raw = os.getenv("RAGFLOW_DATASET_IDS") or os.getenv("RAGFLOW_DATASET_ID") or ""
    return [item.strip() for item in raw.split(",") if item.strip()]


def _pdf_paths(files: list[str]) -> list[Path]:
    paths = [Path(file).expanduser().resolve() for file in files]
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise SystemExit(f"File not found: {', '.join(missing)}")

    invalid = [str(path) for path in paths if path.suffix.lower() != ".pdf"]
    if invalid:
        raise SystemExit(f"Only PDF files are supported: {', '.join(invalid)}")
    return paths


async def upload_document(
    *,
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    dataset_id: str,
    path: Path,
) -> list[str]:
    url = f"{base_url.rstrip('/')}/api/v1/datasets/{dataset_id}/documents"
    headers = {"Authorization": f"Bearer {api_key}"}
    with path.open("rb") as file_obj:
        response = await client.post(
            url,
            headers=headers,
            files={"file": (path.name, file_obj, "application/pdf")},
        )
    response.raise_for_status()
    data = response.json()
    _raise_for_error_envelope(data)
    return _document_ids(data)


async def parse_documents(
    *,
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    dataset_id: str,
    document_ids: list[str],
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/v1/datasets/{dataset_id}/chunks"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    response = await client.post(url, headers=headers, json={"document_ids": document_ids})
    response.raise_for_status()
    data = response.json()
    _raise_for_error_envelope(data)
    return data


def _raise_for_error_envelope(data: Any) -> None:
    if not isinstance(data, dict):
        return

    code = data.get("code")
    if code in (None, 0, "0"):
        return

    message = str(data.get("message") or "RAGFlow upload request failed")
    raise RagflowUploadError(code=code, message=message)


def _document_ids(data: Any) -> list[str]:
    payload = data.get("data", data) if isinstance(data, dict) else data
    if isinstance(payload, dict):
        candidates = (
            payload.get("documents")
            or payload.get("items")
            or payload.get("document_ids")
            or payload.get("ids")
            or []
        )
        if payload.get("id"):
            candidates = [payload]
    else:
        candidates = payload if isinstance(payload, list) else []

    ids: list[str] = []
    for item in candidates:
        if isinstance(item, str):
            ids.append(item)
        elif isinstance(item, dict) and item.get("id"):
            ids.append(str(item["id"]))
    return ids


async def main() -> None:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Upload PDF files to a RAGFlow dataset.")
    parser.add_argument("files", nargs="+", help="PDF files to upload")
    parser.add_argument("--base-url", default=os.getenv("RAGFLOW_BASE_URL", ""))
    parser.add_argument("--api-key", default=os.getenv("RAGFLOW_API_KEY", ""))
    parser.add_argument("--dataset-id", default=(_env_dataset_ids() or [""])[0])
    parser.add_argument("--no-parse", action="store_true", help="Upload only; do not trigger parsing")
    args = parser.parse_args()

    if not args.base_url or not args.api_key or not args.dataset_id:
        raise SystemExit(
            "Missing RAGFlow settings. Set RAGFLOW_BASE_URL, RAGFLOW_API_KEY, "
            "and RAGFLOW_DATASET_ID in .env or pass CLI flags."
        )

    paths = _pdf_paths(args.files)

    all_document_ids: list[str] = []
    async with httpx.AsyncClient(timeout=120.0) as client:
        for path in paths:
            ids = await upload_document(
                client=client,
                base_url=args.base_url,
                api_key=args.api_key,
                dataset_id=args.dataset_id,
                path=path,
            )
            all_document_ids.extend(ids)
            print(f"Uploaded {path.name}: document_ids={ids}")

        if all_document_ids and not args.no_parse:
            result = await parse_documents(
                client=client,
                base_url=args.base_url,
                api_key=args.api_key,
                dataset_id=args.dataset_id,
                document_ids=all_document_ids,
            )
            print(f"Parse triggered: {result}")


if __name__ == "__main__":
    asyncio.run(main())
