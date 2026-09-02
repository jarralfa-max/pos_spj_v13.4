# tests/test_application_factory.py — WA-4
from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.infrastructure.db.schema.whatsapp_schema import create_whatsapp_schema
from bootstrap.application_factory import WhatsAppApplicationFactory


@pytest.fixture()
def db_path(tmp_path):
    path = str(tmp_path / "wa_test.db")
    conn = sqlite3.connect(path)
    create_whatsapp_schema(conn)
    conn.close()
    return path


class TestWhatsAppApplicationFactory:
    def test_health_endpoint_reports_healthy_database_and_schema(self, db_path):
        app = WhatsAppApplicationFactory(db_path).create()
        with TestClient(app) as client:
            response = client.get("/health")
            assert response.status_code == 200
            body = response.json()
            names_to_status = {c["name"]: c["status"] for c in body["checks"]}
            assert names_to_status["database"] == "HEALTHY"
            assert names_to_status["schema"] == "HEALTHY"

    def test_overall_status_is_present(self, db_path):
        app = WhatsAppApplicationFactory(db_path).create()
        with TestClient(app) as client:
            body = client.get("/health").json()
            assert body["status"] in ("HEALTHY", "DEGRADED", "UNHEALTHY", "UNKNOWN")

    def test_composition_root_connection_is_closed_after_context_exit(self, db_path):
        app = WhatsAppApplicationFactory(db_path).create()
        with TestClient(app):
            root = app.state.composition_root
        conn = root.registry.get("whatsapp_db_connection")
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")
