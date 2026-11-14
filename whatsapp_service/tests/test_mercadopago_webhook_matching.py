"""SDLC-WA-001: el webhook de MercadoPago casa el pago con la venta correcta.

Antes: sólo procesaba `payment.created`, buscaba la venta `pendiente_wa` más
reciente por sufijo de teléfono, no comparaba el monto, avisaba al cliente
antes de casar el pago, se tragaba los errores y respondía 200 aunque no
hubiera guardado nada. La idempotencia era por venta y monto, así que dos pagos
reales iguales se fundían.

Estas pruebas usan una base en memoria con el esquema del canal, tablas
`ventas`/`clientes` mínimas, un bridge doble y la API de pagos doblada.
"""
from __future__ import annotations

import json
import sqlite3
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.shared.app_paths import LAYOUT_SOURCE, AppPaths
from migrations.whatsapp_runtime import migrate_channel_schema
from whatsapp_service.erp.events import WAEventEmitter
from whatsapp_service.webhook import mercadopago as mp_webhook

SALE_ID = "0192f0a0-0000-7000-8000-000000000001"
OTHER_SALE_ID = "0192f0a0-0000-7000-8000-000000000002"
PHONE = "5215550001111"


class _FakeBridge:
    def __init__(self, db, confirm_result=True):
        self.db = db
        self.confirm_result = confirm_result
        self.confirmed = []

    def confirmar_pago_anticipo(self, venta_id, monto, referencia="", metodo="mercadopago"):
        self.confirmed.append((venta_id, monto, referencia, metodo))
        if self.confirm_result:
            self.db.execute("UPDATE ventas SET estado='confirmada' WHERE id=?", (venta_id,))
            self.db.commit()
        return self.confirm_result


class _PaymentsApi:
    """Doble de `httpx.AsyncClient` para `GET /v1/payments/{id}`."""

    payments: dict = {}
    status_code = 200
    calls: list = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, headers=None):
        type(self).calls.append(url)
        payment_id = url.rsplit("/", 1)[-1]
        body = json.dumps(type(self).payments.get(payment_id, {}))
        return _Response(type(self).status_code, body)


class _Response:
    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text
        self.content = text.encode("utf-8")


