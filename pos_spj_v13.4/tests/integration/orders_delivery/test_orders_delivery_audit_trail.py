"""Pedidos/Reparto: toda escritura deja rastro en `audit_logs`, en la misma transacción.

EL DEFECTO
----------
`record_orders_delivery_audit_entry` existía y ningún caso de uso lo llamaba: la
Auditoría del área no tenía nada que enseñar. Ahora:

- Los casos de uso que emiten evento auditan desde `_emit`/`_emit_delivery`, un solo
  sitio, con la acción = el nombre del evento.
- Los que guardan sin evento (dirección, zonas, rutas, paquetes, reentregas…)
  llaman a `_audit` con una acción propia de `OrdersDeliveryAuditActions`.
- El renglón de auditoría viaja en la transacción del cambio: si no se puede
  escribir, el cambio tampoco se guarda. Una auditoría que se pierde en silencio
  no es auditoría.
"""
from __future__ import annotations

import ast
import json
import pathlib
import sqlite3

import pytest

from backend.application.orders_delivery.audit import (
    ALL_AUDIT_ACTIONS,
    AUDIT_MODULE,
    OrdersDeliveryAuditActions as A,
)
from backend.application.orders_delivery.authorization import OrdersDeliveryAuthorizationPolicy
from backend.application.orders_delivery.permissions import ALL_ORDERS_DELIVERY_PERMISSIONS
from backend.application.orders_delivery.session_authorization import (
    OrdersDeliverySessionPermissionChecker,
)
from backend.application.orders_delivery.use_cases.address_use_cases import (
    SetOrderDeliveryAddressUseCase,
)
from backend.application.orders_delivery.use_cases.order_capture_use_cases import (
    ConfirmCustomerOrderUseCase,
    CreateCustomerOrderUseCase,
)
from backend.application.orders_delivery.use_cases.zone_use_cases import (
    CreateDeliveryZoneUseCase,
)
from backend.domain.orders_delivery.events import (
    ALL_DELIVERY_EVENTS,
    ALL_ORDER_EVENTS,
    OrderEvents,
)
from backend.infrastructure.db.schema.orders_delivery_schema import (
    create_orders_delivery_schema,
)
from backend.shared.ids import new_uuid
from tests.integration._audit_trail_table import create_audit_logs_table
from tests.integration._born_clean_db import make_db

APP = pathlib.Path(__file__).resolve().parents[3]
SUCURSAL = new_uuid()
USUARIO = new_uuid()


class _Sesion:
    is_active = True
    user_id = USUARIO
    active_branch_id = SUCURSAL

    def tiene_permiso(self, code):
        return code in ALL_ORDERS_DELIVERY_PERMISSIONS


POLITICA = OrdersDeliveryAuthorizationPolicy(OrdersDeliverySessionPermissionChecker(_Sesion()))


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_orders_delivery_schema(c)
    create_audit_logs_table(c)
    c.commit()
    yield c
    c.close()


def _renglones(conn, accion=None):
    sql = ("SELECT accion, entidad, entidad_id, usuario, sucursal_id, valor_despues, detalles"
           " FROM audit_logs WHERE modulo=?")
    params: list = [AUDIT_MODULE]
    if accion:
        sql += " AND accion=?"
        params.append(accion)
    return [dict(r) for r in conn.execute(sql + " ORDER BY rowid", params).fetchall()]


def _pedido(conn, *, fulfillment_type="COUNTER"):
    resultado = CreateCustomerOrderUseCase(POLITICA).execute(
        conn, branch_id=SUCURSAL, channel="POS", order_type="STANDARD",
        fulfillment_type=fulfillment_type,
        lines=[{"product_id": new_uuid(), "unit_price": "300.00", "requested_quantity": "1"}],
        actor_user_id=USUARIO, operation_id=new_uuid())
    assert resultado.success, resultado.message
    return resultado.entity_id


def _zona(conn, codigos="06000"):
    return CreateDeliveryZoneUseCase(POLITICA).execute(
        conn, branch_id=SUCURSAL, name=f"Zona {codigos}", postal_codes=codigos,
        minimum_order="0", delivery_fee="35", actor_user_id=USUARIO, operation_id=new_uuid())


# -- la tabla de pruebas es la canónica ----------------------------------------------
def test_the_test_table_matches_the_canonical_migration():
    canonica = make_db()
    prueba = sqlite3.connect(":memory:")
    create_audit_logs_table(prueba)

    def columnas(c):
        return [tuple(r)[1:] for r in c.execute("PRAGMA table_info(audit_logs)").fetchall()]

    assert columnas(prueba) == columnas(canonica)


# -- ningún caso de uso que escribe se queda sin auditar ---------------------------
def test_every_writing_use_case_audits():
    """Sobre el AST: si una clase de caso de uso guarda algo, emite evento o audita.
    Un caso de uso nuevo que olvide ambas cosas falla aquí, no en producción."""
    sin_rastro = []
    carpeta = APP / "backend/application/orders_delivery/use_cases"
    for archivo in sorted(carpeta.glob("*.py")):
        if archivo.name.startswith("_"):
            continue
        texto = archivo.read_text(encoding="utf-8")
        for nodo in ast.parse(texto).body:
            if not isinstance(nodo, ast.ClassDef):
                continue
            fuente = ast.get_source_segment(texto, nodo) or ""
            if ".save(" in fuente and "_emit" not in fuente and "_audit(" not in fuente:
                sin_rastro.append(f"{archivo.name}::{nodo.name}")
    assert not sin_rastro, sin_rastro


