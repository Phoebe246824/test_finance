from __future__ import annotations

from pymilvus import DataType

from blacklist.milvus_client import (
    MilvusConfig,
    create_milvus_client,
    milvus_config_from_app,
)
from blacklist.stores.base import FieldSpec, MilvusBaseStore
from blacklist.stores.factory import (
    events_collection_from_config,
    milvus_collection_names,
)
from tests.fakes.fake_milvus import FakeMilvusClient


class DummyStore(MilvusBaseStore):
    collection_name = "dummy_collection"
    primary_field = "dummy_id"
    vector_field = ""

    def fields(self) -> list[FieldSpec]:
        return [
            FieldSpec("dummy_id", DataType.VARCHAR, is_primary=True, max_length=64),
            FieldSpec("name", DataType.VARCHAR, max_length=256),
            FieldSpec("enabled", DataType.BOOL),
        ]


def test_milvus_config_from_app_uses_config_values() -> None:
    config = {"milvus": {"uri": "http://milvus:19530", "token": "abc"}}

    result = milvus_config_from_app(config)

    assert result == MilvusConfig(uri="http://milvus:19530", token="abc")


def test_milvus_config_from_app_falls_back_to_env(monkeypatch) -> None:
    monkeypatch.setenv("MILVUS_URI", "http://env-milvus:19530")
    monkeypatch.setenv("MILVUS_TOKEN", "env-token")

    result = milvus_config_from_app({})

    assert result == MilvusConfig(uri="http://env-milvus:19530", token="env-token")


def test_events_collection_from_config_prefers_config_over_env(monkeypatch) -> None:
    monkeypatch.setenv("MILVUS_STASH_COLLECTION", "env_events")

    result = events_collection_from_config(
        {"milvus": {"stash_collection": "configured_events"}}
    )

    assert result == "configured_events"


def test_milvus_collection_names_include_configured_and_default_events() -> None:
    result = milvus_collection_names({"milvus": {"stash_collection": "risk_events"}})

    assert result == (
        "blacklist_event_samples",
        "blacklist_keywords",
        "blacklist_persons",
        "events",
        "review_actions",
        "risk_events",
    )


def test_create_milvus_client_passes_uri_and_token(monkeypatch) -> None:
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("blacklist.milvus_client.MilvusClient", FakeClient)

    create_milvus_client(MilvusConfig(uri="http://127.0.0.1:19530", token="secret"))

    assert captured == {"uri": "http://127.0.0.1:19530", "token": "secret"}


def test_create_milvus_client_omits_empty_token(monkeypatch) -> None:
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("blacklist.milvus_client.MilvusClient", FakeClient)

    create_milvus_client(MilvusConfig(uri="http://127.0.0.1:19530", token=""))

    assert captured == {"uri": "http://127.0.0.1:19530"}


def test_base_store_creates_collection_once_with_schema() -> None:
    client = FakeMilvusClient()
    store = DummyStore(client=client)

    store.ensure_collection()
    store.ensure_collection()

    assert len(client.create_calls) == 1
    assert client.create_calls[0]["collection_name"] == "dummy_collection"
    schema = client.create_calls[0]["schema"]
    field_names = [field.name for field in schema.fields]
    assert field_names == ["dummy_id", "name", "enabled", "_storage_vector"]


def test_base_store_adds_internal_vector_for_scalar_only_rows() -> None:
    client = FakeMilvusClient()
    store = DummyStore(client=client)

    count = store.upsert_rows(
        [{"dummy_id": "D001", "name": "demo", "enabled": True}]
    )

    assert count == 1
    assert client.rows["dummy_collection"]["D001"]["_storage_vector"] == [0.0, 0.0]
    index_params = client.index_params["dummy_collection"]
    assert index_params is not None
