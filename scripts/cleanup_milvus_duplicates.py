from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from blacklist.milvus_client import MilvusConfig, create_milvus_client  # noqa: E402
from blacklist.stores.events_store import EventsStore  # noqa: E402
from blacklist.stores.factory import create_embedding_fn  # noqa: E402


def main() -> None:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(
        description="Clean duplicate or expired Milvus event rows."
    )
    parser.add_argument(
        "--expired",
        action="store_true",
        help="Delete expired event rows instead of duplicate content rows.",
    )
    parser.add_argument("--limit", type=int, default=10000)
    parser.add_argument(
        "--graph-built-retention-days",
        type=int,
        default=None,
        help="Also delete graph-built rows older than this many days when --expired is set.",
    )
    args = parser.parse_args()
    client = create_milvus_client(
        MilvusConfig(
            uri=os.getenv("MILVUS_URI", "http://localhost:19530"),
            token=os.getenv("MILVUS_TOKEN", ""),
        )
    )
    embedding_fn = create_embedding_fn(
        {
            "model": os.getenv("EMBEDDER_MODEL") or "BAAI/bge-m3",
            "api_key": os.getenv("EMBEDDER_API_KEY")
            or os.getenv("LLM_API_KEY")
            or "",
            "api_base": os.getenv("EMBEDDER_API_BASE")
            or "https://api.openai.com/v1",
        }
    )
    try:
        store = EventsStore(
            client=client,
            embedding_fn=embedding_fn,
            embedding_dim=int(os.getenv("EMBEDDING_DIM") or "1024"),
        )
        if args.expired:
            deleted_count = store.cleanup_expired(
                graph_built_retention_days=args.graph_built_retention_days
            )
            print(f"Deleted expired Milvus event rows: {deleted_count}")
        else:
            deleted_count = store.cleanup_duplicate_content(limit=args.limit)
            print(f"Deleted duplicate Milvus event rows: {deleted_count}")
    finally:
        close = getattr(client, "close", None)
        if close is not None:
            close()


if __name__ == "__main__":
    main()
