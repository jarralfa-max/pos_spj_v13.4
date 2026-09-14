"""Pedidos/Reparto: los contadores del sidebar llegan a la vista.

`OrdersDeliveryView` aceptaba `badges` y el activator del shell no los pasaba:
ningún contador del módulo se veía, incluidos los que se corrigieron para que
contaran lo mismo que su lista. Aquí se construye la vista por el activator real,
con una sesión, y se lee el texto del sidebar.

La alerta es por persona: el notificador escribe un renglón por destinatario, así
que el contador de la sesión tiene que ser el de SUS alertas sin leer.
"""
from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.orders_delivery.permissions import OrdersDeliveryPermissions as P
from backend.application.orders_delivery.queries.delivery_records_query_service import (
    DeliveryRecord,
    DeliveryRecordsQueryService,
)
from backend.application.orders_delivery.queries.order_badge_query_service import (
    OrdersDeliveryBadgeQueryService,
)
from backend.domain.orders_delivery.delivery_job import DeliveryAttempt, DeliveryJob
from backend.domain.orders_delivery.entities import CustomerOrder, CustomerOrderLine
from backend.domain.orders_delivery.enums import FulfillmentType, OrderChannel, OrderType
from backend.domain.orders_delivery.value_objects.order_quantity import OrderQuantity
from backend.infrastructure.db.repositories.orders_delivery.customer_order_repository import (
    CustomerOrderRepository,
)
from backend.infrastructure.db.repositories.orders_delivery.delivery_job_repository import (
    DeliveryJobRepository,
)
from backend.infrastructure.db.schema.orders_delivery_schema import (
    create_orders_delivery_schema,
)
from backend.infrastructure.integrations.orders_delivery_internal_notifier import (
    OrdersDeliveryInternalNotifier,
)
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db
from tests.integration._audit_trail_table import create_audit_logs_table

SUCURSAL = new_uuid()


class _Sesion:
    is_active = True

    def __init__(self, permisos, *, user_id=None, branch_id=SUCURSAL):
        self.user_id = user_id or new_uuid()
        self.active_branch_id = branch_id
        self.sucursal_id = branch_id
        self.permisos = frozenset(permisos)

    def tiene_permiso(self, code):
        return code in self.permisos


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_orders_delivery_schema(c)
    create_audit_logs_table(c)
    c.commit()
    yield c
    c.close()


@pytest.fixture(scope="module")
def app():
    qt = pytest.importorskip("PyQt5.QtWidgets")
    yield qt.QApplication.instance() or qt.QApplication([])


def _entrega_fallida(conn):
    pedido = CustomerOrder.create(
        branch_id=SUCURSAL, channel=OrderChannel.POS, order_type=OrderType.STANDARD,
        fulfillment_type=FulfillmentType.HOME_DELIVERY, operation_id=new_uuid())
    pedido.add_line(CustomerOrderLine.create(
        order_id=pedido.id, product_id=new_uuid(), unit_price=Decimal("50"),
        requested_quantity=OrderQuantity(Decimal("1"))))
    CustomerOrderRepository(conn).save(pedido)
    trabajo = DeliveryJob.create(order_id=pedido.id, branch_id=SUCURSAL, operation_id=new_uuid())
    trabajo.assign_driver(driver_id=new_uuid())
    trabajo.mark_ready_to_dispatch()
    trabajo.dispatch()
    trabajo.mark_in_transit()
    trabajo.mark_arrived()
    trabajo.start_delivery_attempt()
    trabajo.record_attempt(DeliveryAttempt.create(
        delivery_job_id=trabajo.id, successful=False, failure_reason="CUSTOMER_NOT_HOME"))
    DeliveryJobRepository(conn).save(trabajo)
    conn.commit()


def _vista(conn, sesion):
    from frontend.desktop.modules.orders_delivery.shell_registration import (
        OrdersDeliveryModuleActivator,
    )
    from frontend.desktop.shell.routing.view_factory_registry import ViewFactoryRegistry

    return OrdersDeliveryModuleActivator(
        connection=conn, view_factory_registry=ViewFactoryRegistry(),
        session_context=sesion)._build_view()


def _textos(vista):
    return [vista.sidebar.item(fila).text() for fila in range(vista.sidebar.count())]


def test_the_sidebar_shows_the_delivery_counts(app, conn):
    _entrega_fallida(conn)

    textos = _textos(_vista(conn, _Sesion({P.FAILURE_REGISTER, P.DELIVERY_VIEW})))

    assert "Entregas fallidas (1)" in textos
    assert "Entregas activas (0)" in textos


def test_without_an_active_branch_there_are_no_counts(app, conn):
    _entrega_fallida(conn)

    textos = _textos(_vista(conn, _Sesion({P.FAILURE_REGISTER}, branch_id=None)))

    # FAILURE_REGISTER abre Incidencias y Entregas fallidas; ninguna con contador.
    assert textos == ["Incidencias", "Entregas fallidas"]


# -- alertas: por persona ----------------------------------------------------------------
def _admin(conn):
    user_id = new_uuid()
    rol = conn.execute("SELECT id FROM roles WHERE LOWER(nombre)='admin'").fetchone()[0]
    conn.execute(
        "INSERT INTO usuarios (id, nombre, usuario, password_hash, rol, sucursal_id, activo)"
        " VALUES (?,?,?,?,?,?,1)",
        (user_id, "Admin", f"admin-{user_id[-12:]}", "hash", "admin", SUCURSAL))
    conn.execute("INSERT INTO usuarios_roles (usuario_id, rol_id, sucursal_id) VALUES (?,?,?)",
                 (user_id, rol, SUCURSAL))
    return user_id


@pytest.fixture
def conn_completa():
    c = make_db()
    create_orders_delivery_schema(c)
    create_audit_logs_table(c)
    c.commit()
    yield c
    c.close()


def test_the_alerts_count_is_my_unread_alerts_not_one_per_recipient(app, conn_completa):
    yo, colega = _admin(conn_completa), _admin(conn_completa)
    escritos = OrdersDeliveryInternalNotifier(conn_completa).notify_roles(
        roles=("admin",), branch_id=SUCURSAL, tipo="entrega_fallida",
        titulo="Entrega fallida", cuerpo="CUSTOMER_NOT_HOME")
    assert escritos >= 2, escritos  # el notificador se traga sus errores
    conn_completa.commit()

    badges = OrdersDeliveryBadgeQueryService(conn_completa)
    mias = badges.get_badge_counts(SUCURSAL, recipient_user_id=yo)["critical_alerts"]
    pantalla = DeliveryRecordsQueryService(conn_completa).list_records(
        SUCURSAL, DeliveryRecord.ALERTS, status="UNREAD", recipient_user_id=yo).total

    assert mias == pantalla == 1
    assert badges.get_badge_counts(SUCURSAL, recipient_user_id=colega)["critical_alerts"] == 1
    assert badges.get_badge_counts(SUCURSAL)["critical_alerts"] == escritos


def test_the_sidebar_alerts_count_is_the_session_users(app, conn_completa):
    yo = _admin(conn_completa)
    _admin(conn_completa)
    OrdersDeliveryInternalNotifier(conn_completa).notify_roles(
        roles=("admin",), branch_id=SUCURSAL, tipo="entrega_fallida",
        titulo="Entrega fallida", cuerpo="CUSTOMER_NOT_HOME")
    conn_completa.commit()

    textos = _textos(_vista(conn_completa, _Sesion({P.ALERTS_VIEW}, user_id=yo)))

    assert textos == ["Alertas (1)"]
