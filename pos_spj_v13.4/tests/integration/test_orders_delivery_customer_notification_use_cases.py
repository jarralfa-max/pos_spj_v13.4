"""ORD-23 — customer WhatsApp notifications: the automatic first
notification fired from `EvaluateCatchWeightUseCase`/`ProposeSubstitutionUseCase`/
`MarkReadyForPickupUseCase`, plus the manual `ResendCustomerApprovalNotificationUseCase`.
A `_FakeWhatsAppClient` is injected everywhere so these tests never touch the
real network (the actual `OrdersDeliveryWhatsAppClient` wrapping the real
microservice REST client is exercised separately by its own unit test)."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.orders_delivery.authorization import OrdersDeliveryAuthorizationPolicy
from backend.application.orders_delivery.use_cases.catch_weight_use_cases import (
    EvaluateCatchWeightUseCase,
)
from backend.application.orders_delivery.use_cases.customer_notification_use_cases import (
    ResendCustomerApprovalNotificationUseCase,
)
from backend.application.orders_delivery.use_cases.inventory_use_cases import (
    ReserveOrderInventoryUseCase,
)
from backend.application.orders_delivery.use_cases.order_capture_use_cases import (
    ConfirmCustomerOrderUseCase,
    CreateCustomerOrderUseCase,
)
from backend.application.orders_delivery.use_cases.pickup_use_cases import (
    MarkReadyForPickupUseCase,
)
from backend.application.orders_delivery.use_cases.preparation_use_cases import (
    AssignPreparationUseCase,
    CompletePreparationUseCase,
    RecordPreparedLineUseCase,
    StartPreparationUseCase,
)
from backend.application.orders_delivery.use_cases.substitution_use_cases import (
    ProposeSubstitutionUseCase,
)
from backend.infrastructure.db.repositories.orders_delivery.customer_order_repository import (
    CustomerOrderRepository,
)
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.db.schema.orders_delivery_schema import create_orders_delivery_schema
from backend.shared.ids import new_uuid


class _FakeWhatsAppClient:
    def __init__(self, *, deliver: bool = True) -> None:
        self.deliver = deliver
        self.pickup_calls: list[dict] = []
        self.approval_calls: list[dict] = []

    def notify_ready_for_pickup(self, *, phone: str, order_number: str, branch_name: str = "") -> bool:
        self.pickup_calls.append(
            {"phone": phone, "order_number": order_number, "branch_name": branch_name})
        return self.deliver and bool(phone)

    def notify_customer_approval_required(self, *, phone: str, order_number: str, reason: str) -> bool:
        self.approval_calls.append(
            {"phone": phone, "order_number": order_number, "reason": reason})
        return self.deliver and bool(phone)


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


def _order_ready_for_weight_evaluation(conn) -> tuple[str, str]:
    """Returns (order_id, line_id) for a confirmed, reserved, in-preparation
    catch-weight order — one 5kg line."""
    branch_id, product_id = new_uuid(), new_uuid()
    _seed_balance(conn, product_id=product_id, branch_id=branch_id)
    result = CreateCustomerOrderUseCase(_allow_all()).execute(
        conn, branch_id=branch_id, channel="POS", order_type="STANDARD",
        fulfillment_type="COUNTER", contact_phone="+525512345678",
        lines=[{"product_id": product_id, "unit_price": "100.00",
                "requested_weight": "5", "catch_weight_enabled": True}],
        actor_user_id=new_uuid(), operation_id=new_uuid())
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
        conn, order_id=order_id, line_id=line_id, weight="6",
        actor_user_id=new_uuid(), operation_id=new_uuid())
    return order_id, line_id


class TestCatchWeightNotification:
    def test_sends_notification_when_out_of_tolerance(self, conn):
        order_id, line_id = _order_ready_for_weight_evaluation(conn)
        fake = _FakeWhatsAppClient()

        result = EvaluateCatchWeightUseCase(_allow_all(), whatsapp_client=fake).execute(
            conn, order_id=order_id, line_id=line_id, tolerance_pct=Decimal("2"),
            actor_user_id=new_uuid(), operation_id=new_uuid())

        assert result.success
        assert result.data["within_tolerance"] is False
        assert result.data["notification_sent"] is True
        assert len(fake.approval_calls) == 1
        assert fake.approval_calls[0]["phone"] == "+525512345678"

    def test_no_notification_when_within_tolerance(self, conn):
        order_id, line_id = _order_ready_for_weight_evaluation(conn)
        fake = _FakeWhatsAppClient()

        result = EvaluateCatchWeightUseCase(_allow_all(), whatsapp_client=fake).execute(
            conn, order_id=order_id, line_id=line_id, tolerance_pct=Decimal("50"),
            actor_user_id=new_uuid(), operation_id=new_uuid())

        assert result.success
        assert result.data["within_tolerance"] is True
        assert result.data["notification_sent"] is False
        assert fake.approval_calls == []

    def test_notification_failure_does_not_fail_the_evaluation(self, conn):
        order_id, line_id = _order_ready_for_weight_evaluation(conn)
        fake = _FakeWhatsAppClient(deliver=False)

        result = EvaluateCatchWeightUseCase(_allow_all(), whatsapp_client=fake).execute(
            conn, order_id=order_id, line_id=line_id, tolerance_pct=Decimal("2"),
            actor_user_id=new_uuid(), operation_id=new_uuid())

        assert result.success
        assert result.data["notification_sent"] is False
        order = CustomerOrderRepository(conn).get(order_id)
        assert order.customer_approval_status.value == "PENDING"


class TestSubstitutionNotification:
    def test_sends_notification_on_propose(self, conn):
        branch_id, product_id = new_uuid(), new_uuid()
        result = CreateCustomerOrderUseCase(_allow_all()).execute(
            conn, branch_id=branch_id, channel="POS", order_type="STANDARD",
            fulfillment_type="COUNTER", contact_phone="+525512345678",
            lines=[{"product_id": product_id, "unit_price": "10.00", "requested_quantity": "3"}],
            actor_user_id=new_uuid(), operation_id=new_uuid())
        order_id = result.entity_id
        line_id = CustomerOrderRepository(conn).get(order_id).lines[0].id
        fake = _FakeWhatsAppClient()

        result = ProposeSubstitutionUseCase(_allow_all(), whatsapp_client=fake).execute(
            conn, order_id=order_id, line_id=line_id, substitute_product_id=new_uuid(),
            substitution_type="EQUIVALENT_PRODUCT", new_unit_price=Decimal("12.00"),
            reason="Sin existencia", actor_user_id=new_uuid(), operation_id=new_uuid())

        assert result.success
        assert result.data["notification_sent"] is True
        assert "sustitución" in fake.approval_calls[0]["reason"]


class TestReadyForPickupNotification:
    def test_sends_notification_when_marked_ready(self, conn):
        branch_id, product_id = new_uuid(), new_uuid()
        _seed_balance(conn, product_id=product_id, branch_id=branch_id)
        result = CreateCustomerOrderUseCase(_allow_all()).execute(
            conn, branch_id=branch_id, channel="POS", order_type="STANDARD",
            fulfillment_type="COUNTER", contact_phone="+525512345678",
            lines=[{"product_id": product_id, "unit_price": "10.00", "requested_quantity": "1"}],
            actor_user_id=new_uuid(), operation_id=new_uuid())
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
            conn, order_id=order_id, line_id=line_id, quantity="1",
            actor_user_id=new_uuid(), operation_id=new_uuid())
        CompletePreparationUseCase(_allow_all()).execute(
            conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        fake = _FakeWhatsAppClient()

        result = MarkReadyForPickupUseCase(_allow_all(), whatsapp_client=fake).execute(
            conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())

        assert result.success
        assert result.data["notification_sent"] is True
        assert fake.pickup_calls[0]["phone"] == "+525512345678"


class TestResendCustomerApprovalNotificationUseCase:
    def test_resends_for_pending_weight_adjustment(self, conn):
        order_id, line_id = _order_ready_for_weight_evaluation(conn)
        silent = _FakeWhatsAppClient(deliver=False)
        EvaluateCatchWeightUseCase(_allow_all(), whatsapp_client=silent).execute(
            conn, order_id=order_id, line_id=line_id, tolerance_pct=Decimal("2"),
            actor_user_id=new_uuid(), operation_id=new_uuid())

        fake = _FakeWhatsAppClient()
        result = ResendCustomerApprovalNotificationUseCase(_allow_all(), whatsapp_client=fake).execute(
            conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())

        assert result.success
        assert result.data["notification_sent"] is True
        assert "peso" in fake.approval_calls[0]["reason"]

    def test_fails_when_nothing_pending(self, conn):
        branch_id, product_id = new_uuid(), new_uuid()
        result = CreateCustomerOrderUseCase(_allow_all()).execute(
            conn, branch_id=branch_id, channel="POS", order_type="STANDARD",
            fulfillment_type="COUNTER",
            lines=[{"product_id": product_id, "unit_price": "10.00", "requested_quantity": "1"}],
            actor_user_id=new_uuid(), operation_id=new_uuid())
        order_id = result.entity_id

        result = ResendCustomerApprovalNotificationUseCase(
            _allow_all(), whatsapp_client=_FakeWhatsAppClient()).execute(
            conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())

        assert not result.success
        assert result.error_code == "CUSTOMER_APPROVAL_REQUIRED"
