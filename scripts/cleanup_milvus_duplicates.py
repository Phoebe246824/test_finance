"""Delete duplicate Milvus stash rows with the same raw content."""

from __future__ import annotations

import sys
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from blacklist.milvus_stash import MilvusStashStore  # noqa: E402


def main() -> None:
    load_dotenv(ROOT / ".env")
    store = MilvusStashStore(
        collection_name=os.getenv("MILVUS_STASH_COLLECTION") or "stashed_events",
        embedding_dim=int(os.getenv("EMBEDDING_DIM") or "1024"),
    )
    deleted_count = store.cleanup_duplicate_content()
    print(f"Deleted duplicate Milvus stash rows: {deleted_count}")


if __name__ == "__main__":
    main()
