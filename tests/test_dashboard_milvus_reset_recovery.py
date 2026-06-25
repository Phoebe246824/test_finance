from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.services import store_provider
from blacklist.stores.event_samples_store import EventSamplesStore
from blacklist.stores.events_store import EventsStore
from blacklist.stores.factory import StoreBundle
from blacklist.stores.keywords_store import KeywordsStore
from blacklist.stores.persons_store import PersonsStore
from blacklist.stores.review_actions_store import ReviewActionsStore
from tests.fakes.fake_milvus import CollectionNotFoundFakeMilvusClient


def fake_embed(text: str) -> list[float]:
    if "分拆" in text:
        return [1.0, 0.0, 0.0]
    return [0.0, 1.0, 0.0]


def real_fake_store_bundle(client: CollectionNotFoundFakeMilvusClient) -> StoreBundle:
    return StoreBundle(
        events=EventsStore(client=client, embedding_fn=fake_embed, embedding_dim=3),
        persons=PersonsStore(client=client, embedding_dim=3),
        keywords=KeywordsStore(client=client, embedding_dim=3),
        event_samples=EventSamplesStore(
            client=client,
            embedding_fn=fake_embed,
            embedding_dim=3,
        ),
        review_actions=ReviewActionsStore(client=client, embedding_dim=3),
    )


def test_dashboard_overview_recovers_after_reset_script_drops_cached_collections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = CollectionNotFoundFakeMilvusClient()
    bundle = real_fake_store_bundle(client)
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setattr(store_provider, "get_store_bundle", lambda: bundle)

    with TestClient(create_app(), raise_server_exceptions=False) as app_client:
        first_response = app_client.get("/api/dashboard/overview")
        for collection_name in list(client.collections):
            client.drop_collection(collection_name)
        reset_response = app_client.get("/api/dashboard/overview")

    assert first_response.status_code == 200
    assert reset_response.status_code == 200
    assert reset_response.json()["metrics"]["total_events"] == 0
    assert reset_response.json()["metrics"]["blacklist_items"] == 0
