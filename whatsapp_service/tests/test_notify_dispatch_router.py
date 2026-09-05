# tests/test_notify_dispatch_router.py — WA-18
"""Endpoints `/api/notify/v2/*` end-to-end: auth real (WA-1) + FastAPI
`TestClient` + `NotificationService` real sobre SQLite real — solo el
`ProviderGateway` es falso (WA-5, contrato ya probado en WA-5)."""
from __future__ import annotations

import sqlite3
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from application.notification_service import NotificationService
from application.outbound_message_service import OutboundMessageService
from backend.infrastructure.db.schema.whatsapp_schema import create_whatsapp_schema
from infrastructure.persistence.sqlite_outbox_repository import SqliteWhatsAppOutboxRepository
from infrastructure.webhooks.outbound_dispatcher import OutboundDispatcher
from middleware import service_auth
from middleware.service_auth import sign_request
from router.notify_dispatch_router import router as notify_dispatch_router

SECRET = "test-internal-key"


class _FakeProviderGateway:
    def __init__(self):
        self.text_calls = []

    async def send_text(self, *, to, body):
        self.text_calls.append((to, body))
        return {"ok": True}


class _FakeRoot:
    def __init__(self, conn):
        self.outbox = SqliteWhatsAppOutboxRepository(conn)
        self.provider_gateway = _FakeProviderGateway()
        self.outbound_message_service = OutboundMessageService(self)
        self.outbound_dispatcher = OutboundDispatcher(self)
        self.notification_service = NotificationService(self)


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

    # `check_same_thread=False`: TestClient corre el app en un thread
    # distinto al de este fixture (Starlette lo despacha vía threadpool).
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    create_whatsapp_schema(connection)

    app = FastAPI()
    app.include_router(notify_dispatch_router)
    app.state.composition_root = _FakeRoot(connection)

    with TestClient(app) as test_client:
        yield test_client
    connection.close()


class TestPedidoListo:
    def test_sends_and_returns_ok(self, client):
        body = b'{"phone": "+525512345678", "folio": "F-001", "sucursal": "Centro"}'
        resp = client.post("/api/notify/v2/pedido-listo", content=body, headers=_signed_headers(body))
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["status"] == "SENT"

    def test_rejects_unsigned_request(self, client):
        resp = client.post(
            "/api/notify/v2/pedido-listo",
            json={"phone": "+525512345678", "folio": "F-001"},
        )
        assert resp.status_code in (401, 403)


class TestAnticipoRequerido:
    def test_sends_and_returns_ok(self, client):
        body = b'{"phone": "+525512345678", "folio": "F-001", "monto": 150.5}'
        resp = client.post("/api/notify/v2/anticipo", content=body, headers=_signed_headers(body))
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


class TestCotizacionLista:
    def test_sends_and_returns_ok(self, client):
        body = b'{"phone": "+525512345678", "folio": "C-001", "total": 980.0}'
        resp = client.post("/api/notify/v2/cotizacion", content=body, headers=_signed_headers(body))
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


class TestSendMessage:
    def test_sends_free_text(self, client):
        body = b'{"phone": "+525512345678", "message": "Hola"}'
        resp = client.post("/api/notify/v2/send", content=body, headers=_signed_headers(body))
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
