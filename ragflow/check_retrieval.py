from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from main import load_config  # noqa: E402
from ragflow.client import RagflowClient  # noqa: E402
from ragflow.context import format_knowledge_for_prompt  # noqa: E402


async def main() -> None:
    load_dotenv(ROOT / ".env", override=True)
    parser = argparse.ArgumentParser(description="Check RAGFlow retrieval settings.")
    parser.add_argument(
        "query",
        nargs="?",
        default="反洗钱 可疑交易 跑分 虚拟币 资金归集 风险识别",
    )
    args = parser.parse_args()

    config = load_config()
    ragflow_config = config.get("ragflow", {}).get("client")
    if ragflow_config is None or not ragflow_config.ready:
        raise SystemExit(
            "RAGFlow is not ready. Check RAGFLOW_ENABLED, RAGFLOW_BASE_URL, "
            "RAGFLOW_API_KEY, and RAGFLOW_DATASET_ID in .env."
        )

    result = await RagflowClient(ragflow_config).retrieve(args.query)
    chunks = result.get("chunks", [])
    print(f"ready={result.get('ready')} chunks={len(chunks)}")
    print(format_knowledge_for_prompt(result, max_chars=1500))


if __name__ == "__main__":
    asyncio.run(main())
