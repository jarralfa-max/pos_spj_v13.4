"""SDLC-ORD-006 — si WhatsApp falla, el aviso al cliente no se pierde.

Antes era una sola llamada HTTP: si fallaba, un warning en el log y nada más.
Ahora cada aviso queda en `whatsapp_outbox` (decisión del responsable) en la
misma transacción que el hecho, se intenta en seguida y, si falla, se reintenta
con espera creciente hasta agotar los intentos. Uno agotado avisa a la sucursal.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from backend.application.orders_delivery.authorization import OrdersDeliveryAuthorizationPolicy
from backend.application.orders_delivery.use_cases.dispatch_use_cases import (
    DispatchDeliveryJobUseCase,
)
from backend.infrastructure.db.schema.whatsapp_schema import create_whatsapp_schema
from backend.infrastructure.integrations.orders_delivery_notice_outbox import (
    NOTICE_FAILED_ALERT_TYPE,
    OrdersDeliveryNoticeOutbox,
)
from backend.shared.ids import new_uuid
from tests.integration.test_orders_delivery_dispatch_use_cases import (  # noqa: F401 - fixture
    _dispatch_ready_job,
    conn,
)


class _WhatsApp:
    """Cliente falso: falla mientras `caido` sea verdadero."""

    def __init__(self, caido=True):
        self.caido = caido
        self.enviados = []

    def _enviar(self, **datos):
        if self.caido:
            return False
        self.enviados.append(datos)
        return True

    def send_message(self, **datos):
        return self._enviar(**datos)

    def notify_ready_for_pickup(self, **datos):
        return self._enviar(**datos)

    def notify_customer_approval_required(self, **datos):
        return self._enviar(**datos)


def _auth():
    return OrdersDeliveryAuthorizationPolicy.permissive_for_tests()


@pytest.fixture
def db(conn):
    create_whatsapp_schema(conn)
    conn.execute("UPDATE customer_orders SET contact_phone='5512345678'")
    conn.commit()
    return conn


def _despachar(conn, whatsapp):
    job_id, order_id, _ = _dispatch_ready_job(conn)
    conn.execute("UPDATE customer_orders SET contact_phone='5512345678' WHERE id=?",
                 (order_id,))
    conn.commit()
    resultado = DispatchDeliveryJobUseCase(_auth(), whatsapp_client=whatsapp).execute(
        conn, delivery_job_id=job_id, actor_user_id=new_uuid(), operation_id=new_uuid())
    assert resultado.success, resultado.message
    return resultado, order_id


def _avisos(conn):
    return conn.execute(
        "SELECT status, attempts, next_retry_at, payload_json, operation_id"
        " FROM whatsapp_outbox").fetchall()


def test_el_aviso_queda_persistido_aunque_whatsapp_falle(db):
    resultado, _ = _despachar(db, _WhatsApp(caido=True))

    assert resultado.data["notification_sent"] is False
    [(estado, intentos, siguiente, payload, _op)] = _avisos(db)
    assert estado == "PENDING" and intentos == 1 and siguiente
    datos = json.loads(payload)
    assert datos["source"] == "orders_delivery" and "va en camino" in datos["body"]


def test_un_aviso_enviado_queda_como_enviado(db):
    resultado, _ = _despachar(db, _WhatsApp(caido=False))

    assert resultado.data["notification_sent"] is True
    assert _avisos(db)[0][0] == "SENT"


def test_el_reintento_lo_entrega_cuando_whatsapp_vuelve(db):
    whatsapp = _WhatsApp(caido=True)
    _despachar(db, whatsapp)
    db.execute("UPDATE whatsapp_outbox SET next_retry_at=NULL")
    db.commit()
    whatsapp.caido = False

    resultado = OrdersDeliveryNoticeOutbox(db, whatsapp=whatsapp).drain()

    assert resultado["sent"] == 1
    assert _avisos(db)[0][0] == "SENT"
    assert len(whatsapp.enviados) == 1


def test_no_reintenta_antes_de_tiempo(db):
    whatsapp = _WhatsApp(caido=True)
    _despachar(db, whatsapp)
    whatsapp.caido = False

    assert OrdersDeliveryNoticeOutbox(db, whatsapp=whatsapp).drain()["sent"] == 0
    assert whatsapp.enviados == []


def test_agotado_queda_visible_para_la_sucursal(db):
    whatsapp = _WhatsApp(caido=True)
    _, order_id = _despachar(db, whatsapp)
    gerente = new_uuid()
    sucursal = db.execute("SELECT branch_id FROM customer_orders WHERE id=?",
                          (order_id,)).fetchone()[0]
    db.execute("CREATE TABLE IF NOT EXISTS usuarios (id TEXT PRIMARY KEY, rol TEXT,"
               " sucursal_id TEXT, activo INTEGER DEFAULT 1)")
    db.execute("INSERT INTO usuarios (id, rol, sucursal_id, activo) VALUES (?,?,?,1)",
               (gerente, "gerente", sucursal))
    db.execute("CREATE TABLE IF NOT EXISTS notification_inbox (id TEXT PRIMARY KEY,"
               " empleado_id TEXT, tipo TEXT, titulo TEXT, cuerpo TEXT, datos TEXT,"
               " sucursal_id TEXT, leida INTEGER DEFAULT 0, created_at TEXT)")
    db.commit()
    bandeja = OrdersDeliveryNoticeOutbox(db, whatsapp=whatsapp)
    for _ in range(OrdersDeliveryNoticeOutbox.MAX_ATTEMPTS):
        db.execute("UPDATE whatsapp_outbox SET next_retry_at=NULL")
        db.commit()
        bandeja.drain()

    assert _avisos(db)[0][0] == "DEAD_LETTER"
    assert db.execute("SELECT COUNT(*) FROM notification_inbox WHERE tipo=?",
                      (NOTICE_FAILED_ALERT_TYPE,)).fetchone()[0] == 1


def test_un_reintento_de_la_misma_operacion_no_duplica_el_aviso(db):
    bandeja = OrdersDeliveryNoticeOutbox(db, whatsapp=_WhatsApp())
    operacion = new_uuid()
    for _ in range(2):
        bandeja.enqueue(route="send", phone="5512345678", operation_id=operacion,
                        branch_id=new_uuid(), order_id=new_uuid(), message="Hola")
    db.commit()

    assert len(_avisos(db)) == 1
