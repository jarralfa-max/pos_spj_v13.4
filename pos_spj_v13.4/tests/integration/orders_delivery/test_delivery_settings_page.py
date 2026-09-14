"""Configuración de Pedidos/Reparto (PASS 6): la pantalla de zonas de entrega.

Se fija que la ruta abre una página real, que sus botones siguen al permiso de la
SESIÓN y al estado de la zona elegida, y que el diálogo entrega al presenter
datos que el caso de uso acepta. Las reglas en sí se prueban en
`test_delivery_zone_use_cases.py`.
"""
from __future__ import annotations

import sqlite3
from decimal import Decimal

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

SUCURSAL = new_uuid()
USUARIO = new_uuid()


class _Sesion:
    is_active = True
    user_id = USUARIO
    active_branch_id = SUCURSAL

    def __init__(self, permisos):
        self.permisos = frozenset(permisos)

    def tiene_permiso(self, code):
        return code in self.permisos


def _politica(*permisos):
    return OrdersDeliveryAuthorizationPolicy(
        OrdersDeliverySessionPermissionChecker(_Sesion(permisos)))


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_orders_delivery_schema(c)
    c.commit()
    yield c
    c.close()


@pytest.fixture(scope="module")
def app():
    qt = pytest.importorskip("PyQt5.QtWidgets")
    yield qt.QApplication.instance() or qt.QApplication([])


def _pagina(conn, politica):
    from frontend.desktop.modules.orders_delivery.orders_delivery_routes import build_page

    pagina = build_page("orders_settings", conn, branch_id=SUCURSAL, actor_user_id=USUARIO,
                        authorization=politica)
    pagina.ensure_loaded()
    return pagina


def _sembrar(pagina):
    presenter = pagina._presenter
    for nombre, codigos in (("Centro", "06000"), ("Roma", "06700")):
        ok, mensaje = presenter.create_zone({
            "name": nombre, "postal_codes": codigos, "minimum_order": Decimal("100"),
            "delivery_fee": Decimal("35")})
        assert ok, mensaje
    pagina.reload()
    roma = next(z for z in presenter._zonas.values() if z.name == "Roma")
    assert presenter.set_zone_active(roma.id, False)[0]
    pagina.reload()


def _textos(pagina, columna):
    return [pagina.table.item(fila, columna).text() for fila in range(pagina.table.rowCount())]


def test_the_settings_route_opens_the_zones_page(app, conn):
    from frontend.desktop.modules.orders_delivery.orders_delivery_routes import (
        ORDERS_DELIVERY_ROUTES,
    )
    from frontend.desktop.modules.orders_delivery.pages.delivery_settings_page import (
        SCOPE_NOTE,
        DeliverySettingsPage,
    )

    pagina = _pagina(conn, _politica(P.SETTINGS_VIEW))

    assert isinstance(pagina, DeliverySettingsPage)
    assert pagina.title == ORDERS_DELIVERY_ROUTES["orders_settings"].title
    assert pagina._notice.isHidden(), pagina._notice.text()
    assert pagina._stack.currentWidget() is pagina._empty
    assert pagina.scope_note.text() == SCOPE_NOTE


def test_the_page_lists_active_and_inactive_zones(app, conn):
    pagina = _pagina(conn, _politica(P.SETTINGS_MANAGE))
    _sembrar(pagina)

    assert _textos(pagina, 0) == ["Centro", "Roma"]
    assert _textos(pagina, 7) == ["Activa", "Inactiva"]
    assert _textos(pagina, 3) == ["$35.00", "$35.00"]


def test_without_the_manage_permission_nothing_is_enabled(app, conn):
    gestor = _pagina(conn, _politica(P.SETTINGS_MANAGE))
    _sembrar(gestor)

    lector = _pagina(conn, _politica(P.SETTINGS_VIEW))
    lector.table.selectRow(0)

    assert lector.new_zone_button.isEnabled() is False
    assert [b.isEnabled() for b in (lector.edit_button, lector.deactivate_button,
                                    lector.activate_button)] == [False, False, False]


@pytest.mark.parametrize("fila, habilitados", [
    (0, [True, True, False]),   # Centro, activa: editar y desactivar
    (1, [True, False, True]),   # Roma, inactiva: editar y activar
], ids=["activa", "inactiva"])
def test_row_actions_follow_the_selected_zone(app, conn, fila, habilitados):
    pagina = _pagina(conn, _politica(P.SETTINGS_MANAGE))
    _sembrar(pagina)

    pagina.table.selectRow(fila)

    assert pagina.new_zone_button.isEnabled() is True
    assert [b.isEnabled() for b in (pagina.edit_button, pagina.deactivate_button,
                                    pagina.activate_button)] == habilitados


def test_the_dialog_data_is_accepted_by_the_use_case(app, conn):
    from frontend.desktop.modules.orders_delivery.dialogs.delivery_zone_dialog import (
        DeliveryZoneDialog,
    )

    pagina = _pagina(conn, _politica(P.SETTINGS_MANAGE))
    dialogo = DeliveryZoneDialog()
    dialogo.name_input.setText("Condesa")
    dialogo.postal_codes_input.setText("06140, 06170")
    dialogo.delivery_fee_input.setValue(float(Decimal("40")))
    dialogo.estimated_minutes_input.setText("30")
    assert dialogo._is_valid()

    ok, mensaje = pagina._presenter.create_zone(dialogo.data())
    pagina.reload()

    assert ok, mensaje
    assert _textos(pagina, 1) == ["06140, 06170"]
    assert _textos(pagina, 5) == ["30 min"]
    assert _textos(pagina, 4) == ["—"]  # sin envío gratis: vacío, no $0


def test_editing_prefills_the_dialog_with_the_zone(app, conn):
    from frontend.desktop.modules.orders_delivery.dialogs.delivery_zone_dialog import (
        DeliveryZoneDialog,
    )

    pagina = _pagina(conn, _politica(P.SETTINGS_MANAGE))
    _sembrar(pagina)
    zona = pagina._presenter.zone(pagina.table.item(0, 0).data(0x0100))

    dialogo = DeliveryZoneDialog(zone=zona)

    assert dialogo.name_input.text() == "Centro"
    assert dialogo.data()["postal_codes"] == "06000"
    assert dialogo.data()["delivery_fee"] == Decimal("35")
    assert dialogo.data()["free_delivery_threshold"] is None


@pytest.mark.parametrize("campo, texto", [("name_input", ""), ("postal_codes_input", " "),
                                          ("estimated_minutes_input", "abc")])
def test_the_dialog_refuses_incomplete_data(app, campo, texto):
    from frontend.desktop.modules.orders_delivery.dialogs.delivery_zone_dialog import (
        DeliveryZoneDialog,
    )

    dialogo = DeliveryZoneDialog()
    dialogo.name_input.setText("Centro")
    dialogo.postal_codes_input.setText("06000")
    getattr(dialogo, campo).setText(texto)

    assert dialogo._is_valid() is False
