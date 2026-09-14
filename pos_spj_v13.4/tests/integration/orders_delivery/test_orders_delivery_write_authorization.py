"""Pedidos/Reparto: las escrituras de la UI llevan la autorización REAL de la sesión.

EL DEFECTO
----------
El activator del shell construía `OrdersDeliveryView` con conexión, sucursal y
usuario, pero sin política de autorización. `_build_orders_list` creaba el
presenter sin ella, y `OrdersDeliveryAuthorizationPolicy()` sin checker falla
cerrada —como debe—. Resultado: "Nuevo pedido" devolvía SIEMPRE "requiere un
PermissionChecker" en la aplicación, y `OrdersDeliverySessionPermissionChecker`,
el checker real, no lo usaba nadie.

LO QUE SE FIJA
--------------
- El activator entrega a la vista una política respaldada por la sesión viva.
- La vista y `build_page` la hacen llegar al presenter que escribe.
- Con permiso se escribe; sin permiso se rechaza y no se escribe nada; sin
  política sigue fallando cerrada. Ninguna de estas pruebas usa una política
  permisiva (§23): el permiso lo concede la sesión.
"""
from __future__ import annotations

import sqlite3

import pytest

from backend.application.orders_delivery.authorization import OrdersDeliveryAuthorizationPolicy
from backend.application.orders_delivery.permissions import OrdersDeliveryPermissions as P
from backend.application.orders_delivery.session_authorization import (
    OrdersDeliverySessionPermissionChecker,
)
from backend.infrastructure.db.schema.orders_delivery_schema import (
    create_orders_delivery_schema,
)
from backend.shared.ids import new_uuid
from tests.integration._audit_trail_table import create_audit_logs_table

SUCURSAL = new_uuid()
USUARIO = new_uuid()


class _Sesion:
    """El subconjunto que exponen `SessionContext` y `LegacySessionAdapter`."""

    is_active = True

    def __init__(self, permisos=frozenset(), *, user_id=USUARIO, branch_id=SUCURSAL):
        self.user_id = user_id
        self.active_branch_id = branch_id
        self.sucursal_id = branch_id
        self.permisos = frozenset(permisos)

    def tiene_permiso(self, code):
        return code in self.permisos


def _politica(sesion):
    return OrdersDeliveryAuthorizationPolicy(OrdersDeliverySessionPermissionChecker(sesion))


def _datos_pedido():
    return {
        "channel": "POS", "fulfillment_type": "COUNTER", "contact_name": "Ana",
        "contact_phone": None,
        "lines": [{"product_id": new_uuid(), "unit_price": "25.00", "requested_quantity": "2"}],
    }


def _pedidos(conn):
    return conn.execute(
        "SELECT COUNT(*) FROM customer_orders WHERE branch_id=?", (SUCURSAL,)).fetchone()[0]


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


# -- el activator ----------------------------------------------------------------
def _vista_capturada(conn, monkeypatch, sesion):
    from frontend.desktop.modules.orders_delivery import orders_delivery_view
    from frontend.desktop.modules.orders_delivery.shell_registration import (
        OrdersDeliveryModuleActivator,
    )
    from frontend.desktop.shell.routing.view_factory_registry import ViewFactoryRegistry

    capturado = {}

    class _Grabadora:
        def __init__(self, **kwargs):
            capturado.update(kwargs)

    monkeypatch.setattr(orders_delivery_view, "OrdersDeliveryView", _Grabadora)
    OrdersDeliveryModuleActivator(
        connection=conn, view_factory_registry=ViewFactoryRegistry(),
        session_context=sesion)._build_view()
    return capturado


def test_the_activator_hands_the_view_a_policy_backed_by_the_session(app, conn, monkeypatch):
    politica = _vista_capturada(conn, monkeypatch, _Sesion({P.ORDER_CREATE}))["authorization"]

    assert isinstance(politica, OrdersDeliveryAuthorizationPolicy)
    assert politica.has_permission(USUARIO, P.ORDER_CREATE) is True
    assert politica.has_permission(USUARIO, P.SETTINGS_MANAGE) is False
    # Otro usuario no hereda los permisos de la sesión.
    assert politica.has_permission(new_uuid(), P.ORDER_CREATE) is False


def test_without_a_session_the_policy_grants_nothing(app, conn, monkeypatch):
    politica = _vista_capturada(conn, monkeypatch, None)["authorization"]

    assert politica.has_permission(USUARIO, P.ORDER_CREATE) is False


# -- build_page y la vista -------------------------------------------------------------
def _presenter_de_lista(conn, **kwargs):
    from frontend.desktop.modules.orders_delivery.orders_delivery_routes import build_page

    pagina = build_page("orders_all", conn, branch_id=SUCURSAL, actor_user_id=USUARIO, **kwargs)
    return pagina._presenter


def test_new_order_writes_when_the_session_grants_it(app, conn):
    ok, mensaje = _presenter_de_lista(
        conn, authorization=_politica(_Sesion({P.ORDER_CREATE}))).create_order(_datos_pedido())

    assert ok, mensaje
    assert _pedidos(conn) == 1


def test_new_order_is_refused_without_the_permission(app, conn):
    ok, mensaje = _presenter_de_lista(
        conn, authorization=_politica(_Sesion({P.VIEW_OWN_BRANCH}))).create_order(_datos_pedido())

    assert not ok
    assert P.ORDER_CREATE in mensaje
    assert _pedidos(conn) == 0


def test_without_a_policy_writing_still_fails_closed(app, conn):
    ok, mensaje = _presenter_de_lista(conn).create_order(_datos_pedido())

    assert not ok
    assert "PermissionChecker" in mensaje
    assert _pedidos(conn) == 0


def test_the_view_passes_the_policy_to_the_pages_it_builds(app, conn):
    from frontend.desktop.modules.orders_delivery.orders_delivery_view import OrdersDeliveryView

    politica = _politica(_Sesion({P.ORDER_CREATE}))
    vista = OrdersDeliveryView(
        has_permission=lambda _p: True, connection=conn, branch_id=SUCURSAL,
        actor_user_id=USUARIO, authorization=politica)
    vista.show_route("orders_all")

    ok, mensaje = vista.stack.currentWidget()._presenter.create_order(_datos_pedido())
    assert ok, mensaje
    assert _pedidos(conn) == 1
