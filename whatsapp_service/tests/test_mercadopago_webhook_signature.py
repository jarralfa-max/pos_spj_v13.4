"""SET-1: MercadoPago webhook must reject notifications with an invalid
or missing X-Signature when MP_WEBHOOK_SECRET is configured.

Regression coverage for the gap found during the Settings/Integrations
SET-0 audit: `webhook/mercadopago.py::mp_notification` previously accepted
any POST body unconditionally, and the already-defined `MP_WEBHOOK_SECRET`
config value was never read.

WA-1: also covers `verify_mp_signature`'s replay-window check (`ts` too old
is rejected even with a valid HMAC — whatsapp_security_audit.md S9).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from whatsapp_service.middleware.hmac_validator import verify_mp_signature
from whatsapp_service.webhook import mercadopago as mp_webhook

SECRET = "test-mp-webhook-secret"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in (
        "APP_ENV",
        "ENVIRONMENT",
        "WA_ALLOW_UNSIGNED_WEBHOOKS",
        "MP_SIGNATURE_MAX_AGE_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)


def _now_ms() -> str:
    return str(int(time.time() * 1000))


def _now_s() -> str:
    return str(int(time.time()))


def _sign(data_id: str, request_id: str, ts: str, secret: str = SECRET) -> str:
    manifest = f"id:{data_id.lower()};request-id:{request_id};ts:{ts};"
    v1 = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return f"ts={ts},v1={v1}"


def test_verify_mp_signature_accepts_correctly_signed_manifest():
    sig = _sign("123456789", "req-1", _now_ms())
    assert verify_mp_signature(sig, "req-1", "123456789", SECRET) is True


def test_verify_mp_signature_rejects_wrong_secret():
    sig = _sign("123456789", "req-1", _now_ms(), secret="other-secret")
    assert verify_mp_signature(sig, "req-1", "123456789", SECRET) is False


def test_verify_mp_signature_rejects_tampered_request_id():
    sig = _sign("123456789", "req-1", _now_ms())
    assert verify_mp_signature(sig, "req-DIFFERENT", "123456789", SECRET) is False


def test_verify_mp_signature_rejects_malformed_header():
    assert verify_mp_signature("not-a-valid-header", "req-1", "123456789", SECRET) is False
    assert verify_mp_signature("", "req-1", "123456789", SECRET) is False


def test_verify_mp_signature_rejects_empty_secret():
    sig = _sign("123456789", "req-1", _now_ms())
    assert verify_mp_signature(sig, "req-1", "123456789", "") is False


def test_verify_mp_signature_rejects_old_timestamp_even_if_validly_signed():
    """WA-1 / S9: a captured-and-replayed request with a valid HMAC but an
    old `ts` must be rejected — the manifest signature alone doesn't bound
    replay."""
    old_ts = str(int(time.time() * 1000) - (600 * 1000))  # 10 minutes ago
    sig = _sign("123456789", "req-1", old_ts)
    assert verify_mp_signature(sig, "req-1", "123456789", SECRET, max_age_seconds=300) is False


def test_verify_mp_signature_accepts_old_timestamp_within_custom_max_age():
    old_ts = str(int(time.time() * 1000) - (600 * 1000))  # 10 minutes ago
    sig = _sign("123456789", "req-1", old_ts)
    assert verify_mp_signature(sig, "req-1", "123456789", SECRET, max_age_seconds=3600) is True


def test_verify_mp_signature_accepts_current_ts_in_seconds():
    """SDLC-WA-002: la documentación muestra `ts` de 10 dígitos (segundos)."""
    ts = _now_s()
    assert len(ts) == 10
    assert verify_mp_signature(_sign("123", "req-1", ts), "req-1", "123", SECRET) is True


def test_verify_mp_signature_accepts_current_ts_in_milliseconds():
    ts = _now_ms()
    assert len(ts) == 13
    assert verify_mp_signature(_sign("123", "req-1", ts), "req-1", "123", SECRET) is True


@pytest.mark.parametrize(
    "ts",
    [
        str(int(time.time()) - 600),
        str(int(time.time()) + 600),
        str(int(time.time() * 1000) - 600_000),
        str(int(time.time() * 1000) + 600_000),
    ],
    ids=["segundos_viejo", "segundos_futuro", "ms_viejo", "ms_futuro"],
)
def test_verify_mp_signature_rejects_both_units_outside_window(ts, caplog):
    with caplog.at_level(logging.WARNING, logger="wa.hmac"):
        assert verify_mp_signature(_sign("123", "req-1", ts), "req-1", "123", SECRET) is False
    assert "ts fuera de ventana" in caplog.text
    assert "firma no coincide" not in caplog.text


def test_verify_mp_signature_rejects_microseconds_closed():
    """Otra escala cae fuera de ventana: falla cerrado, no abierto."""
    ts = str(int(time.time() * 1_000_000))
    assert verify_mp_signature(_sign("123", "req-1", ts), "req-1", "123", SECRET) is False


def test_verify_mp_signature_rejects_non_numeric_ts(caplog):
    with caplog.at_level(logging.WARNING, logger="wa.hmac"):
        assert verify_mp_signature(_sign("123", "req-1", "abc"), "req-1", "123", SECRET) is False
    assert "ts no numérico" in caplog.text


def test_verify_mp_signature_logs_bad_signature_apart_from_age(caplog):
    sig = _sign("123", "req-1", _now_ms(), secret="other-secret")
    with caplog.at_level(logging.WARNING, logger="wa.hmac"):
        assert verify_mp_signature(sig, "req-1", "123", SECRET) is False
    assert "firma no coincide" in caplog.text
    assert "ts fuera de ventana" not in caplog.text


def test_verify_mp_signature_never_logs_the_secret(caplog):
    sig = _sign("123", "req-1", _now_ms(), secret="other-secret")
    with caplog.at_level(logging.DEBUG, logger="wa.hmac"):
        verify_mp_signature(sig, "req-1", "123", SECRET)
    assert SECRET not in caplog.text
    assert "other-secret" not in caplog.text


@pytest.fixture
def app_client():
    app = FastAPI()
    app.include_router(mp_webhook.router)
    return TestClient(app)


def test_webhook_rejects_missing_signature_when_secret_configured(app_client, monkeypatch):
    monkeypatch.setattr("whatsapp_service.config.settings.get_mp_webhook_secret", lambda: SECRET)
    resp = app_client.post(
        "/webhook/mercadopago",
        params={"data.id": "123456789"},
        json={"action": "payment.created", "data": {"id": "123456789"}},
    )
    assert resp.status_code == 403


def test_webhook_rejects_invalid_signature_when_secret_configured(app_client, monkeypatch):
    monkeypatch.setattr("whatsapp_service.config.settings.get_mp_webhook_secret", lambda: SECRET)
    resp = app_client.post(
        "/webhook/mercadopago",
        params={"data.id": "123456789"},
        headers={"x-signature": "ts=1,v1=deadbeef", "x-request-id": "req-1"},
        json={"action": "payment.created", "data": {"id": "123456789"}},
    )
    assert resp.status_code == 403


def test_webhook_accepts_valid_signature_and_ignores_non_payment_action(app_client, monkeypatch):
    monkeypatch.setattr("whatsapp_service.config.settings.get_mp_webhook_secret", lambda: SECRET)
    sig = _sign("123456789", "req-1", _now_ms())
    resp = app_client.post(
        "/webhook/mercadopago",
        params={"data.id": "123456789"},
        headers={"x-signature": sig, "x-request-id": "req-1"},
        json={"action": "payment.updated", "data": {"id": "123456789"}},
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_webhook_falls_back_to_unsigned_when_secret_not_configured(app_client, monkeypatch):
    monkeypatch.setattr("whatsapp_service.config.settings.get_mp_webhook_secret", lambda: "")
    monkeypatch.setenv("WA_ALLOW_UNSIGNED_WEBHOOKS", "1")
    resp = app_client.post(
        "/webhook/mercadopago",
        json={"action": "payment.updated", "data": {"id": "123456789"}},
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_webhook_rejects_unsigned_when_secret_not_configured_without_opt_in(app_client, monkeypatch):
    """SDLC-WA-002: par del anterior; sin opt-in no hay camino sin firma."""
    monkeypatch.setattr("whatsapp_service.config.settings.get_mp_webhook_secret", lambda: "")
    resp = app_client.post(
        "/webhook/mercadopago",
        json={"action": "payment.updated", "data": {"id": "123456789"}},
    )
    assert resp.status_code == 503


def test_webhook_uses_the_configured_replay_window(app_client, monkeypatch):
    """SDLC-WA-002, D2: la ventana configurada llega al validador."""
    monkeypatch.setattr("whatsapp_service.config.settings.get_mp_webhook_secret", lambda: SECRET)
    old_ts = str(int(time.time()) - 600)
    sig = _sign("123456789", "req-1", old_ts)
    body = {"action": "payment.updated", "data": {"id": "123456789"}}
    request = {
        "params": {"data.id": "123456789"},
        "headers": {"x-signature": sig, "x-request-id": "req-1"},
        "json": body,
    }

    assert app_client.post("/webhook/mercadopago", **request).status_code == 403

    monkeypatch.setenv("MP_SIGNATURE_MAX_AGE_SECONDS", "900")
    assert app_client.post("/webhook/mercadopago", **request).status_code == 200
