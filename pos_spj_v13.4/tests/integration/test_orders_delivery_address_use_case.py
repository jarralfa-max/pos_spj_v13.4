"""ORD-7 — SetOrderDeliveryAddressUseCase end-to-end: address capture, zone
resolution, delivery fee assignment, real repository round-trips."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.orders_delivery.authorization import OrdersDeliveryAuthorizationPolicy
from backend.application.orders_delivery.use_cases.address_use_cases import (
    SetOrderDeliveryAddressUseCase,
)
from backend.application.orders_delivery.use_cases.order_capture_use_cases import (
    CreateCustomerOrderUseCase,
)
from backend.domain.orders_delivery.delivery_zone import DeliveryZone
from backend.infrastructure.db.repositories.orders_delivery.address_repository import (
    OrderAddressRepository,
)
from backend.infrastructure.db.repositories.orders_delivery.customer_order_repository import (
    CustomerOrderRepository,
)
from backend.infrastructure.db.repositories.orders_delivery.delivery_zone_repository import (
    DeliveryZoneRepository,
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


def _create_delivery_order(conn, branch_id: str) -> str:
    result = CreateCustomerOrderUseCase(_allow_all()).execute(
        conn, branch_id=branch_id, channel="WHATSAPP", order_type="STANDARD",
        fulfillment_type="HOME_DELIVERY",
        lines=[{"product_id": new_uuid(), "unit_price": "300.00", "requested_quantity": "1"}],
        actor_user_id=new_uuid(), operation_id=new_uuid())
    return result.entity_id


class TestSetOrderDeliveryAddressUseCase:
    def test_assigns_zone_and_fee_for_matching_postal_code(self, conn):
        branch_id = new_uuid()
        zone = DeliveryZone.create(
            branch_id=branch_id, name="Centro", postal_codes=("06000",),
            delivery_fee=Decimal("35.00"))
        DeliveryZoneRepository(conn).save(zone)
        order_id = _create_delivery_order(conn, branch_id)

        result = SetOrderDeliveryAddressUseCase(_allow_all()).execute(
            conn, order_id=order_id, recipient_name="Ana", recipient_phone="5555555555",
            street="Reforma", exterior_number="100", postal_code="06000",
            actor_user_id=new_uuid(), operation_id=new_uuid())

        assert result.success
        assert result.data["order"].grand_total == Decimal("335.00")
        reloaded = CustomerOrderRepository(conn).get(order_id)
        assert reloaded.delivery_fee == Decimal("35.00")
        assert reloaded.delivery_address_id == result.data["address_id"]

    def test_fails_when_no_zone_covers_postal_code(self, conn):
        branch_id = new_uuid()
        order_id = _create_delivery_order(conn, branch_id)
        result = SetOrderDeliveryAddressUseCase(_allow_all()).execute(
            conn, order_id=order_id, recipient_name="Ana", recipient_phone="5555555555",
            street="Reforma", exterior_number="100", postal_code="99999",
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "DELIVERY_ZONE_NOT_AVAILABLE"

    def test_counter_order_skips_zone_resolution(self, conn):
        """A COUNTER order doesn't need a zone — setting an address (e.g.
        for a receipt) must not fail just because no zone exists."""
        branch_id = new_uuid()
        result_create = CreateCustomerOrderUseCase(_allow_all()).execute(
            conn, branch_id=branch_id, channel="POS", order_type="STANDARD",
            fulfillment_type="COUNTER",
            lines=[{"product_id": new_uuid(), "unit_price": "50.00", "requested_quantity": "1"}],
            actor_user_id=new_uuid(), operation_id=new_uuid())
        result = SetOrderDeliveryAddressUseCase(_allow_all()).execute(
            conn, order_id=result_create.entity_id, recipient_name="Ana",
            recipient_phone="5555555555", street="Reforma", exterior_number="100",
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert result.success

    def test_address_persists_and_reloads(self, conn):
        branch_id = new_uuid()
        zone = DeliveryZone.create(branch_id=branch_id, name="Centro", postal_codes=("06000",))
        DeliveryZoneRepository(conn).save(zone)
        order_id = _create_delivery_order(conn, branch_id)
        SetOrderDeliveryAddressUseCase(_allow_all()).execute(
            conn, order_id=order_id, recipient_name="Ana", recipient_phone="5555555555",
            street="Reforma", exterior_number="100", postal_code="06000",
            actor_user_id=new_uuid(), operation_id=new_uuid())
        reloaded = OrderAddressRepository(conn).get_by_order_id(order_id)
        assert reloaded.recipient_name == "Ana"
        assert reloaded.delivery_zone_id == zone.id

    def test_denies_without_permission(self, conn):
        from backend.application.orders_delivery.authorization import (
            DenyAllOrdersDeliveryPermissionCheckerForTests,
        )
        branch_id = new_uuid()
        order_id = _create_delivery_order(conn, branch_id)
        policy = OrdersDeliveryAuthorizationPolicy(DenyAllOrdersDeliveryPermissionCheckerForTests())
        result = SetOrderDeliveryAddressUseCase(policy).execute(
            conn, order_id=order_id, recipient_name="Ana", recipient_phone="5555555555",
            street="Reforma", exterior_number="100",
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"
