"""Puntos en la pantalla del POS (2026-10-02).

* "Puntos a ganar" (§29) sale de las reglas de Fidelidad → Ajustes; a una venta
  de mostrador le pide asignar cliente en vez de inventar un número.
* "Canjear" aparece con un cliente que tiene puntos, descuenta del ticket lo
  que Fidelidad permite (tope del 50 % por omisión) y desaparece una vez
  aplicado.
* Cancelar una venta con canje DEVUELVE los puntos: se descuentan al canjear,
  antes de cobrar, y hasta hoy se perdían.
* Cobrar acredita los puntos de la compra por el bus.

Presentador, casos de uso, esquema y bus son reales; sólo los modales se
sustituyen (un `exec_()` real bloquearía la prueba).
"""

from __future__ import annotations

import os
import sqlite3
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication, QMessageBox  # noqa: E402

from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy  # noqa: E402
from backend.application.loyalty.queries.redemption_preview_query import (  # noqa: E402
    LoyaltyRedemptionPreviewQuery,
)
from backend.application.loyalty.use_cases.sale_points_use_cases import (  # noqa: E402
    AccrueSalePointsUseCase,
)
from backend.application.sales.integrations.wiring import wire_sales  # noqa: E402
from backend.application.services.finance.finance_bootstrap import bootstrap_finance  # noqa: E402
from backend.infrastructure.db.schema.customers_crm_schema import (  # noqa: E402
    create_customers_crm_schema,
)
from backend.infrastructure.db.schema.document_output_schema import (  # noqa: E402
    create_document_numbering_schema,
)
from backend.infrastructure.db.schema.finance_schema import create_finance_schema  # noqa: E402
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema  # noqa: E402
from backend.infrastructure.db.schema.loyalty_schema import create_loyalty_schema  # noqa: E402
from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema  # noqa: E402
from backend.infrastructure.db.schema.products_schema import create_products_schema  # noqa: E402
from backend.infrastructure.db.schema.sales_schema import create_sales_schema  # noqa: E402
from backend.shared.events.application_bus import ApplicationEventBus  # noqa: E402
from backend.shared.ids import new_uuid  # noqa: E402
from frontend.desktop.modules.sales_pos.composition import create_sales_pos_view  # noqa: E402
from frontend.desktop.modules.sales_pos.dialogs.redeem_points_dialog import (  # noqa: E402
    RedeemPointsDialog,
)
from tests.integration._pos_ready import open_cash_shift  # noqa: E402
from tests.integration.sales.test_sales_pos_screen_flows import (  # noqa: E402
    _cobrar,
    _product,
    _producto,
    _Session,
    _stub,
    _unit,
)


class _LoyaltySession(_Session):
    def __init__(self):
        super().__init__()
        self._permissions = set(self._permissions) | {"GROWTH_ENGINE.puntos.canjear"}


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    for create in (create_sales_schema, create_products_schema, create_pricing_schema,
                   create_inventory_schema, create_document_numbering_schema,
                   create_customers_crm_schema, create_loyalty_schema, create_finance_schema):
        create(c)
    bootstrap_finance(c)
    c.execute("CREATE TABLE configuraciones (clave TEXT PRIMARY KEY, valor TEXT,"
              " tipo TEXT, grupo TEXT, descripcion TEXT)")
    c.execute("CREATE TABLE branch_profiles (branch_id TEXT PRIMARY KEY, code TEXT, name TEXT,"
              " address TEXT, phone TEXT, ticket_header TEXT, ticket_footer TEXT)")
    c.execute("INSERT INTO price_list (id, code, name, kind, status, discount_pct)"
              " VALUES (?, 'BASE', 'Lista base', 'BASE', 'ACTIVE', '0')", (new_uuid(),))
    c.commit()
    yield c
    c.close()


