"""ORD-12 — substitutions (§28-29): SubstitutionPolicy, CustomerOrderLine
propose/accept/reject substitution, and CustomerOrder orchestration reusing
the shared customer-approval machinery."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.orders_delivery.entities import CustomerOrder, CustomerOrderLine
from backend.domain.orders_delivery.enums import (
    CustomerApprovalStatus,
    FulfillmentType,
    OrderChannel,
    OrderLineStatus,
    OrderType,
    SubstitutionType,
)
from backend.domain.orders_delivery.exceptions import (
    InvalidOrderStateError,
    SubstitutionNotAllowedError,
)
from backend.domain.orders_delivery.value_objects.order_quantity import OrderQuantity
from backend.shared.ids import new_uuid


def _order_with_line(*, substitution_allowed: bool = True) -> tuple[CustomerOrder, CustomerOrderLine]:
    order = CustomerOrder.create(
        branch_id=new_uuid(), channel=OrderChannel.POS, order_type=OrderType.STANDARD,
        fulfillment_type=FulfillmentType.COUNTER)
    line = CustomerOrderLine.create(
        order_id=order.id, product_id=new_uuid(), unit_price=Decimal("50.00"),
        requested_quantity=OrderQuantity(Decimal("3")), substitution_allowed=substitution_allowed)
    order.add_line(line)
    return order, line


class TestProposeSubstitution:
    def test_propose_requires_substitution_allowed(self):
        order, line = _order_with_line(substitution_allowed=False)
        with pytest.raises(SubstitutionNotAllowedError):
            order.propose_substitution(
                line_id=line.id, substitute_product_id=new_uuid(),
                substitution_type=SubstitutionType.EQUIVALENT_PRODUCT,
                new_unit_price=Decimal("55.00"), reason="Sin existencia")

    def test_propose_sets_pending_approval(self):
        order, line = _order_with_line()
        order.propose_substitution(
            line_id=line.id, substitute_product_id=new_uuid(),
            substitution_type=SubstitutionType.EQUIVALENT_PRODUCT,
            new_unit_price=Decimal("55.00"), reason="Sin existencia")
        assert line.status == OrderLineStatus.PENDING_CUSTOMER_APPROVAL
        assert order.customer_approval_status == CustomerApprovalStatus.PENDING
        assert line.pre_substitution_unit_price == Decimal("50.00")

    def test_no_substitution_type_is_rejected(self):
        order, line = _order_with_line()
        with pytest.raises(SubstitutionNotAllowedError):
            order.propose_substitution(
                line_id=line.id, substitute_product_id=new_uuid(),
                substitution_type=SubstitutionType.NO_SUBSTITUTION,
                new_unit_price=Decimal("55.00"), reason="motivo")


class TestAcceptRejectSubstitution:
    def test_accept_applies_new_price(self):
        order, line = _order_with_line()
        order.propose_substitution(
            line_id=line.id, substitute_product_id=new_uuid(),
            substitution_type=SubstitutionType.EQUIVALENT_PRODUCT,
            new_unit_price=Decimal("60.00"), reason="Sin existencia")
        order.accept_substitution(line.id)
        assert line.status == OrderLineStatus.SUBSTITUTED
        assert line.unit_price_snapshot == Decimal("60.00")
        assert order.totals.subtotal == Decimal("180.00")

    def test_reject_keeps_original_price(self):
        order, line = _order_with_line()
        order.propose_substitution(
            line_id=line.id, substitute_product_id=new_uuid(),
            substitution_type=SubstitutionType.EQUIVALENT_PRODUCT,
            new_unit_price=Decimal("60.00"), reason="Sin existencia")
        order.reject_substitution(line.id)
        assert line.status == OrderLineStatus.REJECTED
        assert line.unit_price_snapshot == Decimal("50.00")

    def test_accept_twice_is_idempotent(self):
        order, line = _order_with_line()
        order.propose_substitution(
            line_id=line.id, substitute_product_id=new_uuid(),
            substitution_type=SubstitutionType.EQUIVALENT_PRODUCT,
            new_unit_price=Decimal("60.00"), reason="motivo")
        order.accept_substitution(line.id)
        order.accept_substitution(line.id)  # must not raise
        assert line.unit_price_snapshot == Decimal("60.00")

    def test_accept_without_proposal_raises(self):
        order, line = _order_with_line()
        with pytest.raises(InvalidOrderStateError):
            order.accept_substitution(line.id)