def test_every_action_is_known():
    """Las acciones auditables son los eventos más las acciones sin evento; no hay
    dos nombres para lo mismo."""
    propias = {v for k, v in vars(A).items() if k.isupper()}
    assert ALL_AUDIT_ACTIONS == ALL_ORDER_EVENTS | ALL_DELIVERY_EVENTS | propias
    assert not propias & (ALL_ORDER_EVENTS | ALL_DELIVERY_EVENTS)


# -- lo que queda escrito -----------------------------------------------------------------
def test_an_event_is_audited_with_actor_branch_and_entity(conn):
    pedido = _pedido(conn)

    [renglon] = _renglones(conn)

    assert (renglon["accion"], renglon["entidad"], renglon["entidad_id"]) == (
        OrderEvents.CREATED, "CustomerOrder", pedido)
    assert (renglon["usuario"], renglon["sucursal_id"]) == (USUARIO, SUCURSAL)
    assert json.loads(renglon["valor_despues"]) == {"channel": "POS"}
    assert "operation_id" in json.loads(renglon["detalles"])


def test_each_operation_adds_its_own_row(conn):
    pedido = _pedido(conn)
    ConfirmCustomerOrderUseCase(POLITICA).execute(
        conn, order_id=pedido, actor_user_id=USUARIO, operation_id=new_uuid())

    assert [r["accion"] for r in _renglones(conn)] == [OrderEvents.CREATED, OrderEvents.CONFIRMED]


def test_writes_without_an_event_are_audited_too(conn):
    zona = _zona(conn).entity_id
    pedido = _pedido(conn, fulfillment_type="HOME_DELIVERY")

    direccion = SetOrderDeliveryAddressUseCase(POLITICA).execute(
        conn, order_id=pedido, recipient_name="Ana", recipient_phone="5555555555",
        street="Reforma", exterior_number="100", postal_code="06000",
        actor_user_id=USUARIO, operation_id=new_uuid())
    assert direccion.success, direccion.message

    [alta_zona] = _renglones(conn, A.DELIVERY_ZONE_CREATED)
    [alta_direccion] = _renglones(conn, A.ORDER_DELIVERY_ADDRESS_SET)
    assert (alta_zona["entidad"], alta_zona["entidad_id"]) == ("DeliveryZone", zona)
    assert (alta_direccion["entidad"], alta_direccion["entidad_id"]) == ("CustomerOrder", pedido)
    assert json.loads(alta_direccion["valor_despues"])["delivery_fee"] == "35"


def test_a_settlement_event_is_audited_as_the_settlement(conn):
    """El outbox archiva los eventos de liquidación bajo "DeliveryJob", pero su
    entity_id es la liquidación: la auditoría nombra lo que de verdad se tocó."""
    from decimal import Decimal

    from backend.application.orders_delivery.use_cases.settlement_use_cases import (
        CreateDriverSettlementUseCase,
    )
    from backend.domain.orders_delivery.cash_collection import DriverCashCollection
    from backend.domain.orders_delivery.enums import CollectionPaymentMethod
    from backend.infrastructure.db.repositories.orders_delivery.cash_collection_repository import (
        DriverCashCollectionRepository,
    )

    repartidor = new_uuid()
    cobro = DriverCashCollection.create(
        delivery_job_id=new_uuid(), driver_id=repartidor, expected_amount=Decimal("100"),
        payment_method=CollectionPaymentMethod.CASH)
    cobro.record_collection(collected_amount=Decimal("100"))
    cobro.mark_pending_settlement()
    DriverCashCollectionRepository(conn).save(cobro)
    conn.commit()

    liquidacion = CreateDriverSettlementUseCase(POLITICA).execute(
        conn, driver_id=repartidor, branch_id=SUCURSAL, actor_user_id=USUARIO,
        operation_id=new_uuid())

    assert liquidacion.success, liquidacion.message
    [renglon] = _renglones(conn, "DRIVER_SETTLEMENT_CREATED")
    assert (renglon["entidad"], renglon["entidad_id"]) == ("DriverSettlement", liquidacion.entity_id)


def test_a_refused_operation_leaves_no_row(conn):
    assert _zona(conn, "06000").success

    rechazada = _zona(conn, "06000")

    assert rechazada.error_code == "DELIVERY_ZONE_OVERLAP"
    assert len(_renglones(conn, A.DELIVERY_ZONE_CREATED)) == 1


def test_if_the_audit_cannot_be_written_the_change_is_not_saved(conn):
    """Sin la tabla de auditoría la escritura falla y la transacción se revierte:
    no queda un pedido sin rastro."""
    conn.execute("DROP TABLE audit_logs")
    conn.commit()

    with pytest.raises(sqlite3.OperationalError, match="audit_logs"):
        _pedido(conn)

    assert conn.execute("SELECT COUNT(*) FROM customer_orders").fetchone()[0] == 0
