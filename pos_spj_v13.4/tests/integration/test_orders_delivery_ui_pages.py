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

pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication

from backend.application.orders_delivery.authorization import OrdersDeliveryAuthorizationPolicy
from backend.application.orders_delivery.use_cases.order_capture_use_cases import (
    CreateCustomerOrderUseCase,
)
from backend.infrastructure.db.schema.orders_delivery_schema import create_orders_delivery_schema
from backend.shared.ids import new_uuid
from frontend.desktop.modules.orders_delivery.dialogs.new_order_dialog import NewOrderDialog
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

        monkeypatch.setattr(page_module, "QMessageBox", _FakeMessageBox)
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

    def test_new_order_dialog_creates_a_real_order(self, app, conn):
        branch_id = new_uuid()
        presenter = OrdersListPresenter(
            conn, branch_id=branch_id, actor_user_id=new_uuid(), authorization=_allow_all())
        ok, message = presenter.create_order({
            "channel": "POS", "fulfillment_type": "COUNTER", "contact_name": "Ana",
            "contact_phone": None,
            "lines": [{"product_id": new_uuid(), "unit_price": "25.00", "requested_quantity": "2"}],
        })
        assert ok, message
        row = conn.execute(
            "SELECT COUNT(*) FROM customer_orders WHERE branch_id=?", (branch_id,)).fetchone()
        assert row[0] == 1


class TestOrdersAnalyticsPage(object):
    def test_renders_kpis_and_charts_without_crashing(self, app, conn):
        branch_id = new_uuid()
        _seed_order(conn, branch_id=branch_id)
        page = OrdersAnalyticsPage(OrdersAnalyticsPresenter(conn, branch_id=branch_id))
        page.ensure_loaded()
        assert page.kpis._cards
        assert len(page.charts) == 2


class TestNewOrderDialog(object):
    def test_data_shape_matches_use_case_expectations(self, app):
        dialog = NewOrderDialog()
        dialog.channel_combo.set_current_id("POS")
        dialog.fulfillment_combo.set_current_id("COUNTER")
        dialog.contact_name_input.setText("Cliente")
        product_id = new_uuid()
        dialog.product_id_input.setText(product_id)
        dialog.quantity_input.setText("2")
        dialog.unit_price_input.setValue(10.0)

        data = dialog.data()

        assert data["channel"] == "POS"
        assert data["fulfillment_type"] == "COUNTER"
        assert data["lines"] == [{
            "product_id": product_id, "unit_price": "10.0", "requested_quantity": "2.000",
        }]
        assert dialog._is_valid() is True

    def test_invalid_without_required_fields(self, app):
        dialog = NewOrderDialog()
        assert dialog._is_valid() is False


class TestBuildPageWiring(object):
    def test_wired_routes_return_real_pages_with_a_connection(self, app, conn):
        branch_id = new_uuid()
        assert isinstance(
            build_page("orders_overview", conn, branch_id=branch_id), OrdersOverviewPage)
        assert isinstance(
            build_page("orders_all", conn, branch_id=branch_id), OrdersListPage)
        assert isinstance(
            build_page("orders_analytics", conn, branch_id=branch_id), OrdersAnalyticsPage)

    def test_unwired_routes_still_fall_back_to_placeholder(self, app, conn):
        page = build_page("orders_audit", conn, branch_id=new_uuid())
        assert isinstance(page, OrdersDeliveryPlaceholderPage)

    def test_no_connection_keeps_ord4_placeholder_behavior(self, app):
        page = build_page("orders_overview")
        assert isinstance(page, OrdersDeliveryPlaceholderPage)
