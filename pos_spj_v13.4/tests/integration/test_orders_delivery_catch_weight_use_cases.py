"""ORD-10 — EvaluateCatchWeightUseCase/Accept/Reject/OverrideWeightAdjustment,
end-to-end through the full pipeline: capture -> confirm -> reserve ->
assign -> start -> record prepared -> evaluate."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.orders_delivery.authorization import OrdersDeliveryAuthorizationPolicy
from backend.application.orders_delivery.use_cases.catch_weight_use_cases import (
    AcceptWeightAdjustmentUseCase,
    EvaluateCatchWeightUseCase,
    OverrideWeightAdjustmentUseCase,
    RejectWeightAdjustmentUseCase,
)
from backend.application.orders_delivery.use_cases.inventory_use_cases import (
    ReserveOrderInventoryUseCase,
)
from backend.application.orders_delivery.use_cases.order_capture_use_cases import (
    ConfirmCustomerOrderUseCase,
    CreateCustomerOrderUseCase,
)
from backend.application.orders_delivery.use_cases.preparation_use_cases import (
    AssignPreparationUseCase,
    RecordPreparedLineUseCase,
    StartPreparationUseCase,
)
from backend.infrastructure.db.repositories.orders_delivery.customer_order_repository import (
    CustomerOrderRepository,
)
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.db.schema.orders_delivery_schema import create_orders_delivery_schema
from backend.shared.ids import new_uuid


class _NoOpWhatsAppClient:
    """ORD-23: `EvaluateCatchWeightUseCase` now fires a best-effort WhatsApp
    notification when a line goes out of tolerance. This phase's own tests
    predate ORD-23 and don't exercise that concern, so a no-op stub is
    injected to keep them fast and network-free."""

    def notify_customer_approval_required(self, **_kwargs) -> bool:
        return False


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    create_orders_delivery_schema(connection)
    create_inventory_schema(connection)
    yield connection
    connection.close()


def _allow_all() -> OrdersDeliveryAuthorizationPolicy:
    return OrdersDeliveryAuthorizationPolicy.permissive_for_tests()


def _seed_balance(conn, *, product_id: str, branch_id: str) -> None:
    conn.execute(
        "INSERT INTO inventory_balances (id, product_id, branch_id, warehouse_id,"
        " location_id, lot_id, serial_id, inventory_status, quantity, weight,"
        " reserved_quantity, reserved_weight, version, updated_at)"
        " VALUES (?,?,?,?,'','','','AVAILABLE','100','100','0','0',0,?)",
        (new_uuid(), product_id, branch_id, branch_id, "t"))


def _prepared_catch_weight_line(conn, *, prepared_weight: str) -> tuple[str, str]:
    branch_id, product_id = new_uuid(), new_uuid()
    _seed_balance(conn, product_id=product_id, branch_id=branch_id)
    result = CreateCustomerOrderUseCase(_allow_all()).execute(
        conn, branch_id=branch_id, channel="POS", order_type="STANDARD",
        fulfillment_type="COUNTER",
        lines=[{
            "product_id": product_id, "unit_price": "100.00",
            "requested_weight": "2.000", "requested_weight_unit": "KG",
            "catch_weight_enabled": True,
        }], actor_user_id=new_uuid(), operation_id=new_uuid())
    order_id = result.entity_id
    ConfirmCustomerOrderUseCase(_allow_all()).execute(
        conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
    ReserveOrderInventoryUseCase(_allow_all()).execute(
        conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
    AssignPreparationUseCase(_allow_all()).execute(
        conn, order_id=order_id, assigned_to_user_id=new_uuid(),
        actor_user_id=new_uuid(), operation_id=new_uuid())
    StartPreparationUseCase(_allow_all()).execute(
        conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
    line_id = CustomerOrderRepository(conn).get(order_id).lines[0].id
    RecordPreparedLineUseCase(_allow_all()).execute(
        conn, order_id=order_id, line_id=line_id, weight=prepared_weight,
        actor_user_id=new_uuid(), operation_id=new_uuid())
    return order_id, line_id


class TestEvaluateCatchWeightUseCase:
    def test_within_tolerance_finalizes_automatically(self, conn):
        order_id, line_id = _prepared_catch_weight_line(conn, prepared_weight="2.020")
        result = EvaluateCatchWeightUseCase(_allow_all(), whatsapp_client=_NoOpWhatsAppClient()).execute(
            conn, order_id=order_id, line_id=line_id, tolerance_pct=Decimal("5"),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        assert result.data["within_tolerance"] is True
        reloaded = CustomerOrderRepository(conn).get(order_id)
        assert reloaded.lines[0].final_weight.value == Decimal("2.020")
        assert reloaded.customer_approval_status.value == "NOT_REQUIRED"

    def test_outside_tolerance_requires_approval(self, conn):
        order_id, line_id = _prepared_catch_weight_line(conn, prepared_weight="2.600")
        result = EvaluateCatchWeightUseCase(_allow_all(), whatsapp_client=_NoOpWhatsAppClient()).execute(
            conn, order_id=order_id, line_id=line_id, tolerance_pct=Decimal("5"),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        assert result.data["within_tolerance"] is False
        reloaded = CustomerOrderRepository(conn).get(order_id)
        assert reloaded.lines[0].status.value == "PENDING_CUSTOMER_APPROVAL"
        assert reloaded.customer_approval_status.value == "PENDING"

    def test_enqueues_approval_required_event_when_out_of_tolerance(self, conn):
        order_id, line_id = _prepared_catch_weight_line(conn, prepared_weight="2.600")
        EvaluateCatchWeightUseCase(_allow_all(), whatsapp_client=_NoOpWhatsAppClient()).execute(
            conn, order_id=order_id, line_id=line_id, tolerance_pct=Decimal("5"),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        row = conn.execute(
            "SELECT 1 FROM orders_delivery_outbox WHERE aggregate_id=? AND event_type=?",
            (order_id, "ORDER_CUSTOMER_APPROVAL_REQUIRED")).fetchone()
        assert row is not None


class TestAcceptRejectWeightAdjustment:
    def test_accept_finalizes_line(self, conn):
        order_id, line_id = _prepared_catch_weight_line(conn, prepared_weight="2.600")
        EvaluateCatchWeightUseCase(_allow_all(), whatsapp_client=_NoOpWhatsAppClient()).execute(
            conn, order_id=order_id, line_id=line_id, tolerance_pct=Decimal("5"),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        result = AcceptWeightAdjustmentUseCase(_allow_all()).execute(
            conn, order_id=order_id, line_id=line_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert result.success
        reloaded = CustomerOrderRepository(conn).get(order_id)
        assert reloaded.lines[0].final_weight.value == Decimal("2.600")
        assert reloaded.totals.subtotal == Decimal("260.000")

    def test_reject_marks_line_rejected(self, conn):
        order_id, line_id = _prepared_catch_weight_line(conn, prepared_weight="2.600")
        EvaluateCatchWeightUseCase(_allow_all(), whatsapp_client=_NoOpWhatsAppClient()).execute(
            conn, order_id=order_id, line_id=line_id, tolerance_pct=Decimal("5"),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        result = RejectWeightAdjustmentUseCase(_allow_all()).execute(
            conn, order_id=order_id, line_id=line_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert result.success
        reloaded = CustomerOrderRepository(conn).get(order_id)
        assert reloaded.lines[0].status.value == "REJECTED"


class TestOverrideWeightAdjustmentUseCase:
    def test_supervisor_override_finalizes_line(self, conn):
        order_id, line_id = _prepared_catch_weight_line(conn, prepared_weight="2.600")
        EvaluateCatchWeightUseCase(_allow_all(), whatsapp_client=_NoOpWhatsAppClient()).execute(
            conn, order_id=order_id, line_id=line_id, tolerance_pct=Decimal("5"),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        requester, supervisor = new_uuid(), new_uuid()
        result = OverrideWeightAdjustmentUseCase(_allow_all()).execute(
            conn, order_id=order_id, line_id=line_id, requested_by=requester,
            authorizer_user_id=supervisor, reason="Cliente no localizable, autorizado por gerente",
            operation_id=new_uuid())
        assert result.success
        reloaded = CustomerOrderRepository(conn).get(order_id)
        assert reloaded.lines[0].final_weight.value == Decimal("2.600")

    def test_self_authorization_is_rejected(self, conn):
        order_id, line_id = _prepared_catch_weight_line(conn, prepared_weight="2.600")
        EvaluateCatchWeightUseCase(_allow_all(), whatsapp_client=_NoOpWhatsAppClient()).execute(
            conn, order_id=order_id, line_id=line_id, tolerance_pct=Decimal("5"),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        same_user = new_uuid()
        result = OverrideWeightAdjustmentUseCase(_allow_all()).execute(
            conn, order_id=order_id, line_id=line_id, requested_by=same_user,
            authorizer_user_id=same_user, reason="motivo", operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "SEGREGATION_OF_DUTIES"
