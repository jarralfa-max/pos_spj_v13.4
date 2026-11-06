"""WA-1 / S4: los webhooks de Meta y MercadoPago deben fallar CERRADO (503)
en producción si no hay secreto de firma configurado, reemplazando el
fail-open anterior (`if WA_APP_SECRET:` / `if MP_WEBHOOK_SECRET:` que
simplemente omitían la verificación y procesaban igual).

SDLC-WA-002: la regla dejó de depender de `APP_ENV`. Sin secreto el webhook
responde 503 en cualquier entorno; aceptar sin firma exige el opt-in
`WA_ALLOW_UNSIGNED_WEBHOOKS`, válido sólo en una máquina de desarrollo.
"""
from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.shared.app_paths import LAYOUT_INSTALLED, LAYOUT_SOURCE, AppPaths
from whatsapp_service.webhook import mercadopago as mp_webhook
from whatsapp_service.webhook import whatsapp as wa_webhook

_TEXT_PAYLOAD = {
    "entry": [{
        "changes": [{
            "value": {
                "metadata": {"phone_number_id": "pn-1"},
                "messages": [{
                    "id": "wamid-wa-002",
                    "from": "5215550001111",
                    "timestamp": "1700000000",
                    "type": "text",
                    "text": {"body": "hola"},
                }],
            }
        }]
    }]
}
_MP_PAYMENT = {"action": "payment.created", "data": {"id": "123456789"}}


class _RecordingRouter:
    def __init__(self):
        self.calls = []

    async def route(self, msg, cfg):
        self.calls.append(msg)


class _RecordingNumberRouter:
    def route(self, msg):
        return object()


class _RecordingStore:
    def __init__(self):
        self.logged = []

    def is_duplicate(self, message_id):
        return False

    def log_message(self, *args):
        self.logged.append(args)


class _ForbiddenHttpClient:
    constructed = 0

    def __init__(self, *args, **kwargs):
        type(self).constructed += 1
        raise RuntimeError("doble: la API de pagos no se consulta de verdad")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("APP_ENV", "ENVIRONMENT", "WA_ALLOW_UNSIGNED_WEBHOOKS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        "whatsapp_service.config.settings._APP_PATHS", AppPaths(layout=LAYOUT_SOURCE)
    )
    _ForbiddenHttpClient.constructed = 0


@pytest.fixture
def meta(monkeypatch):
    monkeypatch.setattr("whatsapp_service.config.settings.get_app_secret", lambda: "")
    router = _RecordingRouter()
    store = _RecordingStore()
    monkeypatch.setattr(wa_webhook, "_message_router", router)
    monkeypatch.setattr(wa_webhook, "_number_router", _RecordingNumberRouter())
    monkeypatch.setattr(wa_webhook, "_conversation_store", store)
    app = FastAPI()
    app.include_router(wa_webhook.router)
    client = TestClient(app)
    client.router_double = router
    client.store_double = store
    return client


@pytest.fixture
def mp(monkeypatch):
    monkeypatch.setattr("whatsapp_service.config.settings.get_mp_webhook_secret", lambda: "")
    monkeypatch.setattr("whatsapp_service.config.settings.MP_ACCESS_TOKEN", "token", raising=False)
    monkeypatch.setattr("httpx.AsyncClient", _ForbiddenHttpClient)
    app = FastAPI()
    app.include_router(mp_webhook.router)
    return TestClient(app)


def _assert_meta_rejected(meta, caplog):
    with caplog.at_level(logging.ERROR, logger="wa.webhook"):
        resp = meta.post("/webhook", json=_TEXT_PAYLOAD)
    assert resp.status_code == 503
    assert meta.router_double.calls == []
    assert meta.store_double.logged == []
    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert any("WA_APP_SECRET" in message for message in errors)
    return errors


def _assert_mp_rejected(mp, caplog):
    with caplog.at_level(logging.ERROR, logger="wa.webhook.mp"):
        resp = mp.post("/webhook/mercadopago", json=_MP_PAYMENT)
    assert resp.status_code == 503
    assert _ForbiddenHttpClient.constructed == 0
    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert any("MP_WEBHOOK_SECRET" in message for message in errors)
    return errors


@pytest.mark.parametrize("app_env", [None, "development", "test", "prd"])
def test_whatsapp_webhook_rejects_without_secret_nor_opt_in(meta, caplog, monkeypatch, app_env):
    """SDLC-WA-002, criterios 1 y 2."""
    if app_env is not None:
        monkeypatch.setenv("APP_ENV", app_env)
    _assert_meta_rejected(meta, caplog)


@pytest.mark.parametrize("app_env", [None, "development", "test", "prd"])
def test_mercadopago_webhook_rejects_without_secret_nor_opt_in(mp, caplog, monkeypatch, app_env):
    """SDLC-WA-002, criterios 1 y 2."""
    if app_env is not None:
        monkeypatch.setenv("APP_ENV", app_env)
    _assert_mp_rejected(mp, caplog)


