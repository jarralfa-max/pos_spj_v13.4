"""ORD-28 — the first REAL Pedidos/Delivery desktop pages (Resumen/Todos los
pedidos/Análisis), against a real in-memory SQLite connection. Headless
(offscreen Qt, set globally by tests/conftest.py). Mirrors the composition
style `tests/integration/shell/test_finance_module_migration.py` already
established: a real connection, no whole dependency container.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest
from tests.integration._audit_trail_table import create_audit_logs_table

pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication

from backend.application.orders_delivery.authorization import OrdersDeliveryAuthorizationPolicy
from backend.application.orders_delivery.use_cases.order_capture_use_cases import (
    CreateCustomerOrderUseCase,
)
from backend.infrastructure.db.schema.orders_delivery_schema import create_orders_delivery_schema
from backend.shared.ids import new_uuid
from frontend.desktop.modules.orders_delivery.orders_delivery_routes import build_page
from frontend.desktop.modules.orders_delivery.pages.analytics_page import OrdersAnalyticsPage
from frontend.desktop.modules.orders_delivery.pages.orders_list_page import OrdersListPage
from frontend.desktop.modules.orders_delivery.pages.overview_page import OrdersOverviewPage
from frontend.desktop.modules.orders_delivery.pages import OrdersDeliveryPlaceholderPage
from frontend.desktop.modules.orders_delivery.presenters.analytics_presenter import (
    OrdersAnalyticsPresenter,
)
from frontend.desktop.modules.orders_delivery.presenters.orders_list_presenter import (
    OrdersListPresenter,
)
from frontend.desktop.modules.orders_delivery.presenters.overview_presenter import (
    OrdersOverviewPresenter,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    create_orders_delivery_schema(connection)
    create_audit_logs_table(connection)
    yield connection
    connection.close()


def _allow_all() -> OrdersDeliveryAuthorizationPolicy:
    return OrdersDeliveryAuthorizationPolicy.permissive_for_tests()


def _seed_order(conn, *, branch_id: str, status: str = "COMPLETED", grand_total: str = "50.00") -> None:
    result = CreateCustomerOrderUseCase(_allow_all()).execute(
        conn, branch_id=branch_id, channel="POS", order_type="STANDARD",
        fulfillment_type="COUNTER", contact_name="Cliente de prueba",
        lines=[{"product_id": new_uuid(), "unit_price": grand_total, "requested_quantity": "1"}],
        actor_user_id=new_uuid(), operation_id=new_uuid())
    if status != "DRAFT":
        conn.execute("UPDATE customer_orders SET status=? WHERE id=?", (status, result.entity_id))


class TestOrdersOverviewPage(object):
    def test_renders_real_kpis(self, app, conn):
        branch_id = new_uuid()
        _seed_order(conn, branch_id=branch_id)
        page = OrdersOverviewPage(OrdersOverviewPresenter(conn, branch_id=branch_id))
        page.ensure_loaded()
        assert page.kpis._cards  # KPI cards were actually populated
        titles = {card.title for card in page.kpis._cards}
        assert "Pedidos (30 días)" in titles

    def test_never_crashes_on_broken_presenter(self, app, conn, monkeypatch):
        from frontend.desktop.modules.orders_delivery.pages import overview_page as page_module

        class _FakeMessageBox:
            @staticmethod
            def warning(*_args, **_kwargs):
                return None

        class _BrokenPresenter:
            def kpi_cards(self):
                raise RuntimeError("boom")

        monkeypatch.setattr(page_module, "MessageDialog", _FakeMessageBox)
        page = OrdersOverviewPage(_BrokenPresenter())
        page.ensure_loaded()  # must not raise (real QMessageBox would show a blocking modal)


class TestOrdersListPage(object):
    def test_lists_real_orders_and_filters_by_search(self, app, conn):
        branch_id = new_uuid()
        _seed_order(conn, branch_id=branch_id)
        _seed_order(conn, branch_id=branch_id, status="CANCELLED")
        presenter = OrdersListPresenter(conn, branch_id=branch_id, actor_user_id=new_uuid())
        page = OrdersListPage(presenter)
        page.ensure_loaded()
        assert page.table.rowCount() == 2

        page._search.setText("no-such-customer-xyz")
        page.reload()
        assert page.table.rowCount() == 0


class TestOrdersAnalyticsPage(object):
    def test_renders_kpis_and_charts_without_crashing(self, app, conn):
        branch_id = new_uuid()
        _seed_order(conn, branch_id=branch_id)
        page = OrdersAnalyticsPage(OrdersAnalyticsPresenter(conn, branch_id=branch_id))
        page.ensure_loaded()
        assert page.kpis._cards
        assert len(page.charts) == 2


class TestBuildPageWiring(object):
    def test_wired_routes_return_real_pages_with_a_connection(self, app, conn):
        branch_id = new_uuid()
        assert isinstance(
            build_page("orders_overview", conn, branch_id=branch_id), OrdersOverviewPage)
        assert isinstance(
            build_page("orders_all", conn, branch_id=branch_id), OrdersListPage)
        assert isinstance(
            build_page("orders_analytics", conn, branch_id=branch_id), OrdersAnalyticsPage)

    def test_every_route_has_a_real_page_with_a_connection(self, app, conn):
        """PASS 6 terminó de construir las 23 rutas: con conexión ninguna cae a
        placeholder. Sin conexión sí (ver la prueba siguiente)."""
        from frontend.desktop.modules.orders_delivery.orders_delivery_routes import (
            _REAL_ROUTE_BUILDERS,
            ORDERS_DELIVERY_ROUTES,
        )
        assert set(_REAL_ROUTE_BUILDERS) == set(ORDERS_DELIVERY_ROUTES)

    def test_no_connection_keeps_ord4_placeholder_behavior(self, app):
        page = build_page("orders_overview")
        assert isinstance(page, OrdersDeliveryPlaceholderPage)
