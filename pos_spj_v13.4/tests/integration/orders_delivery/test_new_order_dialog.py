"""SDLC-ORD-005 — "Nuevo pedido" es un solo flujo desde cualquier pantalla.

El alta rápida de "Todos los pedidos" se conserva (decisión del responsable),
pero ya no pide el UUID del producto ni un precio libre que terminaba cobrándose:
es la misma captura de la página, con búsqueda, precio de Pricing y dirección.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from backend.application.orders_delivery.authorization import OrdersDeliveryAuthorizationPolicy
from backend.application.orders_delivery.permissions import ALL_ORDERS_DELIVERY_PERMISSIONS
from backend.application.orders_delivery.session_authorization import (
    OrdersDeliverySessionPermissionChecker,
)
from backend.infrastructure.db.repositories.orders_delivery.customer_order_repository import (
    CustomerOrderRepository,
)
from tests.integration.orders_delivery.test_capture_order import (  # noqa: F401 - fixtures
    SUCURSAL,
    USUARIO,
    Catalogo,
    catalogo,
    conn,
)

RAIZ = Path(__file__).resolve().parents[3]


class _Sesion:
    is_active = True
    user_id = USUARIO
    active_branch_id = SUCURSAL

    def tiene_permiso(self, code):
        return code in ALL_ORDERS_DELIVERY_PERMISSIONS


@pytest.fixture(scope="module")
def app():
    qt = pytest.importorskip("PyQt5.QtWidgets")
    yield qt.QApplication.instance() or qt.QApplication([])


def _listado(conn):
    from frontend.desktop.modules.orders_delivery.orders_delivery_routes import build_page

    politica = OrdersDeliveryAuthorizationPolicy(
        OrdersDeliverySessionPermissionChecker(_Sesion()))
    return build_page("orders_all", conn, branch_id=SUCURSAL, actor_user_id=USUARIO,
                      authorization=politica)


def _dialogo(conn):
    from frontend.desktop.modules.orders_delivery.dialogs.new_order_dialog import NewOrderDialog

    return NewOrderDialog(_listado(conn)._presenter.new_order_presenter())


def test_el_alta_rapida_usa_la_misma_captura_que_la_pagina(app, conn):
    from frontend.desktop.modules.orders_delivery.pages.new_order_page import NewOrderPage

    assert isinstance(_dialogo(conn).capture, NewOrderPage)


def test_el_alta_rapida_cobra_el_precio_de_pricing_y_se_cierra(app, conn, catalogo):
    catalogo.producto("Refresco", precio="25")
    dialogo = _dialogo(conn)
    captura = dialogo.capture
    captura.channel.set_current_id("POS")
    captura.fulfillment.set_current_id("COUNTER")
    [opcion] = captura._presenter.search_products("Refresco")
    captura.product.selected.emit(opcion)
    captura.quantity.setText("2")
    captura.add_selected_product()

    captura.create_order()

    assert dialogo.result() == dialogo.Accepted
    assert dialogo.message
    [fila] = conn.execute("SELECT id FROM customer_orders").fetchall()
    [linea] = CustomerOrderRepository(conn).get(fila[0]).lines
    assert linea.unit_price_snapshot == Decimal("25")


def test_un_pedido_rechazado_deja_el_dialogo_abierto_con_el_motivo(app, conn):
    dialogo = _dialogo(conn)
    captura = dialogo.capture
    captura.channel.set_current_id("POS")
    captura.fulfillment.set_current_id("COUNTER")

    captura.create_order()   # sin líneas

    assert dialogo.result() != dialogo.Accepted
    assert captura.notice.text()


def test_el_boton_del_listado_abre_el_flujo_y_avisa(app, conn, monkeypatch):
    from frontend.desktop.modules.orders_delivery.dialogs import new_order_dialog

    pagina = _listado(conn)
    abiertos, avisos = [], []

    def _exec(dialogo):
        abiertos.append(dialogo)
        dialogo.message = "Pedido creado"
        return dialogo.Accepted

    monkeypatch.setattr(new_order_dialog.NewOrderDialog, "exec_", _exec)
    monkeypatch.setattr(pagina, "notify", lambda *a: avisos.append(a))

    pagina._new_order()

    assert len(abiertos) == 1
    assert avisos == [(True, "Pedido creado")]


def test_ninguna_pantalla_de_pedidos_pide_uuid_ni_precio_manual():
    modulo = RAIZ / "frontend/desktop/modules/orders_delivery"
    for archivo in modulo.rglob("*.py"):
        texto = archivo.read_text(encoding="utf-8")
        assert "UUID del producto" not in texto, archivo
        assert "unit_price" not in texto, archivo


def test_el_precio_libre_no_esta_expuesto_a_la_ui():
    """`CreateCustomerOrderUseCase` respeta el precio de la línea: es para precio
    COTIZADO. Ninguna pantalla debe llegar a él."""
    for archivo in (RAIZ / "frontend").rglob("*.py"):
        assert "CreateCustomerOrderUseCase" not in archivo.read_text(encoding="utf-8"), archivo
