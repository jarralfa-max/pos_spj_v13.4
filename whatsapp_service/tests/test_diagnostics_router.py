# tests/test_diagnostics_router.py — WA-20
"""`GET /diagnostics` end-to-end: auth real (WA-1) + FastAPI `TestClient`
+ `DiagnosticsService` real sobre SQLite real."""
from __future__ import annotations

import sqlite3
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from application.diagnostics_service import DiagnosticsService
from backend.infrastructure.db.schema.whatsapp_schema import create_whatsapp_schema
from middleware import service_auth
from middleware.service_auth import sign_request
from router.diagnostics_router import router as diagnostics_router

SECRET = "test-internal-key"


class _FakeRegistry:
    def __init__(self, conn):
        self._conn = conn

    def get(self, name):
        return self._conn


class _FakeRoot:
    def __init__(self, conn):
        self.registry = _FakeRegistry(conn)
        self.diagnostics_service = DiagnosticsService(self)


@pytest.fixture(autouse=True)
def _reset_nonce_cache():
    service_auth.reset_nonce_cache()
    yield
    service_auth.reset_nonce_cache()


def _signed_headers(body: bytes, *, nonce="nonce-1"):
    ts = str(int(time.time()))
    sig = sign_request("erp-core", ts, nonce, body, SECRET)
    return {"X-Service-Id": "erp-core", "X-Timestamp": ts, "X-Nonce": nonce, "X-Signature": sig}


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr("config.settings.get_internal_api_key", lambda: SECRET)
    monkeypatch.setattr("config.settings.is_production", lambda: False)

    connection = sqlite3.connect(":memory:", check_same_thread=False)
    create_whatsapp_schema(connection)

    app = FastAPI()
    app.include_router(diagnostics_router)
    app.state.composition_root = _FakeRoot(connection)

    with TestClient(app) as test_client:
        yield test_client
    connection.close()


class TestDiagnosticsEndpoint:
    def test_returns_metrics_shape(self, client):
        resp = client.get("/diagnostics", headers=_signed_headers(b""))
        assert resp.status_code == 200
        data = resp.json()
        assert "conversations" in data
        assert "outbox" in data
        assert "handoff" in data

    def test_rejects_unsigned_request(self, client):
        resp = client.get("/diagnostics")
        assert resp.status_code in (401, 403)
