"""Exercise the real ASGI lifespan against isolated databases, never Meta."""
import sqlite3

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    from whatsapp_service.config import settings
    from whatsapp_service.main import app
    db = tmp_path / "erp.db"
    sqlite3.connect(db).close()
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setattr(settings, "ERP_DB_PATH", str(db))
    monkeypatch.setattr(settings, "CONTEXT_DB_PATH", str(tmp_path / "conversations.db"))
    for key in ("WA_ACCESS_TOKEN", "WA_PHONE_NUMBER_ID", "WA_APP_SECRET", "WA_INTERNAL_API_KEY", "MP_ACCESS_TOKEN"):
        monkeypatch.setattr(settings, key, "")
    monkeypatch.setattr(settings, "WA_VERIFY_TOKEN", "test-verification")
    monkeypatch.delenv("WA_INTEGRATION_INSTANCE_ID", raising=False)
    return app, db


def test_real_lifespan_health_docs_and_webhook(runtime):
    app, db = runtime
    with TestClient(app) as client:
        assert client.get("/docs").status_code == 200
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["service"] == "whatsapp-service"
        assert client.get("/webhook", params={"hub.mode":"subscribe", "hub.verify_token":"test-verification", "hub.challenge":"challenge"}).text == "challenge"
        assert client.get("/diagnostics").status_code in (401,403,503)
        assert client.get("/api/delivery/orders/pending").status_code in (401,403,503)
    with pytest.raises(sqlite3.ProgrammingError):
        app.state.erp.db.execute("SELECT 1") if app.state.erp._conn else app.state.store.db.execute("SELECT 1")
    conn = sqlite3.connect(db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "sales" not in tables and "ventas" not in tables


def test_invalid_path_does_not_create_database(runtime, monkeypatch, tmp_path):
    from whatsapp_service.config import settings
    app, _ = runtime
    path = tmp_path / "misspelled.db"
    monkeypatch.setattr(settings, "ERP_DB_PATH", str(path))
    with pytest.raises(RuntimeError, match="database"):
        with TestClient(app):
            pass
    assert not path.exists()


def test_future_schema_version_fails_explicitly(runtime):
    from migrations.whatsapp_runtime import migrate_channel_schema
    app, db = runtime
    conn = sqlite3.connect(db)
    migrate_channel_schema(conn)
    conn.execute("UPDATE whatsapp_runtime_schema SET version=999")
    conn.commit()
    conn.close()
    with pytest.raises(RuntimeError, match="schema version"):
        with TestClient(app):
            pass
