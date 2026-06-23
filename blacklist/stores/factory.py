from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from blacklist.milvus_client import create_milvus_client, milvus_config_from_app
from blacklist.stores.base import EmbeddingFn
from blacklist.stores.event_samples_store import EventSamplesStore
from blacklist.stores.events_store import EventsStore
from blacklist.stores.keywords_store import KeywordsStore
from blacklist.stores.persons_store import PersonsStore
from blacklist.stores.review_actions_store import ReviewActionsStore


@dataclass(frozen=True, slots=True)
class StoreBundle:
    events: EventsStore
    persons: PersonsStore
    keywords: KeywordsStore
    event_samples: EventSamplesStore
    review_actions: ReviewActionsStore


def create_embedding_fn(config: dict[str, Any]) -> EmbeddingFn:
    from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig

    embedder = OpenAIEmbedder(
        config=OpenAIEmbedderConfig(
            embedding_model=str(config.get("model") or "BAAI/bge-m3"),
            api_key=str(config.get("api_key") or ""),
            base_url=str(config.get("api_base") or "https://api.openai.com/v1"),
        )
    )
    return embedder.create


def create_store_bundle(config: dict[str, Any]) -> StoreBundle:
    client = create_milvus_client(milvus_config_from_app(config))
    milvus_config = config.get("milvus", {})
    embedding_dim = int(milvus_config.get("embedding_dim") or 1024)
    ttl_days = int(milvus_config.get("stash_ttl_days") or 90)
    embedding_fn = create_embedding_fn(config.get("embedder", {}))
    return StoreBundle(
        events=EventsStore(
            client=client,
            embedding_fn=embedding_fn,
            embedding_dim=embedding_dim,
            ttl_days=ttl_days,
            collection_name=str(milvus_config.get("stash_collection") or "events"),
            semantic_score_threshold=float(milvus_config.get("rerank_min_score") or 0.0),
        ),
        persons=PersonsStore(client=client, embedding_dim=embedding_dim),
        keywords=KeywordsStore(client=client, embedding_dim=embedding_dim),
        event_samples=EventSamplesStore(
            client=client,
            embedding_fn=embedding_fn,
            embedding_dim=embedding_dim,
        ),
        review_actions=ReviewActionsStore(client=client, embedding_dim=embedding_dim),
    )
