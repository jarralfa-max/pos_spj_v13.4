"""WA-1: HMAC + identidad de servicio para el canal interno
ERP↔microservicio (`middleware.service_auth.require_service_auth`).

Reemplaza la comparación de string plano `X-Internal-Key` (`!=`, no
constant-time, fail-open si la clave no estaba configurada) que
`notify_router.py`/`delivery_router.py` reimplementaban cada uno por su
cuenta (whatsapp_security_audit.md, S1/S2/S3).

También cubre la compatibilidad byte-a-byte entre `sign_request()` (copia
canónica, este módulo) y `_sign_request()` (copia corta del lado ERP en
`pos_spj_v13.4/core/integrations/whatsapp_client.py`) — ambas deben producir
exactamente la misma firma para el mismo input, o el canal se rompe.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from middleware import service_auth
from middleware.service_auth import require_service_auth, sign_request

SECRET = "test-internal-key"


@pytest.fixture(autouse=True)
def _reset_nonce_cache():
    service_auth.reset_nonce_cache()
    yield
    service_auth.reset_nonce_cache()


def _signed_headers(body: bytes = b"{}", *, service_id="erp-core", ts=None,
                     nonce="nonce-1", secret=SECRET):
    timestamp = ts if ts is not None else str(int(time.time()))
    sig = sign_request(service_id, timestamp, nonce, body, secret)
    return {
        "X-Service-Id": service_id,
        "X-Timestamp": timestamp,
        "X-Nonce": nonce,
        "X-Signature": sig,
    }


@pytest.fixture
def app_client(monkeypatch):
    monkeypatch.setattr("config.settings.get_internal_api_key", lambda: SECRET)
    monkeypatch.setattr("config.settings.is_production", lambda: False)
    app = FastAPI()

    @app.post("/protected")
    async def protected(_: None = Depends(require_service_auth)):
        return {"ok": True}

    return TestClient(app)


def test_valid_signed_request_passes(app_client):
    resp = app_client.post("/protected", content=b"{}", headers=_signed_headers())
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_missing_headers_rejected(app_client):
    resp = app_client.post("/protected", content=b"{}")
    assert resp.status_code == 401


def test_bad_signature_rejected(app_client):
    headers = _signed_headers()
    headers["X-Signature"] = "0" * 64
    resp = app_client.post("/protected", content=b"{}", headers=headers)
    assert resp.status_code == 401


def test_wrong_secret_rejected(app_client):
    headers = _signed_headers(secret="not-the-real-secret")
    resp = app_client.post("/protected", content=b"{}", headers=headers)
    assert resp.status_code == 401


def test_stale_timestamp_rejected(app_client):
    old_ts = str(int(time.time()) - 600)  # 10 minutes ago, tolerance is 120s
    headers = _signed_headers(ts=old_ts)
    resp = app_client.post("/protected", content=b"{}", headers=headers)
    assert resp.status_code == 401


def test_invalid_timestamp_format_rejected(app_client):
    headers = _signed_headers(ts="not-a-number")
    resp = app_client.post("/protected", content=b"{}", headers=headers)
    assert resp.status_code == 401


def test_replayed_nonce_rejected(app_client):
    headers = _signed_headers(nonce="dup-nonce")

    resp1 = app_client.post("/protected", content=b"{}", headers=headers)
    assert resp1.status_code == 200

    # Misma request otra vez (mismo nonce+timestamp) — debe rechazarse.
    resp2 = app_client.post("/protected", content=b"{}", headers=headers)
    assert resp2.status_code == 401


def test_body_tamper_invalidates_signature(app_client):
    """La firma cubre el body — cambiarlo sin resignar debe fallar."""
    headers = _signed_headers(body=b'{"phone": "5215500000000"}')
    resp = app_client.post("/protected", content=b'{"phone": "OTHER_NUMBER"}', headers=headers)
    assert resp.status_code == 401


def test_missing_secret_in_production_rejects(monkeypatch):
    monkeypatch.setattr("config.settings.get_internal_api_key", lambda: "")
    monkeypatch.setattr("config.settings.is_production", lambda: True)
    app = FastAPI()

    @app.post("/protected")
    async def protected(_: None = Depends(require_service_auth)):
        return {"ok": True}

    client = TestClient(app)
    resp = client.post("/protected", content=b"{}")
    assert resp.status_code == 503


def test_missing_secret_outside_production_allows_with_warning(monkeypatch):
    monkeypatch.setattr("config.settings.get_internal_api_key", lambda: "")
    monkeypatch.setattr("config.settings.is_production", lambda: False)
    app = FastAPI()

    @app.post("/protected")
    async def protected(_: None = Depends(require_service_auth)):
        return {"ok": True}

    client = TestClient(app)
    resp = client.post("/protected", content=b"{}")
    assert resp.status_code == 200


# ── Compatibilidad cruzada con la copia del lado ERP ──────────────────────────

ERP_ROOT = Path(__file__).resolve().parents[2] / "pos_spj_v13.4"


def test_sign_request_matches_erp_side_copy():
    """`service_auth.sign_request` y `whatsapp_client._sign_request` deben
    producir exactamente la misma firma — si divergen, el canal ERP→WA se
    rompe en producción de forma silenciosa (401 permanente)."""
    if str(ERP_ROOT) not in sys.path:
        sys.path.insert(0, str(ERP_ROOT))
    if str(Path(__file__).resolve().parents[1]) not in sys.path:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    from core.integrations.whatsapp_client import _sign_request as erp_sign_request

    body = b'{"phone": "5215500000000", "message": "hola"}'
    a = sign_request("erp-core", "1700000000", "abc123", body, SECRET)
    b = erp_sign_request("erp-core", "1700000000", "abc123", body, SECRET)
    assert a == b
