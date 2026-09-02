"""ORD-13 — CreatePackageUseCase/SealPackageUseCase, end-to-end through
capture -> confirm -> package -> seal."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.orders_delivery.authorization import OrdersDeliveryAuthorizationPolicy
from backend.application.orders_delivery.use_cases.order_capture_use_cases import (
    ConfirmCustomerOrderUseCase,
    CreateCustomerOrderUseCase,
)
from backend.application.orders_delivery.use_cases.packaging_use_cases import (
    CreatePackageUseCase,
    SealPackageUseCase,
)
from backend.infrastructure.db.repositories.orders_delivery.customer_order_repository import (
    CustomerOrderRepository,
)
from backend.infrastructure.db.repositories.orders_delivery.package_repository import (
    OrderPackageRepository,
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


def _confirmed_order(conn) -> tuple[str, str]:
    result = CreateCustomerOrderUseCase(_allow_all()).execute(
        conn, branch_id=new_uuid(), channel="POS", order_type="STANDARD",
        fulfillment_type="COUNTER",
        lines=[{"product_id": new_uuid(), "unit_price": "10.00", "requested_quantity": "1"}],
        actor_user_id=new_uuid(), operation_id=new_uuid())
    order_id = result.entity_id
    ConfirmCustomerOrderUseCase(_allow_all()).execute(
        conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
    line_id = CustomerOrderRepository(conn).get(order_id).lines[0].id
    return order_id, line_id


class TestCreatePackageUseCase:
    def test_creates_package_and_assigns_line(self, conn):
        order_id, line_id = _confirmed_order(conn)
        result = CreatePackageUseCase(_allow_all()).execute(
            conn, order_id=order_id, package_number="1", package_type="BOX",
            line_ids=[line_id], tare=Decimal("0.2"), gross_weight=Decimal("1.2"),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        assert result.data["net_weight"] == Decimal("1.0")
        reloaded = CustomerOrderRepository(conn).get(order_id)
        assert reloaded.lines[0].package_id == result.entity_id

    def test_fails_with_line_not_in_order(self, conn):
        order_id, _ = _confirmed_order(conn)
        result = CreatePackageUseCase(_allow_all()).execute(
            conn, order_id=order_id, package_number="1", package_type="BOX",
            line_ids=[new_uuid()], actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "LINE_NOT_FOUND"

    def test_denies_without_permission(self, conn):
        from backend.application.orders_delivery.authorization import (
            DenyAllOrdersDeliveryPermissionCheckerForTests,
        )
        order_id, line_id = _confirmed_order(conn)
        policy = OrdersDeliveryAuthorizationPolicy(DenyAllOrdersDeliveryPermissionCheckerForTests())
        result = CreatePackageUseCase(policy).execute(
            conn, order_id=order_id, package_number="1", package_type="BOX",
            line_ids=[line_id], actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"


class TestSealPackageUseCase:
    def test_seals_package(self, conn):
        order_id, line_id = _confirmed_order(conn)
        create_result = CreatePackageUseCase(_allow_all()).execute(
            conn, order_id=order_id, package_number="1", package_type="BOX",
            line_ids=[line_id], actor_user_id=new_uuid(), operation_id=new_uuid())
        result = SealPackageUseCase(_allow_all()).execute(
            conn, package_id=create_result.entity_id, seal_number="SEAL-1",
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        reloaded = OrderPackageRepository(conn).get(create_result.entity_id)
        assert reloaded.status.value == "SEALED"
        assert reloaded.seal_number == "SEAL-1"

    def test_seal_unknown_package_fails(self, conn):
        result = SealPackageUseCase(_allow_all()).execute(
            conn, package_id=new_uuid(), seal_number="SEAL-1",
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "INVALID_PACKAGE"
