"""ORD-9 — preparation lifecycle (§25): CustomerOrder.assign_preparation()/
start_preparation()/complete_preparation()/cancel_preparation(),
CustomerOrderLine.record_prepared_amount(), OrderPreparationPolicy."""

from __future__ import annotations

import pytest

from backend.domain.orders_delivery.entities import CustomerOrder, CustomerOrderLine
from backend.domain.orders_delivery.enums import (
    FulfillmentStatus,
    FulfillmentType,
    OrderChannel,
    OrderLineStatus,
    OrderType,
    PreparationStatus,
)
from backend.domain.orders_delivery.exceptions import (
    InvalidOrderQuantityError,
    OrderPreparationNotAllowedError,
)
from backend.domain.orders_delivery.value_objects.order_quantity import OrderQuantity
from backend.shared.ids import new_uuid
from decimal import Decimal


def _reserved_order_with_line() -> CustomerOrder:
    order = CustomerOrder.create(
        branch_id=new_uuid(), channel=OrderChannel.POS, order_type=OrderType.STANDARD,
        fulfillment_type=FulfillmentType.COUNTER,
    )
    order.add_line(CustomerOrderLine.create(
        order_id=order.id, product_id=new_uuid(), unit_price=Decimal("10"),
        requested_quantity=OrderQuantity(Decimal("2"))))
    order.confirm(confirmed_by_user_id=new_uuid())
    order.fulfillment_status = FulfillmentStatus.RESERVED  # ORD-8's own step, out of scope here
    return order


class TestAssignPreparation:
    def test_assign_requires_reserved_fulfillment(self):
        order = CustomerOrder.create(
            branch_id=new_uuid(), channel=OrderChannel.POS, order_type=OrderType.STANDARD,
            fulfillment_type=FulfillmentType.COUNTER)
        with pytest.raises(OrderPreparationNotAllowedError):
            order.assign_preparation(assigned_to_user_id=new_uuid())

    def test_assign_sets_status_and_user(self):
        order = _reserved_order_with_line()
        preparer = new_uuid()
        order.assign_preparation(assigned_to_user_id=preparer, station_id="station-1")
        assert order.preparation_status == PreparationStatus.ASSIGNED
        assert order.assigned_to_user_id == preparer
        assert order.station_id == "station-1"

    def test_double_assign_raises(self):
        order = _reserved_order_with_line()
        order.assign_preparation(assigned_to_user_id=new_uuid())
        with pytest.raises(OrderPreparationNotAllowedError):
            order.assign_preparation(assigned_to_user_id=new_uuid())


class TestStartPreparation:
    def test_start_sets_started_at_and_fulfillment(self):
        order = _reserved_order_with_line()
        order.assign_preparation(assigned_to_user_id=new_uuid())
        order.start_preparation()
        assert order.preparation_status == PreparationStatus.IN_PROGRESS
        assert order.preparation_started_at is not None
        assert order.fulfillment_status == FulfillmentStatus.PREPARING

    def test_cannot_start_without_assignment(self):
        order = _reserved_order_with_line()
        with pytest.raises(OrderPreparationNotAllowedError):
            order.start_preparation()


class TestRecordPreparedAmount:
    def test_records_quantity_and_marks_prepared(self):
        order = _reserved_order_with_line()
        line = order.lines[0]
        line.record_prepared_amount(quantity=OrderQuantity(Decimal("2")))
        assert line.status == OrderLineStatus.PREPARED
        assert line.prepared_quantity.value == Decimal("2")

    def test_requires_quantity_or_weight(self):
        order = _reserved_order_with_line()
        with pytest.raises(InvalidOrderQuantityError):
            order.lines[0].record_prepared_amount()


class TestCompletePreparation:
    def test_cannot_complete_with_unfinished_lines(self):
        order = _reserved_order_with_line()
        order.assign_preparation(assigned_to_user_id=new_uuid())
        order.start_preparation()
        with pytest.raises(OrderPreparationNotAllowedError):
            order.complete_preparation()

    def test_completes_when_all_lines_prepared(self):
        order = _reserved_order_with_line()
        order.assign_preparation(assigned_to_user_id=new_uuid())
        order.start_preparation()
        order.lines[0].record_prepared_amount(quantity=OrderQuantity(Decimal("2")))
        order.complete_preparation()
        assert order.preparation_status == PreparationStatus.READY
        assert order.fulfillment_status == FulfillmentStatus.READY
        assert order.preparation_completed_at is not None


class TestCancelPreparation:
    def test_cancel_from_pending(self):
        order = _reserved_order_with_line()
        order.cancel_preparation()
        assert order.preparation_status == PreparationStatus.CANCELLED

    def test_cannot_cancel_ready_preparation(self):
        order = _reserved_order_with_line()
        order.assign_preparation(assigned_to_user_id=new_uuid())
        order.start_preparation()
        order.lines[0].record_prepared_amount(quantity=OrderQuantity(Decimal("2")))
        order.complete_preparation()
        with pytest.raises(OrderPreparationNotAllowedError):
            order.cancel_preparation()
