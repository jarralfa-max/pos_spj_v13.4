"""ORD-22 — Sales/Finance integration domain layer: `OrderPaymentPolicy`
(§15 payment-status transitions) and `CustomerOrder.link_sale()`/
`apply_payment_status()`."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.orders_delivery.entities import CustomerOrder, CustomerOrderLine
from backend.domain.orders_delivery.enums import FulfillmentType, OrderChannel, OrderType, PaymentStatus
from backend.domain.orders_delivery.exceptions import (
    InvalidPaymentStatusError,
    OrderAlreadyLinkedToSaleError,
)
from backend.domain.orders_delivery.policies.order_payment_policy import OrderPaymentPolicy
from backend.domain.orders_delivery.value_objects.order_quantity import OrderQuantity
from backend.shared.ids import new_uuid


def _order_with_line() -> CustomerOrder:
    order = CustomerOrder.create(
        branch_id=new_uuid(), channel=OrderChannel.POS, order_type=OrderType.STANDARD,
        fulfillment_type=FulfillmentType.COUNTER)
    line = CustomerOrderLine.create(
        order_id=order.id, product_id=new_uuid(), unit_price=Decimal("50.00"),
        requested_quantity=OrderQuantity(Decimal("2")))
    order.add_line(line)
    return order


class TestOrderPaymentPolicyTransitions:
    def test_unpaid_to_paid_direct(self):
        OrderPaymentPolicy.ensure_transition(current=PaymentStatus.UNPAID, target=PaymentStatus.PAID)

    def test_same_status_is_idempotent_noop(self):
        OrderPaymentPolicy.ensure_transition(
            current=PaymentStatus.PARTIALLY_PAID, target=PaymentStatus.PARTIALLY_PAID)

    def test_refunded_is_final(self):
        with pytest.raises(InvalidPaymentStatusError):
            OrderPaymentPolicy.ensure_transition(
                current=PaymentStatus.REFUNDED, target=PaymentStatus.PAID)

    def test_invalid_transition_rejected(self):
        with pytest.raises(InvalidPaymentStatusError):
            OrderPaymentPolicy.ensure_transition(
                current=PaymentStatus.UNPAID, target=PaymentStatus.REFUNDED)

    def test_paid_to_refunded_allowed(self):
        OrderPaymentPolicy.ensure_transition(current=PaymentStatus.PAID, target=PaymentStatus.REFUNDED)


class TestResolveFromAmounts:
    def test_zero_paid_is_unpaid(self):
        assert OrderPaymentPolicy.resolve_from_amounts(
            total_paid=Decimal("0"), order_total=Decimal("100")) == PaymentStatus.UNPAID

    def test_partial_paid(self):
        assert OrderPaymentPolicy.resolve_from_amounts(
            total_paid=Decimal("40"), order_total=Decimal("100")) == PaymentStatus.PARTIALLY_PAID

    def test_full_paid(self):
        assert OrderPaymentPolicy.resolve_from_amounts(
            total_paid=Decimal("100"), order_total=Decimal("100")) == PaymentStatus.PAID

    def test_overpaid_is_still_paid(self):
        assert OrderPaymentPolicy.resolve_from_amounts(
            total_paid=Decimal("120"), order_total=Decimal("100")) == PaymentStatus.PAID


class TestLinkSale:
    def test_links_sale_id(self):
        order = _order_with_line()
        sale_id = new_uuid()
        order.link_sale(sale_id)
        assert order.sale_id == sale_id

    def test_relinking_same_sale_is_noop(self):
        order = _order_with_line()
        sale_id = new_uuid()
        order.link_sale(sale_id)
        order.link_sale(sale_id)
        assert order.sale_id == sale_id

    def test_relinking_different_sale_raises(self):
        order = _order_with_line()
        order.link_sale(new_uuid())
        with pytest.raises(OrderAlreadyLinkedToSaleError):
            order.link_sale(new_uuid())


class TestApplyPaymentStatus:
    def test_applies_valid_transition(self):
        order = _order_with_line()
        order.apply_payment_status(PaymentStatus.PAID)
        assert order.payment_status == PaymentStatus.PAID

    def test_repeated_same_status_is_noop(self):
        order = _order_with_line()
        order.apply_payment_status(PaymentStatus.PARTIALLY_PAID)
        order.apply_payment_status(PaymentStatus.PARTIALLY_PAID)
        assert order.payment_status == PaymentStatus.PARTIALLY_PAID

    def test_invalid_transition_raises(self):
        order = _order_with_line()
        order.apply_payment_status(PaymentStatus.PAID)
        order.apply_payment_status(PaymentStatus.REFUNDED)
        with pytest.raises(InvalidPaymentStatusError):
            order.apply_payment_status(PaymentStatus.PAID)
