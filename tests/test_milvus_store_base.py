from __future__ import annotations

from pymilvus import DataType

from blacklist.milvus_client import (
    MilvusConfig,
    create_milvus_client,
    milvus_config_from_app,
)
from blacklist.stores.base import FieldSpec, MilvusBaseStore
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
    assert field_names == ["dummy_id", "name", "enabled"]

