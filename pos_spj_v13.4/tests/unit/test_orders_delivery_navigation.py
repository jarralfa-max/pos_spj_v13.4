"""ORD-4 — Sidebar navigation, routes and badge query service for Pedidos y
Delivery. Mirrors the testable surface of the Losses navigation module
(pure-logic pieces only; PyQt widget instantiation is exercised at a higher
integration level elsewhere in this repo, not here)."""

from __future__ import annotations

import sqlite3

from backend.application.orders_delivery.permissions import (
    ALL_ORDERS_DELIVERY_PERMISSIONS,
    OrdersDeliveryPermissions,
)
from backend.application.orders_delivery.queries.order_badge_query_service import (
    OrdersDeliveryBadgeQueryService,
)
from backend.infrastructure.db.schema.orders_delivery_schema import create_orders_delivery_schema
from frontend.desktop.modules.orders_delivery.navigation.orders_delivery_sidebar import (
    ORDERS_DELIVERY_NAV,
    visible_entries,
)
from frontend.desktop.modules.orders_delivery.orders_delivery_routes import (
    ORDERS_DELIVERY_ROUTES,
    build_page,
)


def test_every_nav_entry_has_a_unique_page_id():
    page_ids = [entry.page_id for entry in ORDERS_DELIVERY_NAV]
    assert len(page_ids) == len(set(page_ids))


def test_every_nav_entry_permission_is_registered():
    for entry in ORDERS_DELIVERY_NAV:
        assert entry.permission in ALL_ORDERS_DELIVERY_PERMISSIONS


def test_visible_entries_filters_by_permission():
    allowed = {OrdersDeliveryPermissions.DASHBOARD_VIEW}
    visible = visible_entries(lambda code: code in allowed)
    assert len(visible) == 1
    assert visible[0][0].page_id == "orders_overview"


def test_visible_entries_empty_when_no_permissions():
    assert visible_entries(lambda code: False) == ()


def test_visible_entries_attaches_badge_value():
    visible = visible_entries(
        lambda code: True, badges={"pending_confirmation": 7})
    entry_map = {entry.page_id: badge for entry, badge in visible}
    assert entry_map["orders_pending_confirmation"] == 7
    assert entry_map["orders_overview"] is None


def test_routes_registry_covers_every_nav_entry():
    assert set(ORDERS_DELIVERY_ROUTES) == {e.page_id for e in ORDERS_DELIVERY_NAV}


def test_build_page_unknown_route_raises():
    import pytest
    with pytest.raises(KeyError):
        build_page("not_a_real_route")


class TestOrdersDeliveryBadgeQueryService:
    def _db(self):
        conn = sqlite3.connect(":memory:")
        create_orders_delivery_schema(conn)
        return conn

    def _insert_order(self, conn, **overrides):
        row = dict(
            id="o1", branch_id="b1", channel="POS", order_type="STANDARD",
            fulfillment_type="COUNTER", status="DRAFT", fulfillment_status="PENDING",
            customer_approval_status="NOT_REQUIRED", operation_id="op-1",
            created_at="t", updated_at="t",
        )
        row.update(overrides)
        cols = ", ".join(row)
        placeholders = ", ".join("?" for _ in row)
        conn.execute(
            f"INSERT INTO customer_orders ({cols}) VALUES ({placeholders})",
            list(row.values()))

    def test_degrades_to_zero_on_empty_db(self):
        service = OrdersDeliveryBadgeQueryService(self._db())
        counts = service.get_badge_counts("b1")
        assert all(value == 0 for value in counts.values())

    def test_counts_pending_confirmation(self):
        conn = self._db()
        self._insert_order(conn, id="o1", operation_id="op-1", status="PENDING_CONFIRMATION")
        self._insert_order(conn, id="o2", operation_id="op-2", branch_id="other-branch",
                            status="PENDING_CONFIRMATION")
        counts = OrdersDeliveryBadgeQueryService(conn).get_badge_counts("b1")
        assert counts["pending_confirmation"] == 1

    def test_counts_weight_adjustments_pending(self):
        conn = self._db()
        self._insert_order(conn, customer_approval_status="PENDING")
        counts = OrdersDeliveryBadgeQueryService(conn).get_badge_counts("b1")
        assert counts["weight_adjustments_pending"] == 1

    def test_degrades_to_zero_on_missing_table(self):
        conn = sqlite3.connect(":memory:")  # no schema created at all
        counts = OrdersDeliveryBadgeQueryService(conn).get_badge_counts("b1")
        assert all(value == 0 for value in counts.values())

    def test_counts_settlements_pending_review(self):
        """ORD-27: `driver_settlements` did not exist when ORD-4 wrote this
        service (hardcoded 0); ORD-21 built it, closing the gap."""
        conn = self._db()
        conn.execute(
            "INSERT INTO driver_settlements (id, driver_id, branch_id, status,"
            " created_at, updated_at) VALUES ('s1','d1','b1','PENDING_REVIEW','t','t')")
        conn.execute(
            "INSERT INTO driver_settlements (id, driver_id, branch_id, status,"
            " created_at, updated_at) VALUES ('s2','d1','other-branch','PENDING_REVIEW','t','t')")
        counts = OrdersDeliveryBadgeQueryService(conn).get_badge_counts("b1")
        assert counts["settlements_pending_review"] == 1

    def test_counts_critical_alerts_from_notification_inbox(self):
        """ORD-27: `notification_inbox` alerts did not exist when ORD-4 wrote
        this service (hardcoded 0); ORD-26 built the 'entrega_fallida' alert,
        closing the gap. Scoped to that specific tipo — this badge must not
        count unrelated inbox entries from other modules."""
        conn = self._db()
        conn.execute(
            "CREATE TABLE notification_inbox (id TEXT PRIMARY KEY, empleado_id TEXT,"
            " tipo TEXT, titulo TEXT, cuerpo TEXT, datos TEXT, sucursal_id TEXT,"
            " leido INTEGER DEFAULT 0, leido_at TEXT, created_at TEXT)")
        conn.execute(
            "INSERT INTO notification_inbox (id, empleado_id, tipo, sucursal_id, leido)"
            " VALUES ('n1','e1','entrega_fallida','b1',0)")
        conn.execute(
            "INSERT INTO notification_inbox (id, empleado_id, tipo, sucursal_id, leido)"
            " VALUES ('n2','e1','entrega_fallida','b1',1)")  # already read
        conn.execute(
            "INSERT INTO notification_inbox (id, empleado_id, tipo, sucursal_id, leido)"
            " VALUES ('n3','e1','pedido_whatsapp_nuevo','b1',0)")  # unrelated module
        counts = OrdersDeliveryBadgeQueryService(conn).get_badge_counts("b1")
        assert counts["critical_alerts"] == 1
