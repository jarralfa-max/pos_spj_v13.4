"""ORD-14 — pickup/counter (§30): PickupPolicy, CustomerOrder.
mark_ready_for_pickup()/complete_pickup(), and the mark_reserved() ->
IN_FULFILLMENT fix that made complete_pickup() reachable at all."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.orders_delivery.entities import CustomerOrder, CustomerOrderLine
from backend.domain.orders_delivery.enums import (
    FulfillmentStatus,
    FulfillmentType,
    OrderChannel,
    OrderStatus,
    OrderType,
    PaymentStatus,
)
from backend.domain.orders_delivery.exceptions import (
    OrderPreparationNotAllowedError,
    PaymentRequiredForPickupError,
    PickupVerificationFailedError,
)
from backend.domain.orders_delivery.value_objects.order_quantity import OrderQuantity
from backend.shared.ids import new_uuid


def _ready_pickup_order() -> CustomerOrder:
    order = CustomerOrder.create(
        branch_id=new_uuid(), channel=OrderChannel.POS, order_type=OrderType.STANDARD,
        fulfillment_type=FulfillmentType.COUNTER)
    order.add_line(CustomerOrderLine.create(
        order_id=order.id, product_id=new_uuid(), unit_price=Decimal("10"),
        requested_quantity=OrderQuantity(Decimal("1"))))
    order.confirm(confirmed_by_user_id=new_uuid())
    order.move_to_fulfillment()
    order.fulfillment_status = FulfillmentStatus.READY  # ORD-9's own step, out of scope here
    return order


class TestMarkReadyForPickup:
    def test_requires_pickup_fulfillment_type(self):
        order = CustomerOrder.create(
            branch_id=new_uuid(), channel=OrderChannel.WHATSAPP, order_type=OrderType.STANDARD,
            fulfillment_type=FulfillmentType.HOME_DELIVERY)
        with pytest.raises(OrderPreparationNotAllowedError):
            order.mark_ready_for_pickup(verification_code="123456")

    def test_requires_ready_fulfillment_status(self):
        order = CustomerOrder.create(
            branch_id=new_uuid(), channel=OrderChannel.POS, order_type=OrderType.STANDARD,
            fulfillment_type=FulfillmentType.COUNTER)
        with pytest.raises(OrderPreparationNotAllowedError):
            order.mark_ready_for_pickup(verification_code="123456")

    def test_sets_verification_code(self):
        order = _ready_pickup_order()
        order.mark_ready_for_pickup(verification_code="654321")
        assert order.pickup_verification_code == "654321"


class TestCompletePickup:
    def test_wrong_code_fails(self):
        order = _ready_pickup_order()
        order.mark_ready_for_pickup(verification_code="111111")
        order.payment_status = PaymentStatus.PAID
        with pytest.raises(PickupVerificationFailedError):
            order.complete_pickup(presented_code="000000")

    def test_unpaid_order_fails(self):
        order = _ready_pickup_order()
        order.mark_ready_for_pickup(verification_code="111111")
        with pytest.raises(PaymentRequiredForPickupError):
            order.complete_pickup(presented_code="111111")

    def test_correct_code_and_paid_completes(self):
        order = _ready_pickup_order()
        order.mark_ready_for_pickup(verification_code="111111")
        order.payment_status = PaymentStatus.PAID
        order.complete_pickup(presented_code="111111")
        assert order.status == OrderStatus.COMPLETED
        assert order.fulfillment_status == FulfillmentStatus.DELIVERED

    def test_home_delivery_order_cannot_use_pickup_completion(self):
        order = CustomerOrder.create(
            branch_id=new_uuid(), channel=OrderChannel.WHATSAPP, order_type=OrderType.STANDARD,
            fulfillment_type=FulfillmentType.HOME_DELIVERY)
        with pytest.raises(OrderPreparationNotAllowedError):
            order.complete_pickup(presented_code="000000")


class TestMarkReservedAdvancesFulfillment:
    def test_mark_reserved_moves_confirmed_order_to_in_fulfillment(self):
        order = CustomerOrder.create(
            branch_id=new_uuid(), channel=OrderChannel.POS, order_type=OrderType.STANDARD,
            fulfillment_type=FulfillmentType.COUNTER)
        order.add_line(CustomerOrderLine.create(
            order_id=order.id, product_id=new_uuid(), unit_price=Decimal("10"),
            requested_quantity=OrderQuantity(Decimal("1"))))
        order.confirm(confirmed_by_user_id=new_uuid())
        assert order.status == OrderStatus.CONFIRMED
        order.mark_reserved()
        assert order.status == OrderStatus.IN_FULFILLMENT
        assert order.fulfillment_status == FulfillmentStatus.RESERVED
