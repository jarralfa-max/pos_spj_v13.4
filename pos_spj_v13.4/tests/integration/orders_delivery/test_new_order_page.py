"""Nuevo pedido (PASS 6): la pantalla.

Las reglas se prueban en `test_capture_order.py`. Aquí: que la ruta abre la página
real, que la búsqueda enseña precio y "sin precio", que no se agrega un producto
sin precio, que la dirección sólo aparece para modalidades con entrega, que el
botón sigue al permiso de la sesión y que crear deja el pedido con el precio de
Pricing.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from backend.application.orders_delivery.authorization import OrdersDeliveryAuthorizationPolicy
from backend.application.orders_delivery.permissions import (
    ALL_ORDERS_DELIVERY_PERMISSIONS,
    OrdersDeliveryPermissions as P,
)
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
    _zona,
    catalogo,
    conn,
)


class _Sesion:
    is_active = True
    user_id = USUARIO
    active_branch_id = SUCURSAL

    def __init__(self, permisos):
        self.permisos = frozenset(permisos)

    def tiene_permiso(self, code):
        return code in self.permisos


@pytest.fixture(scope="module")
def app():
    qt = pytest.importorskip("PyQt5.QtWidgets")
    yield qt.QApplication.instance() or qt.QApplication([])


def _pagina(conn, permisos=ALL_ORDERS_DELIVERY_PERMISSIONS):
    from frontend.desktop.modules.orders_delivery.orders_delivery_routes import build_page

    politica = OrdersDeliveryAuthorizationPolicy(
        OrdersDeliverySessionPermissionChecker(_Sesion(permisos)))
    pagina = build_page("orders_new", conn, branch_id=SUCURSAL, actor_user_id=USUARIO,
                        authorization=politica)
    pagina.ensure_loaded()
    return pagina


def _elegir(pagina, nombre):
    [opcion] = [o for o in pagina._presenter.search_products(nombre) if o.label == nombre]
    pagina.product.selected.emit(opcion)
    return opcion


def test_the_route_opens_the_capture_page(app, conn):
    from frontend.desktop.modules.orders_delivery.orders_delivery_routes import (
        ORDERS_DELIVERY_ROUTES,
    )
    from frontend.desktop.modules.orders_delivery.pages.new_order_page import NewOrderPage

    pagina = _pagina(conn)

    assert isinstance(pagina, NewOrderPage)
    assert pagina.title == ORDERS_DELIVERY_ROUTES["orders_new"].title


def test_the_search_shows_the_price_or_that_there_is_none(app, conn, catalogo):
    catalogo.producto("Refresco", precio="25")
    catalogo.producto("Tortillas")
    pagina = _pagina(conn)

    subtitulos = {o.label: o.subtitle for o in pagina._presenter.search_products("")}

    assert subtitulos["Refresco"].endswith("$25.00 / PZA")
    assert subtitulos["Tortillas"].endswith("Sin precio vigente")


def test_a_product_is_added_with_its_estimated_subtotal(app, conn, catalogo):
    catalogo.producto("Refresco", precio="25")
    pagina = _pagina(conn)
    _elegir(pagina, "Refresco")
    pagina.quantity.setText("3")

    pagina.add_selected_product()

    assert pagina.lines_table.rowCount() == 1
    assert [pagina.lines_table.item(0, c).text() for c in range(4)] == [
        "Refresco", "3.000 PZA", "$25.00", "$75.00"]


def test_a_product_without_price_is_not_added(app, conn, catalogo):
    catalogo.producto("Tortillas")
    pagina = _pagina(conn)
    _elegir(pagina, "Tortillas")
    pagina.quantity.setText("1")

    pagina.add_selected_product()

    assert pagina.lines_table.rowCount() == 0
    assert "precio vigente" in pagina.notice.text()


@pytest.mark.parametrize("modalidad, visible", [
    ("COUNTER", False), ("PICKUP", False), ("HOME_DELIVERY", True), ("EXPRESS_DELIVERY", True)])
def test_the_address_is_only_asked_for_deliveries(app, conn, modalidad, visible):
    pagina = _pagina(conn)

    pagina.fulfillment.set_current_id(modalidad)

    assert pagina.address_group.isHidden() is not visible


def test_without_the_create_permission_the_button_is_disabled(app, conn):
    assert _pagina(conn, {P.VIEW_OWN_BRANCH}).create_button.isEnabled() is False
    assert _pagina(conn).create_button.isEnabled() is True


def test_creating_a_home_delivery_saves_it_and_resets_the_form(app, conn, catalogo):
    _zona(conn, "06000", costo="35")
    catalogo.producto("Refresco", precio="25")
    pagina = _pagina(conn)
    pagina.channel.set_current_id("WHATSAPP")
    pagina.fulfillment.set_current_id("HOME_DELIVERY")
    pagina.contact_name.setText("Ana")
    _elegir(pagina, "Refresco")
    pagina.quantity.setText("2")
    pagina.add_selected_product()
    for campo, valor in ((pagina.recipient_name, "Ana"), (pagina.street, "Reforma"),
                         (pagina.exterior_number, "100"), (pagina.postal_code, "06000")):
        campo.setText(valor)
    pagina.recipient_phone.setText("5555555555")

    pagina.create_order()

    assert pagina.notice.property("state") == "SUCCESS", pagina.notice.text()
    assert pagina.lines_table.rowCount() == 0
    [fila] = conn.execute("SELECT id FROM customer_orders").fetchall()
    pedido = CustomerOrderRepository(conn).get(fila[0])
    assert (pedido.totals.subtotal, pedido.delivery_fee) == (Decimal("50"), Decimal("35"))
    assert pedido.delivery_address_id is not None