@pytest.fixture
def env(monkeypatch):
    for name in ("APP_ENV", "ENVIRONMENT", "MP_SIGNATURE_MAX_AGE_SECONDS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("WA_ALLOW_UNSIGNED_WEBHOOKS", "1")
    monkeypatch.setattr("whatsapp_service.config.settings._APP_PATHS", AppPaths(layout=LAYOUT_SOURCE))
    monkeypatch.setattr("whatsapp_service.config.settings.get_mp_webhook_secret", lambda: "")
    monkeypatch.setattr("whatsapp_service.config.settings.MP_ACCESS_TOKEN", "token", raising=False)

    db = sqlite3.connect(":memory:", check_same_thread=False)
    db.row_factory = sqlite3.Row
    migrate_channel_schema(db)
    db.execute("CREATE TABLE clientes (id TEXT PRIMARY KEY, telefono TEXT)")
    db.execute(
        "CREATE TABLE ventas (id TEXT PRIMARY KEY, folio TEXT, cliente_id TEXT, "
        "total REAL, estado TEXT, fecha TEXT)"
    )
    db.execute("INSERT INTO clientes VALUES ('c1', '5550001111')")
    db.execute("INSERT INTO clientes VALUES ('c2', '5559998888')")
    db.execute(
        "INSERT INTO ventas VALUES (?, 'WA-1', 'c1', 350.5, 'pendiente_wa', '2026-11-01')",
        (SALE_ID,),
    )
    db.execute(
        "INSERT INTO ventas VALUES (?, 'WA-2', 'c1', 350.5, 'pendiente_wa', '2026-11-02')",
        (OTHER_SALE_ID,),
    )
    db.commit()

    bridge = _FakeBridge(db)
    events = WAEventEmitter(db)
    monkeypatch.setattr(mp_webhook, "_erp_bridge", bridge)
    monkeypatch.setattr(mp_webhook, "_events", events)

    _PaymentsApi.payments = {}
    _PaymentsApi.status_code = 200
    _PaymentsApi.calls = []
    monkeypatch.setattr("httpx.AsyncClient", _PaymentsApi)

    notified = []

    async def _notify(phone, folio, monto):
        notified.append((phone, folio, monto))

    monkeypatch.setattr(
        "whatsapp_service.notifications.customer.notificar_pago_recibido", _notify
    )

    app = FastAPI()
    app.include_router(mp_webhook.router)
    client = TestClient(app, raise_server_exceptions=False)
    yield {"client": client, "db": db, "bridge": bridge, "notified": notified}
    db.close()


def _payment(payment_id="9001", ref=f"{SALE_ID}:{PHONE}", amount="350.50",
             status="approved", currency="MXN"):
    _PaymentsApi.payments[payment_id] = {
        "id": payment_id,
        "status": status,
        "external_reference": ref,
        "transaction_amount": float(amount) if amount is not None else None,
        "currency_id": currency,
    }


def _post(env, payment_id="9001", action="payment.updated"):
    return env["client"].post(
        "/webhook/mercadopago",
        params={"data.id": payment_id},
        json={"action": action, "data": {"id": payment_id}},
    )


def _events(env, event_type):
    rows = env["db"].execute(
        "SELECT data_json FROM wa_event_log WHERE event_type=?", (event_type,)
    ).fetchall()
    return [json.loads(r[0]) for r in rows]


def _tray(env):
    return env["db"].execute(
        "SELECT provider_payment_id, reason, amount FROM whatsapp_unmatched_payments"
    ).fetchall()


@pytest.mark.parametrize("action", ["payment.created", "payment.updated"])
def test_approved_payment_confirms_the_referenced_sale(env, action):
    _payment()
    resp = _post(env, action=action)

    assert resp.status_code == 200
    assert env["bridge"].confirmed == [(SALE_ID, Decimal("350.50"), "MP-9001", "mercadopago")]
    assert env["notified"] == [(PHONE, "MP-9001", Decimal("350.50"))]
    received = _events(env, "PAYMENT_RECEIVED")
    assert len(received) == 1
    assert received[0]["venta_id"] == SALE_ID
    assert received[0]["telefono"] == PHONE
    assert _tray(env) == []


def test_repeated_notification_of_the_same_payment_is_applied_once(env):
    _payment()
    assert _post(env).status_code == 200
    assert _post(env, action="payment.created").status_code == 200

    assert len(env["bridge"].confirmed) == 1
    assert len(env["notified"]) == 1
    assert len(_events(env, "PAYMENT_RECEIVED")) == 1
    assert _tray(env) == []


def test_two_real_payments_of_the_same_amount_are_not_merged(env):
    _payment("9001")
    _payment("9002")
    _post(env, "9001")
    _post(env, "9002")

    assert len(env["bridge"].confirmed) == 1
    tray = _tray(env)
    assert [(r[0], r[1]) for r in tray] == [("9002", "venta no pendiente (confirmada)")]


def test_reference_without_sale_does_not_fall_back_to_phone_suffix(env):
    _payment(ref=PHONE)
    resp = _post(env)

    assert resp.status_code == 200
    assert env["bridge"].confirmed == []
    assert env["notified"] == []
    assert _events(env, "PAYMENT_RECEIVED") == []
    assert [r[1] for r in _tray(env)] == ["referencia sin venta"]


@pytest.mark.parametrize(
    "kwargs,reason",
    [
        ({"amount": "175.25"}, "monto no coincide (esperado 350.50, recibido 175.25)"),
        ({"amount": "400.00"}, "monto no coincide (esperado 350.50, recibido 400.00)"),
        ({"currency": "USD"}, "moneda no esperada (USD)"),
        ({"ref": f"{SALE_ID}:5215559998888"}, "teléfono no coincide"),
        ({"ref": "no-existe:5215550001111"}, "venta no encontrada"),
    ],
)
def test_payment_that_does_not_match_goes_to_the_tray(env, kwargs, reason):
    _payment(**kwargs)
    resp = _post(env)

    assert resp.status_code == 200
    assert env["bridge"].confirmed == []
    assert env["notified"] == []
    assert _events(env, "PAYMENT_RECEIVED") == []
    assert [r[1] for r in _tray(env)] == [reason]


def test_unmatched_payment_is_recorded_once(env):
    _payment(amount="1.00")
    _post(env)
    _post(env)
    assert len(_tray(env)) == 1


def test_payment_not_approved_is_ignored(env):
    _payment(status="pending")
    resp = _post(env)

    assert resp.status_code == 200
    assert env["bridge"].confirmed == []
    assert env["notified"] == []
    assert _tray(env) == []


def test_payments_api_failure_asks_for_a_retry(env):
    _payment()
    _PaymentsApi.status_code = 500
    resp = _post(env)

    assert resp.status_code == 502
    assert env["bridge"].confirmed == []
    assert env["notified"] == []


def test_missing_access_token_asks_for_a_retry(env, monkeypatch):
    monkeypatch.setattr("whatsapp_service.config.settings.MP_ACCESS_TOKEN", "", raising=False)
    _payment()
    assert _post(env).status_code == 503
    assert _PaymentsApi.calls == []


def test_invalid_json_is_rejected(env):
    resp = env["client"].post(
        "/webhook/mercadopago", content=b"{no es json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400


def test_oversized_body_is_rejected(env):
    resp = env["client"].post(
        "/webhook/mercadopago", content=b"x" * (mp_webhook.MAX_BODY_BYTES + 1),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 413
    assert _PaymentsApi.calls == []


def test_query_and_body_payment_ids_must_agree(env):
    _payment("9001")
    resp = env["client"].post(
        "/webhook/mercadopago",
        params={"data.id": "9001"},
        json={"action": "payment.updated", "data": {"id": "9999"}},
    )
    assert resp.status_code == 400
    assert _PaymentsApi.calls == []


def test_failed_confirmation_is_not_swallowed_nor_announced(env):
    env["bridge"].confirm_result = False
    _payment()

    resp = _post(env)

    assert resp.status_code == 500
    assert env["notified"] == []
    assert _events(env, "PAYMENT_RECEIVED") == []

    # El reintento del proveedor deja el pago visible en la bandeja.
    assert _post(env).status_code == 200
    assert [r[1] for r in _tray(env)] == ["confirmación falló en un intento anterior"]
    assert env["notified"] == []


def test_lookup_error_is_visible_not_swallowed(env, caplog):
    env["db"].execute("DROP TABLE ventas")
    _payment()

    resp = _post(env)

    assert resp.status_code == 500
    assert env["notified"] == []
    assert "9001" in caplog.text
