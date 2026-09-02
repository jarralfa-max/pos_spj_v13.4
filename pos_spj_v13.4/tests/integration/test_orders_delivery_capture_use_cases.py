"""ORD-5 — omnichannel order capture (§17 create/confirm flow, §18
deduplication), exercised end-to-end against a real SQLite connection with
the ORD-3 schema. First real caller of
`OrdersDeliveryAuthorizationPolicy.require()` (ORD-1 was foundation-only)."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.orders_delivery.authorization import OrdersDeliveryAuthorizationPolicy
from backend.application.orders_delivery.permissions import OrdersDeliveryPermissions
from backend.application.orders_delivery.use_cases.order_capture_use_cases import (
    ConfirmCustomerOrderUseCase,
    CreateCustomerOrderUseCase,
)
from backend.infrastructure.db.schema.orders_delivery_schema import create_orders_delivery_schema
from backend.shared.ids import new_uuid


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    create_orders_delivery_schema(connection)
    yield connection
    connection.close()


def _allow_all() -> OrdersDeliveryAuthorizationPolicy:
    return OrdersDeliveryAuthorizationPolicy.permissive_for_tests()


def _sample_lines() -> list[dict]:
    return [{
        "product_id": new_uuid(), "unit_price": "10.00",
        "requested_quantity": "2", "requested_quantity_unit": "PZA",
    }]


class TestCreateCustomerOrderUseCase:
    def test_creates_order_with_lines(self, conn):
        branch_id = new_uuid()
        result = CreateCustomerOrderUseCase(_allow_all()).execute(
            conn, branch_id=branch_id, channel="POS", order_type="STANDARD",
            fulfillment_type="COUNTER", lines=_sample_lines(),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        assert result.data["order"].grand_total == Decimal("20.00")
        assert len(result.data["order"].lines) == 1

    def test_denies_without_permission(self, conn):
        from backend.application.orders_delivery.authorization import (
            DenyAllOrdersDeliveryPermissionCheckerForTests,
        )
        policy = OrdersDeliveryAuthorizationPolicy(DenyAllOrdersDeliveryPermissionCheckerForTests())
        result = CreateCustomerOrderUseCase(policy).execute(
            conn, branch_id=new_uuid(), channel="POS", order_type="STANDARD",
            fulfillment_type="COUNTER", lines=_sample_lines(),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "PERMISSION_DENIED"

    def test_retry_with_same_operation_id_is_idempotent(self, conn):
        branch_id = new_uuid()
        operation_id = new_uuid()
        lines = _sample_lines()
        first = CreateCustomerOrderUseCase(_allow_all()).execute(
            conn, branch_id=branch_id, channel="POS", order_type="STANDARD",
            fulfillment_type="COUNTER", lines=lines,
            actor_user_id=new_uuid(), operation_id=operation_id)
        second = CreateCustomerOrderUseCase(_allow_all()).execute(
            conn, branch_id=branch_id, channel="POS", order_type="STANDARD",
            fulfillment_type="COUNTER", lines=lines,
            actor_user_id=new_uuid(), operation_id=operation_id)
        assert first.success and second.success
        assert first.entity_id == second.entity_id
        count = conn.execute("SELECT COUNT(*) FROM customer_orders").fetchone()[0]
        assert count == 1

    def test_whatsapp_retry_with_same_external_reference_is_idempotent(self, conn):
        """§18: a WhatsApp webhook retry must not create a second order."""
        branch_id = new_uuid()
        first = CreateCustomerOrderUseCase(_allow_all()).execute(
            conn, branch_id=branch_id, channel="WHATSAPP", order_type="STANDARD",
            fulfillment_type="HOME_DELIVERY", lines=_sample_lines(),
            actor_user_id=new_uuid(), operation_id=new_uuid(),
            external_order_reference="wa-msg-123")
        second = CreateCustomerOrderUseCase(_allow_all()).execute(
            conn, branch_id=branch_id, channel="WHATSAPP", order_type="STANDARD",
            fulfillment_type="HOME_DELIVERY", lines=_sample_lines(),
            actor_user_id=new_uuid(), operation_id=new_uuid(),
            external_order_reference="wa-msg-123")
        assert first.success and second.success
        assert first.entity_id == second.entity_id
        count = conn.execute("SELECT COUNT(*) FROM customer_orders").fetchone()[0]
        assert count == 1

    def test_different_channels_same_external_reference_do_not_collide(self, conn):
        """Dedup is scoped to (channel, external_order_reference) — the same
        raw reference string on a different channel is not the same order."""
        branch_id = new_uuid()
        pos_order = CreateCustomerOrderUseCase(_allow_all()).execute(
            conn, branch_id=branch_id, channel="POS", order_type="STANDARD",
            fulfillment_type="COUNTER", lines=_sample_lines(),
            actor_user_id=new_uuid(), operation_id=new_uuid(),
            external_order_reference="ref-1")
        wa_order = CreateCustomerOrderUseCase(_allow_all()).execute(
            conn, branch_id=branch_id, channel="WHATSAPP", order_type="STANDARD",
            fulfillment_type="HOME_DELIVERY", lines=_sample_lines(),
            actor_user_id=new_uuid(), operation_id=new_uuid(),
            external_order_reference="ref-1")
        assert pos_order.entity_id != wa_order.entity_id

    def test_rejects_line_without_quantity_or_weight(self, conn):
        result = CreateCustomerOrderUseCase(_allow_all()).execute(
            conn, branch_id=new_uuid(), channel="POS", order_type="STANDARD",
            fulfillment_type="COUNTER",
            lines=[{"product_id": new_uuid(), "unit_price": "10.00"}],
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "INVALID_QUANTITY"

    def test_persists_and_reloads_catch_weight_line(self, conn):
        branch_id = new_uuid()
        result = CreateCustomerOrderUseCase(_allow_all()).execute(
            conn, branch_id=branch_id, channel="POS", order_type="STANDARD",
            fulfillment_type="COUNTER",
            lines=[{
                "product_id": new_uuid(), "unit_price": "100.00",
                "requested_weight": "2.5", "requested_weight_unit": "KG",
                "catch_weight_enabled": True,
            }],
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        from backend.infrastructure.db.repositories.orders_delivery.customer_order_repository import (
            CustomerOrderRepository,
        )
        reloaded = CustomerOrderRepository(conn).get(result.entity_id)
        assert reloaded.lines[0].catch_weight_enabled is True
        assert reloaded.lines[0].requested_subtotal == Decimal("250.00")


class TestConfirmCustomerOrderUseCase:
    def _create(self, conn) -> str:
        result = CreateCustomerOrderUseCase(_allow_all()).execute(
            conn, branch_id=new_uuid(), channel="POS", order_type="STANDARD",
            fulfillment_type="COUNTER", lines=_sample_lines(),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        return result.entity_id

    def test_confirm_transitions_status(self, conn):
        order_id = self._create(conn)
        result = ConfirmCustomerOrderUseCase(_allow_all()).execute(
            conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        assert result.data["order"].status == "CONFIRMED"

    def test_confirm_unknown_order_fails(self, conn):
        result = ConfirmCustomerOrderUseCase(_allow_all()).execute(
            conn, order_id=new_uuid(), actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "NOT_FOUND"

    def test_double_confirm_fails(self, conn):
        order_id = self._create(conn)
        ConfirmCustomerOrderUseCase(_allow_all()).execute(
            conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        result = ConfirmCustomerOrderUseCase(_allow_all()).execute(
            conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "INVALID_STATE"

    def test_confirm_enqueues_outbox_event(self, conn):
        order_id = self._create(conn)
        ConfirmCustomerOrderUseCase(_allow_all()).execute(
            conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        row = conn.execute(
            "SELECT event_type FROM orders_delivery_outbox WHERE aggregate_id=? AND event_type=?",
            (order_id, "ORDER_CONFIRMED")).fetchone()
        assert row is not None