def test_whatsapp_webhook_with_opt_in_reaches_the_router(meta, caplog, monkeypatch):
    """SDLC-WA-002, criterio 3."""
    monkeypatch.setenv("WA_ALLOW_UNSIGNED_WEBHOOKS", "1")
    with caplog.at_level(logging.WARNING, logger="wa.webhook"):
        resp = meta.post("/webhook", json=_TEXT_PAYLOAD)
    assert resp.status_code == 200
    assert len(meta.router_double.calls) == 1
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_mercadopago_webhook_with_opt_in_queries_the_payment(mp, caplog, monkeypatch):
    """SDLC-WA-002, criterio 3: pasa de la firma y llega a la API de pagos."""
    monkeypatch.setenv("WA_ALLOW_UNSIGNED_WEBHOOKS", "1")
    with caplog.at_level(logging.WARNING, logger="wa.webhook.mp"):
        mp.post("/webhook/mercadopago", json=_MP_PAYMENT)
    assert _ForbiddenHttpClient.constructed == 1
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_whatsapp_webhook_ignores_opt_in_in_production(meta, caplog, monkeypatch):
    """SDLC-WA-002, criterio 4."""
    monkeypatch.setenv("WA_ALLOW_UNSIGNED_WEBHOOKS", "1")
    monkeypatch.setenv("APP_ENV", "production")
    errors = _assert_meta_rejected(meta, caplog)
    assert any("se ignoró por producción" in message for message in errors)


def test_mercadopago_webhook_ignores_opt_in_in_production(mp, caplog, monkeypatch):
    """SDLC-WA-002, criterio 4."""
    monkeypatch.setenv("WA_ALLOW_UNSIGNED_WEBHOOKS", "1")
    monkeypatch.setenv("APP_ENV", "production")
    errors = _assert_mp_rejected(mp, caplog)
    assert any("se ignoró por producción" in message for message in errors)


def test_whatsapp_webhook_ignores_opt_in_on_installed_station(meta, caplog, monkeypatch):
    """SDLC-WA-002, criterio 5."""
    monkeypatch.setenv("WA_ALLOW_UNSIGNED_WEBHOOKS", "1")
    monkeypatch.setattr(
        "whatsapp_service.config.settings._APP_PATHS", AppPaths(layout=LAYOUT_INSTALLED)
    )
    errors = _assert_meta_rejected(meta, caplog)
    assert any("se ignoró por estación instalada" in message for message in errors)


def test_mercadopago_webhook_ignores_opt_in_on_installed_station(mp, caplog, monkeypatch):
    """SDLC-WA-002, criterio 5."""
    monkeypatch.setenv("WA_ALLOW_UNSIGNED_WEBHOOKS", "1")
    monkeypatch.setattr(
        "whatsapp_service.config.settings._APP_PATHS", AppPaths(layout=LAYOUT_INSTALLED)
    )
    errors = _assert_mp_rejected(mp, caplog)
    assert any("se ignoró por estación instalada" in message for message in errors)


def test_whatsapp_webhook_rejects_when_secret_missing_in_production(monkeypatch):
    monkeypatch.setattr("whatsapp_service.config.settings.get_app_secret", lambda: "")
    monkeypatch.setattr("whatsapp_service.config.settings.is_production", lambda: True)
    app = FastAPI()
    app.include_router(wa_webhook.router)
    client = TestClient(app)

    resp = client.post("/webhook", json={"entry": []})

    assert resp.status_code == 503


def test_whatsapp_webhook_allows_with_warning_outside_production(monkeypatch):
    monkeypatch.setattr("whatsapp_service.config.settings.get_app_secret", lambda: "")
    monkeypatch.setattr("whatsapp_service.config.settings.is_production", lambda: False)
    monkeypatch.setenv("WA_ALLOW_UNSIGNED_WEBHOOKS", "1")
    app = FastAPI()
    app.include_router(wa_webhook.router)
    client = TestClient(app)

    resp = client.post("/webhook", json={"entry": []})

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_mercadopago_webhook_rejects_when_secret_missing_in_production(monkeypatch):
    monkeypatch.setattr("whatsapp_service.config.settings.get_mp_webhook_secret", lambda: "")
    monkeypatch.setattr("whatsapp_service.config.settings.is_production", lambda: True)
    app = FastAPI()
    app.include_router(mp_webhook.router)
    client = TestClient(app)

    resp = client.post(
        "/webhook/mercadopago",
        json={"action": "payment.updated", "data": {"id": "1"}},
    )

    assert resp.status_code == 503


def test_mercadopago_webhook_allows_with_warning_outside_production(monkeypatch):
    monkeypatch.setattr("whatsapp_service.config.settings.get_mp_webhook_secret", lambda: "")
    monkeypatch.setattr("whatsapp_service.config.settings.is_production", lambda: False)
    monkeypatch.setenv("WA_ALLOW_UNSIGNED_WEBHOOKS", "1")
    app = FastAPI()
    app.include_router(mp_webhook.router)
    client = TestClient(app)

    resp = client.post(
        "/webhook/mercadopago",
        json={"action": "payment.updated", "data": {"id": "1"}},
    )

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
