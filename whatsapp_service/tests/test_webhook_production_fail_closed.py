"""WA-1 / S4: los webhooks de Meta y MercadoPago deben fallar CERRADO (503)
en producción si no hay secreto de firma configurado, reemplazando el
fail-open anterior (`if WA_APP_SECRET:` / `if MP_WEBHOOK_SECRET:` que
simplemente omitían la verificación y procesaban igual).

Fuera de producción se conserva el comportamiento de conveniencia para
desarrollo local: advertir y continuar sin verificar firma.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from webhook import mercadopago as mp_webhook
from webhook import whatsapp as wa_webhook


def test_whatsapp_webhook_rejects_when_secret_missing_in_production(monkeypatch):
    monkeypatch.setattr("config.settings.get_app_secret", lambda: "")
    monkeypatch.setattr("config.settings.is_production", lambda: True)
    app = FastAPI()
    app.include_router(wa_webhook.router)
    client = TestClient(app)

    resp = client.post("/webhook", json={"entry": []})

    assert resp.status_code == 503


def test_whatsapp_webhook_allows_with_warning_outside_production(monkeypatch):
    monkeypatch.setattr("config.settings.get_app_secret", lambda: "")
    monkeypatch.setattr("config.settings.is_production", lambda: False)
    app = FastAPI()
    app.include_router(wa_webhook.router)
    client = TestClient(app)

    resp = client.post("/webhook", json={"entry": []})

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_mercadopago_webhook_rejects_when_secret_missing_in_production(monkeypatch):
    monkeypatch.setattr("config.settings.get_mp_webhook_secret", lambda: "")
    monkeypatch.setattr("config.settings.is_production", lambda: True)
    app = FastAPI()
    app.include_router(mp_webhook.router)
    client = TestClient(app)

    resp = client.post(
        "/webhook/mercadopago",
        json={"action": "payment.updated", "data": {"id": "1"}},
    )

    assert resp.status_code == 503


def test_mercadopago_webhook_allows_with_warning_outside_production(monkeypatch):
    monkeypatch.setattr("config.settings.get_mp_webhook_secret", lambda: "")
    monkeypatch.setattr("config.settings.is_production", lambda: False)
    app = FastAPI()
    app.include_router(mp_webhook.router)
    client = TestClient(app)

    resp = client.post(
        "/webhook/mercadopago",
        json={"action": "payment.updated", "data": {"id": "1"}},
    )

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
