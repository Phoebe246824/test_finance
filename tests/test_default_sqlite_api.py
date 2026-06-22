from fastapi.testclient import TestClient

from backend.app.main import create_app


def test_default_api_uses_sqlite_storage_without_redis(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "sentinel.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.delenv("BLACKLIST_BACKEND", raising=False)
    monkeypatch.delenv("STASH_BACKEND", raising=False)

    with TestClient(create_app()) as client:
        health_response = client.get("/api/system/health")
        persons_response = client.get("/api/blacklist/persons")

    assert health_response.status_code == 200
    assert health_response.json() == {
        "api": True,
        "database": True,
        "blacklist_backend": "sqlite",
        "stash_backend": "sqlite",
    }
    assert persons_response.status_code == 200
    person_values = {item["value"] for item in persons_response.json()["items"]}
    assert {"P05", "P105"}.issubset(person_values)
