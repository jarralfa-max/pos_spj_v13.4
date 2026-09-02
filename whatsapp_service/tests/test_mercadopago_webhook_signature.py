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
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from middleware.hmac_validator import verify_mp_signature
from webhook import mercadopago as mp_webhook

SECRET = "test-mp-webhook-secret"


def _now_ms() -> str:
    return str(int(time.time() * 1000))


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


@pytest.fixture
def app_client():
    app = FastAPI()
    app.include_router(mp_webhook.router)
    return TestClient(app)


def test_webhook_rejects_missing_signature_when_secret_configured(app_client, monkeypatch):
    monkeypatch.setattr("config.settings.MP_WEBHOOK_SECRET", SECRET, raising=False)
    resp = app_client.post(
        "/webhook/mercadopago",
        params={"data.id": "123456789"},
        json={"action": "payment.created", "data": {"id": "123456789"}},
    )
    assert resp.status_code == 403


def test_webhook_rejects_invalid_signature_when_secret_configured(app_client, monkeypatch):
    monkeypatch.setattr("config.settings.MP_WEBHOOK_SECRET", SECRET, raising=False)
    resp = app_client.post(
        "/webhook/mercadopago",
        params={"data.id": "123456789"},
        headers={"x-signature": "ts=1,v1=deadbeef", "x-request-id": "req-1"},
        json={"action": "payment.created", "data": {"id": "123456789"}},
    )
    assert resp.status_code == 403


def test_webhook_accepts_valid_signature_and_ignores_non_payment_action(app_client, monkeypatch):
    monkeypatch.setattr("config.settings.MP_WEBHOOK_SECRET", SECRET, raising=False)
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
    monkeypatch.setattr("config.settings.MP_WEBHOOK_SECRET", "", raising=False)
    resp = app_client.post(
        "/webhook/mercadopago",
        json={"action": "payment.updated", "data": {"id": "123456789"}},
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
