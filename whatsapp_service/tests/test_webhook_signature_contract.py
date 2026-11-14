"""SDLC-WA-002: contrato que no debe moverse.

Con secreto configurado, una firma inválida o ausente da 403 en los dos
webhooks, en cualquier entorno y aunque se haya pedido el opt-in de
`WA_ALLOW_UNSIGNED_WEBHOOKS`. El opt-in sólo cubre la ausencia de secreto,
nunca una firma mala.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from whatsapp_service.webhook import mercadopago as mp_webhook
from whatsapp_service.webhook import whatsapp as wa_webhook

ENVIRONMENTS = (None, "development", "test", "production")
OPT_IN = (False, True)


class _RecordingRouter:
    def __init__(self):
        self.calls = []

    async def route(self, msg, cfg):
        self.calls.append(msg)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("APP_ENV", "ENVIRONMENT", "WA_ALLOW_UNSIGNED_WEBHOOKS"):
        monkeypatch.delenv(name, raising=False)


def _configure(monkeypatch, app_env, opt_in):
    if app_env is not None:
        monkeypatch.setenv("APP_ENV", app_env)
    if opt_in:
        monkeypatch.setenv("WA_ALLOW_UNSIGNED_WEBHOOKS", "1")


def _meta_client(monkeypatch):
    monkeypatch.setattr("whatsapp_service.config.settings.get_app_secret", lambda: "meta-secret")
    router = _RecordingRouter()
    monkeypatch.setattr(wa_webhook, "_message_router", router)
    app = FastAPI()
    app.include_router(wa_webhook.router)
    return TestClient(app), router


def _mp_client(monkeypatch):
    monkeypatch.setattr("whatsapp_service.config.settings.get_mp_webhook_secret", lambda: "mp-secret")
    monkeypatch.setattr("whatsapp_service.config.settings.MP_ACCESS_TOKEN", "token", raising=False)

    def _no_http(*args, **kwargs):
        raise AssertionError("no debe consultarse la API de pagos con firma inválida")

    monkeypatch.setattr("httpx.AsyncClient", _no_http)
    app = FastAPI()
    app.include_router(mp_webhook.router)
    return TestClient(app)


@pytest.mark.parametrize("opt_in", OPT_IN)
@pytest.mark.parametrize("app_env", ENVIRONMENTS)
@pytest.mark.parametrize(
    "headers",
    [{}, {"X-Hub-Signature-256": "sha256=deadbeef"}],
    ids=["sin_firma", "firma_invalida"],
)
def test_meta_webhook_rejects_bad_signature_everywhere(monkeypatch, app_env, opt_in, headers):
    _configure(monkeypatch, app_env, opt_in)
    client, router = _meta_client(monkeypatch)

    resp = client.post("/webhook", json={"entry": []}, headers=headers)

    assert resp.status_code == 403
    assert router.calls == []


@pytest.mark.parametrize("opt_in", OPT_IN)
@pytest.mark.parametrize("app_env", ENVIRONMENTS)
@pytest.mark.parametrize(
    "headers",
    [{}, {"x-signature": "ts=1,v1=deadbeef", "x-request-id": "req-1"}],
    ids=["sin_firma", "firma_invalida"],
)
def test_mercadopago_webhook_rejects_bad_signature_everywhere(monkeypatch, app_env, opt_in, headers):
    _configure(monkeypatch, app_env, opt_in)
    client = _mp_client(monkeypatch)

    resp = client.post(
        "/webhook/mercadopago",
        params={"data.id": "123456789"},
        headers=headers,
        json={"action": "payment.created", "data": {"id": "123456789"}},
    )

    assert resp.status_code == 403
