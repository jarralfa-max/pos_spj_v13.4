"""SDLC-ORD-002 — ningún outbox con consumidores locales se queda sin drenar.

Medido el 2026-11-06 con el cableado real: de los eventos de CRM, clientes,
cotizaciones, tarjetas, sorteos, atención a clientes y privacidad, NINGUNO tiene
suscriptor en el bus. Esos outbox son sólo-replicación, y aquí queda fijado: si
alguien suscribe uno de sus eventos, esta prueba exige construirle despachador
en vez de dejar un consumidor que nunca recibe nada.
"""
from __future__ import annotations

import importlib
import json
import sqlite3
from pathlib import Path

import pytest

from backend.bootstrap.wiring.event_wiring import (
    orders_delivery_tick,
    wire_cross_context_events,
)
from backend.domain.orders_delivery.events import DeliveryEvents, OrderEvents, order_event_payload
from backend.infrastructure.db.repositories.orders_delivery.outbox_repository import (
    OrdersDeliveryOutboxRepository,
)
from backend.infrastructure.db.schema.orders_delivery_schema import create_orders_delivery_schema
from backend.infrastructure.sync.replication_sources import (
    DEFAULT_SOURCES,
    REPLICATION_ONLY_OUTBOXES,
)
from backend.shared.events.application_bus import ApplicationEventBus, get_bus, reset_bus
from backend.shared.ids import new_uuid
from tests.integration._audit_trail_table import create_audit_logs_table

RAIZ = Path(__file__).resolve().parents[3]

#: Tabla sólo-replicación → contexto dueño de sus eventos.
_CONTEXTOS = {
    "crm_outbox": "crm",
    "customer_outbox": "customers",
    "quote_outbox": "quotes",
    "loyalty_cards_outbox": "loyalty_cards",
    "sweepstakes_outbox": "sweepstakes",
    "customer_service_outbox": "customer_service",
    "customer_privacy_outbox": "customer_privacy",
}


@pytest.fixture(autouse=True)
def _bus_aislado():
    reset_bus()
    yield
    reset_bus()


def _eventos(contexto: str) -> set[str]:
    modulo = importlib.import_module(f"backend.domain.{contexto}.events")
    nombres: set[str] = set()
    for valor in vars(modulo).values():
        if isinstance(valor, type) and valor.__module__ == modulo.__name__:
            nombres.update(v for k, v in vars(valor).items()
                           if k.isupper() and isinstance(v, str))
    return nombres


def test_los_sin_consumidor_estan_declarados_y_replican():
    assert REPLICATION_ONLY_OUTBOXES == frozenset(_CONTEXTOS)
    assert REPLICATION_ONLY_OUTBOXES <= {fuente.table for fuente in DEFAULT_SOURCES}


@pytest.mark.parametrize("tabla, contexto", sorted(_CONTEXTOS.items()))
def test_un_outbox_solo_replicacion_no_tiene_suscriptores(tabla, contexto):
    conn = sqlite3.connect(":memory:")
    try:
        wire_cross_context_events(conn)
        bus = get_bus()
        suscritos = {e for e in _eventos(contexto) if bus.subscriptions_for(e)}
    finally:
        conn.close()

    assert suscritos == set(), (
        f"{tabla} tiene consumidores locales y nadie lo despacha: constrúyele despachador "
        "y sácalo de REPLICATION_ONLY_OUTBOXES")


def test_pedidos_tiene_tarea_de_fondo_y_consumidores():
    conn = sqlite3.connect(":memory:")
    try:
        wire_cross_context_events(conn)
        assert get_bus().subscriptions_for(DeliveryEvents.CASH_COLLECTION_RECORDED)
        assert get_bus().subscriptions_for(DeliveryEvents.DRIVER_SETTLEMENT_CLOSED)
    finally:
        conn.close()
    shell = (RAIZ / "frontend/desktop/shell/desktop_shell_window_composition.py"
             ).read_text(encoding="utf-8")
    assert '"orders_delivery.outbox"' in shell


def test_la_tarea_de_pedidos_drena_su_outbox():
    conn = sqlite3.connect(":memory:")
    create_orders_delivery_schema(conn)
    create_audit_logs_table(conn)
    operacion, pedido = new_uuid(), new_uuid()
    sobre = order_event_payload(OrderEvents.CREATED, operation_id=operacion, entity_id=pedido,
                                branch_id=new_uuid(), user_id=new_uuid(), channel="POS")
    OrdersDeliveryOutboxRepository(conn).enqueue(
        event_id=sobre["event_id"], aggregate_type="CustomerOrder", aggregate_id=pedido,
        event_type=OrderEvents.CREATED, payload_json=json.dumps(sobre), operation_id=operacion)
    conn.commit()

    resultado = orders_delivery_tick(conn, ApplicationEventBus())

    assert resultado["dispatched"] == 1
    assert conn.execute("SELECT status FROM orders_delivery_outbox").fetchone()[0] == "DONE"
    conn.close()
