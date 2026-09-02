"""ORD-12 — ProposeSubstitutionUseCase/AcceptSubstitutionUseCase/
RejectSubstitutionUseCase, end-to-end through capture -> confirm -> propose
-> accept/reject."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.orders_delivery.authorization import OrdersDeliveryAuthorizationPolicy
from backend.application.orders_delivery.use_cases.order_capture_use_cases import (
    ConfirmCustomerOrderUseCase,
    CreateCustomerOrderUseCase,
)
from backend.application.orders_delivery.use_cases.substitution_use_cases import (
    AcceptSubstitutionUseCase,
    ProposeSubstitutionUseCase,
    RejectSubstitutionUseCase,
)
from backend.infrastructure.db.repositories.orders_delivery.customer_order_repository import (
    CustomerOrderRepository,
)
from backend.infrastructure.db.schema.orders_delivery_schema import create_orders_delivery_schema
from backend.shared.ids import new_uuid


class _NoOpWhatsAppClient:
    """ORD-23: `ProposeSubstitutionUseCase` now fires a best-effort WhatsApp
    notification — keeps this ORD-12-era test network-free."""

    def notify_customer_approval_required(self, **_kwargs) -> bool:
        return False


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    create_orders_delivery_schema(connection)
    yield connection
    connection.close()


def _allow_all() -> OrdersDeliveryAuthorizationPolicy:
    return OrdersDeliveryAuthorizationPolicy.permissive_for_tests()


def _confirmed_order(conn) -> tuple[str, str]:
    result = CreateCustomerOrderUseCase(_allow_all()).execute(
        conn, branch_id=new_uuid(), channel="POS", order_type="STANDARD",
        fulfillment_type="COUNTER",
        lines=[{"product_id": new_uuid(), "unit_price": "50.00", "requested_quantity": "3"}],
        actor_user_id=new_uuid(), operation_id=new_uuid())
    order_id = result.entity_id
    ConfirmCustomerOrderUseCase(_allow_all()).execute(
        conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
    line_id = CustomerOrderRepository(conn).get(order_id).lines[0].id
    return order_id, line_id


class TestProposeSubstitutionUseCase:
    def test_proposes_and_persists(self, conn):
        order_id, line_id = _confirmed_order(conn)
        result = ProposeSubstitutionUseCase(_allow_all(), whatsapp_client=_NoOpWhatsAppClient()).execute(
            conn, order_id=order_id, line_id=line_id, substitute_product_id=new_uuid(),
            substitution_type="EQUIVALENT_PRODUCT", new_unit_price=Decimal("60.00"),
            reason="Sin existencia", actor_user_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        reloaded = CustomerOrderRepository(conn).get(order_id)
        assert reloaded.lines[0].status.value == "PENDING_CUSTOMER_APPROVAL"
        assert reloaded.customer_approval_status.value == "PENDING"

    def test_denies_without_permission(self, conn):
        from backend.application.orders_delivery.authorization import (
            DenyAllOrdersDeliveryPermissionCheckerForTests,
        )
        order_id, line_id = _confirmed_order(conn)
        policy = OrdersDeliveryAuthorizationPolicy(DenyAllOrdersDeliveryPermissionCheckerForTests())
        result = ProposeSubstitutionUseCase(policy).execute(
            conn, order_id=order_id, line_id=line_id, substitute_product_id=new_uuid(),
            substitution_type="EQUIVALENT_PRODUCT", new_unit_price=Decimal("60.00"),
            reason="motivo", actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"

    def test_enqueues_proposed_event(self, conn):
        order_id, line_id = _confirmed_order(conn)
        ProposeSubstitutionUseCase(_allow_all(), whatsapp_client=_NoOpWhatsAppClient()).execute(
            conn, order_id=order_id, line_id=line_id, substitute_product_id=new_uuid(),
            substitution_type="EQUIVALENT_PRODUCT", new_unit_price=Decimal("60.00"),
            reason="motivo", actor_user_id=new_uuid(), operation_id=new_uuid())
        row = conn.execute(
            "SELECT 1 FROM orders_delivery_outbox WHERE aggregate_id=? AND event_type=?",
            (order_id, "ORDER_SUBSTITUTION_PROPOSED")).fetchone()
        assert row is not None


class TestAcceptRejectSubstitutionUseCase:
    def test_accept_updates_price_and_totals(self, conn):
        order_id, line_id = _confirmed_order(conn)
        ProposeSubstitutionUseCase(_allow_all(), whatsapp_client=_NoOpWhatsAppClient()).execute(
            conn, order_id=order_id, line_id=line_id, substitute_product_id=new_uuid(),
            substitution_type="EQUIVALENT_PRODUCT", new_unit_price=Decimal("60.00"),
            reason="Sin existencia", actor_user_id=new_uuid(), operation_id=new_uuid())
        result = AcceptSubstitutionUseCase(_allow_all()).execute(
            conn, order_id=order_id, line_id=line_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert result.success
        assert result.data["order"].grand_total == Decimal("180.00")
        reloaded = CustomerOrderRepository(conn).get(order_id)
        assert reloaded.lines[0].status.value == "SUBSTITUTED"

    def test_reject_keeps_original_price(self, conn):
        order_id, line_id = _confirmed_order(conn)
        ProposeSubstitutionUseCase(_allow_all(), whatsapp_client=_NoOpWhatsAppClient()).execute(
            conn, order_id=order_id, line_id=line_id, substitute_product_id=new_uuid(),
            substitution_type="EQUIVALENT_PRODUCT", new_unit_price=Decimal("60.00"),
            reason="Sin existencia", actor_user_id=new_uuid(), operation_id=new_uuid())
        result = RejectSubstitutionUseCase(_allow_all()).execute(
            conn, order_id=order_id, line_id=line_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert result.success
        assert result.data["order"].grand_total == Decimal("150.00")