@pytest.fixture
def pos(app, conn, monkeypatch):
    session = _LoyaltySession()
    branch = session.active_branch_id
    conn.execute("INSERT INTO branch_profiles (branch_id, code, name) VALUES (?, 'COR', ?)",
                 (branch, "Corregidora"))
    open_cash_shift(conn, branch_id=branch, cashier_user_id=session.user_id)
    pza = _unit(conn, "PZA", "COUNT")
    _product(conn, name="Huacal", code="HUA", unit_id=pza, price="100", branch_id=branch,
             stock="20")

    # El bus de la aplicación, cableado como al arrancar (Finanzas + Fidelidad).
    bus = ApplicationEventBus()
    wire_sales(bus, conn)
    monkeypatch.setattr("backend.shared.events.application_bus.get_bus", lambda: bus)
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *_a: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *_a: None))

    workspace = create_sales_pos_view(conn, session)
    workspace.resize(1366, 768)
    workspace.show()
    app.processEvents()
    workspace.conn = conn
    yield workspace
    workspace.close()


def _customer_with_points(pos, points_worth):
    """Un cliente con puntos ganados en una compra previa de `points_worth` pesos."""
    created = pos._presenter.quick_create_customer(display_name="Ana Torres")
    assert created.success, created.message
    result = AccrueSalePointsUseCase(LoyaltyAuthorizationPolicy.permissive_for_tests()).execute(
        pos.conn, sale_id=new_uuid(), customer_id=created.entity_id, total=points_worth,
        credit_amount="0", branch_id=new_uuid(), actor_user_id=new_uuid(),
        operation_id=new_uuid())
    assert result.success, result.message
    return created.entity_id


def _balance(pos, customer_id):
    return LoyaltyRedemptionPreviewQuery(pos.conn).balance(customer_id)


def _redeem_dialog(points=None):
    class _Redeem(RedeemPointsDialog):
        def exec_(self):
            if points is not None:
                self.set_points(points)
            self._submit()
            return self.result()

    return _Redeem


def test_points_to_earn_follow_the_loyalty_rules(pos):
    pos._on_product_selected(_producto(pos, "Huacal"))
    assert pos.checkout.totals._points_value.text() == "Asigna un cliente"

    customer = _customer_with_points(pos, "0")
    pos._on_customer_selected(customer)
    assert pos.checkout.totals._points_value.text() == "10 pts"

    pos.conn.execute("INSERT INTO configuraciones (clave, valor) VALUES"
                     " ('loyalty_pesos_por_punto', '5')")
    pos._refresh()
    assert pos.checkout.totals._points_value.text() == "20 pts"


def test_redeem_is_offered_only_with_points_and_applies_the_loyalty_cap(pos):
    pos._on_product_selected(_producto(pos, "Huacal"))
    customer = _customer_with_points(pos, "10000")  # 1000 puntos = $100
    pos._on_customer_selected(customer)
    assert pos.checkout.customer.redeem_button().isVisibleTo(pos)

    pos.dialogs["redeem"] = _redeem_dialog()
    pos._on_redeem_requested()

    # Tope por omisión: 50 % del subtotal de $100 → 500 puntos, $50.
    assert pos._sale.loyalty_total == Decimal("50.00")
    assert pos._sale.total == Decimal("50.00")
    assert _balance(pos, customer) == 500
    assert not pos.checkout.customer.redeem_button().isVisibleTo(pos)


def test_cancelling_a_sale_gives_the_redeemed_points_back(pos):
    pos._on_product_selected(_producto(pos, "Huacal"))
    customer = _customer_with_points(pos, "10000")
    pos._on_customer_selected(customer)
    pos.dialogs["redeem"] = _redeem_dialog(points=200)
    pos._on_redeem_requested()
    assert _balance(pos, customer) == 800

    pos.dialogs["cancel"] = _stub(reason="el cliente se arrepintió")
    pos._on_cancel_requested()

    assert _balance(pos, customer) == 1000


def test_charging_credits_the_points_of_the_purchase(pos):
    pos._on_product_selected(_producto(pos, "Huacal"))
    customer = _customer_with_points(pos, "0")
    pos._on_customer_selected(customer)

    _cobrar(pos, "100")

    assert _balance(pos, customer) == 10
