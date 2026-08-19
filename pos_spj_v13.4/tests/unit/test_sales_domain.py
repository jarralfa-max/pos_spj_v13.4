"""SALES-3 — Sale/SaleLine aggregate, SaleTotals, policies, events.
Mirrors tests/unit/cash_register/test_cash_register_domain.py's structure
(one test module per bounded-context domain phase, class-per-concept)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.sales.enums import PaymentMethod, SaleStatus
from backend.domain.sales.events import ALL_SALE_EVENTS, SaleEvents, sale_event_payload
from backend.domain.sales.exceptions import (
    DiscountNotAllowedError,
    InvalidMoneyValueError,
    InvalidQuantityError,
    SaleCancellationNotAllowedError,
    SaleEmptyCartError,
    SaleInvalidStateError,
    SaleLineNotFoundError,
    SaleResumeNotAllowedError,
    SaleSuspensionLimitError,
)
from backend.domain.sales.policies.customer_assignment_policy import CustomerAssignmentPolicy
from backend.domain.sales.policies.discount_policy import SaleDiscountPolicy
from backend.domain.sales.policies.lifecycle_policies import (
    CheckoutPolicy,
    SaleCancellationPolicy,
    SaleLifecyclePolicy,
)
from backend.domain.sales.policies.line_policies import QuantityPolicy, SaleLinePolicy
from backend.domain.sales.policies.sale_creation_policy import SaleCreationPolicy
from backend.domain.sales.policies.suspension_policies import (
    SaleResumptionPolicy,
    SaleSuspensionPolicy,
)
from backend.domain.sales.entities import Sale, SaleLine
from backend.domain.sales.services.sale_totals_service import SaleTotalsService
from backend.domain.sales.value_objects.money import money
from backend.domain.sales.value_objects.quantity import Quantity
from backend.domain.sales.value_objects.sale_totals import SaleTotals
from backend.shared.ids import new_uuid


def _uid() -> str:
    return new_uuid()


class TestQuantity:
    def test_valid_quantity(self):
        q = Quantity(Decimal("2"), "PZA")
        assert q.value == Decimal("2")

    def test_rejects_float(self):
        with pytest.raises(InvalidQuantityError):
            Quantity(1.5, "PZA")

    def test_rejects_zero(self):
        with pytest.raises(InvalidQuantityError):
            Quantity(Decimal("0"), "PZA")

    def test_rejects_negative(self):
        with pytest.raises(InvalidQuantityError):
            Quantity(Decimal("-1"), "PZA")

    def test_add_same_unit(self):
        total = Quantity(Decimal("2"), "PZA").add(Quantity(Decimal("3"), "PZA"))
        assert total.value == Decimal("5")

    def test_add_rejects_mismatched_unit(self):
        with pytest.raises(InvalidQuantityError):
            Quantity(Decimal("2"), "PZA").add(Quantity(Decimal("1"), "KG"))


class TestMoney:
    def test_rejects_float(self):
        with pytest.raises(InvalidMoneyValueError):
            money(1.5)

    def test_rejects_negative_by_default(self):
        with pytest.raises(InvalidMoneyValueError):
            money(Decimal("-1"))

    def test_allows_negative_when_flagged(self):
        assert money(Decimal("-1"), allow_negative=True) == Decimal("-1")

    def test_rejects_zero_when_disallowed(self):
        with pytest.raises(InvalidMoneyValueError):
            money(Decimal("0"), allow_zero=False)


class TestSaleTotals:
    def test_valid_totals(self):
        totals = SaleTotals(gross_subtotal=Decimal("100"), tax_total=Decimal("16"),
                             total=Decimal("116"))
        assert totals.total == Decimal("116")

    def test_rejects_inconsistent_total(self):
        with pytest.raises(InvalidMoneyValueError):
            SaleTotals(gross_subtotal=Decimal("100"), total=Decimal("999"))

    def test_zero(self):
        assert SaleTotals.zero().total == Decimal("0")


class TestSaleTotalsService:
    def _line(self, qty: str, price: str, discount: str = "0", tax: str = "0") -> SaleLine:
        return SaleLine.create(
            sale_id=_uid(), product_id=_uid(),
            quantity=Quantity(Decimal(qty)), unit_price=Decimal(price),
        )

    def test_calculates_from_lines(self):
        line1 = self._line("2", "50.00")
        line1.apply_tax(Decimal("16.00"))
        line2 = self._line("1", "30.00")
        totals = SaleTotalsService.calculate([line1, line2])
        assert totals.gross_subtotal == Decimal("130.00")
        assert totals.tax_total == Decimal("16.00")
        assert totals.total == Decimal("146.00")

    def test_includes_sale_level_discount(self):
        line = self._line("1", "100.00")
        totals = SaleTotalsService.calculate([line], sale_level_discount=Decimal("10.00"))
        assert totals.discount_total == Decimal("10.00")
        assert totals.total == Decimal("90.00")

    def test_empty_cart_is_zero(self):
        totals = SaleTotalsService.calculate([])
        assert totals.total == Decimal("0")


class TestSaleLifecyclePolicy:
    def test_valid_transition(self):
        SaleLifecyclePolicy.ensure_transition(current=SaleStatus.DRAFT, target=SaleStatus.ACTIVE)

    def test_invalid_transition_rejected(self):
        with pytest.raises(SaleInvalidStateError):
            SaleLifecyclePolicy.ensure_transition(
                current=SaleStatus.DRAFT, target=SaleStatus.COMPLETED)

    def test_final_status_cannot_transition(self):
        with pytest.raises(SaleInvalidStateError):
            SaleLifecyclePolicy.ensure_transition(
                current=SaleStatus.CANCELLED, target=SaleStatus.ACTIVE)

    def test_is_line_mutable(self):
        assert SaleLifecyclePolicy.is_line_mutable(SaleStatus.ACTIVE) is True
        assert SaleLifecyclePolicy.is_line_mutable(SaleStatus.COMPLETED) is False


class TestCheckoutPolicy:
    def test_requires_at_least_one_line(self):
        with pytest.raises(SaleEmptyCartError):
            CheckoutPolicy.ensure_can_checkout(
                status=SaleStatus.ACTIVE, line_count=0, total=Decimal("0"))

    def test_requires_positive_total(self):
        with pytest.raises(SaleEmptyCartError):
            CheckoutPolicy.ensure_can_checkout(
                status=SaleStatus.ACTIVE, line_count=1, total=Decimal("0"))

    def test_allows_valid_checkout(self):
        CheckoutPolicy.ensure_can_checkout(
            status=SaleStatus.ACTIVE, line_count=1, total=Decimal("50"))


class TestSaleCancellationPolicy:
    def test_requires_reason(self):
        with pytest.raises(SaleCancellationNotAllowedError):
            SaleCancellationPolicy.ensure_can_cancel(status=SaleStatus.ACTIVE, reason="  ")

    def test_completed_sale_cannot_be_cancelled(self):
        """§42: a paid sale must be reversed, not cancelled."""
        with pytest.raises(SaleCancellationNotAllowedError):
            SaleCancellationPolicy.ensure_can_cancel(
                status=SaleStatus.COMPLETED, reason="cliente cambió de opinión")

    def test_active_sale_can_be_cancelled(self):
        SaleCancellationPolicy.ensure_can_cancel(status=SaleStatus.ACTIVE, reason="motivo")


class TestSaleSuspensionPolicy:
    def test_rejects_empty_cart(self):
        with pytest.raises(SaleEmptyCartError):
            SaleSuspensionPolicy.ensure_can_suspend(
                status=SaleStatus.ACTIVE, line_count=0,
                current_suspended_count=0, max_suspended_sales=5)

    def test_enforces_limit(self):
        with pytest.raises(SaleSuspensionLimitError):
            SaleSuspensionPolicy.ensure_can_suspend(
                status=SaleStatus.ACTIVE, line_count=1,
                current_suspended_count=5, max_suspended_sales=5)

    def test_allows_within_limit(self):
        SaleSuspensionPolicy.ensure_can_suspend(
            status=SaleStatus.ACTIVE, line_count=1,
            current_suspended_count=2, max_suspended_sales=5)

    def test_unlimited_when_max_is_zero(self):
        SaleSuspensionPolicy.ensure_can_suspend(
            status=SaleStatus.ACTIVE, line_count=1,
            current_suspended_count=999, max_suspended_sales=0)


class TestSaleResumptionPolicy:
    def test_same_user_same_workstation_always_allowed(self):
        SaleResumptionPolicy.ensure_can_resume(
            status=SaleStatus.SUSPENDED,
            suspended_by_user_id="u1", resuming_user_id="u1",
            suspended_at_workstation_id="w1", resuming_workstation_id="w1",
            allow_cross_user_resume=False, allow_cross_workstation_resume=False,
        )

    def test_cross_user_denied_when_not_allowed(self):
        with pytest.raises(SaleResumeNotAllowedError):
            SaleResumptionPolicy.ensure_can_resume(
                status=SaleStatus.SUSPENDED,
                suspended_by_user_id="u1", resuming_user_id="u2",
                suspended_at_workstation_id="w1", resuming_workstation_id="w1",
                allow_cross_user_resume=False,
            )

    def test_cross_workstation_denied_when_not_allowed(self):
        with pytest.raises(SaleResumeNotAllowedError):
            SaleResumptionPolicy.ensure_can_resume(
                status=SaleStatus.SUSPENDED,
                suspended_by_user_id="u1", resuming_user_id="u1",
                suspended_at_workstation_id="w1", resuming_workstation_id="w2",
                allow_cross_workstation_resume=False,
            )

    def test_only_suspended_sale_can_resume(self):
        with pytest.raises(SaleResumeNotAllowedError):
            SaleResumptionPolicy.ensure_can_resume(
                status=SaleStatus.COMPLETED,
                suspended_by_user_id="u1", resuming_user_id="u1",
                suspended_at_workstation_id="w1", resuming_workstation_id="w1",
            )


class TestQuantityAndLinePolicy:
    def test_quantity_policy_rejects_non_positive(self):
        with pytest.raises(InvalidQuantityError):
            QuantityPolicy.ensure_valid(Quantity(Decimal("1")), max_sellable=Decimal("0"))

    def test_quantity_policy_enforces_max_sellable(self):
        with pytest.raises(InvalidQuantityError):
            QuantityPolicy.ensure_valid(Quantity(Decimal("10")), max_sellable=Decimal("5"))

    def test_line_policy_blocks_mutation_after_checkout(self):
        with pytest.raises(SaleInvalidStateError):
            SaleLinePolicy.ensure_can_modify_line(SaleStatus.CHECKOUT_PENDING)

    def test_line_policy_allows_mutation_while_active(self):
        SaleLinePolicy.ensure_can_modify_line(SaleStatus.ACTIVE)


class TestSaleDiscountPolicy:
    def test_small_discount_does_not_require_authorization(self):
        SaleDiscountPolicy.ensure_valid_discount(
            discount_amount=Decimal("5"), base_amount=Decimal("100"), authorized=False)

    def test_large_discount_requires_authorization(self):
        with pytest.raises(DiscountNotAllowedError):
            SaleDiscountPolicy.ensure_valid_discount(
                discount_amount=Decimal("50"), base_amount=Decimal("100"), authorized=False)

    def test_large_discount_allowed_when_authorized(self):
        SaleDiscountPolicy.ensure_valid_discount(
            discount_amount=Decimal("50"), base_amount=Decimal("100"), authorized=True)

    def test_discount_cannot_exceed_base(self):
        with pytest.raises(DiscountNotAllowedError):
            SaleDiscountPolicy.ensure_valid_discount(
                discount_amount=Decimal("150"), base_amount=Decimal("100"), authorized=True)


class TestCustomerAssignmentPolicy:
    def test_allowed_while_active(self):
        CustomerAssignmentPolicy.ensure_can_assign(SaleStatus.ACTIVE)

    def test_denied_after_completion(self):
        with pytest.raises(SaleInvalidStateError):
            CustomerAssignmentPolicy.ensure_can_assign(SaleStatus.COMPLETED)


class TestSaleCreationPolicy:
    def test_blocks_without_open_shift_when_required(self):
        with pytest.raises(SaleInvalidStateError):
            SaleCreationPolicy.ensure_can_start(
                requires_open_cash_session=True, has_open_cash_session=False)

    def test_allows_with_open_shift(self):
        SaleCreationPolicy.ensure_can_start(
            requires_open_cash_session=True, has_open_cash_session=True)

    def test_allows_when_not_required(self):
        SaleCreationPolicy.ensure_can_start(
            requires_open_cash_session=False, has_open_cash_session=False)


class TestSaleLineEntity:
    def test_create_and_line_total(self):
        line = SaleLine.create(
            sale_id=_uid(), product_id=_uid(),
            quantity=Quantity(Decimal("3")), unit_price=Decimal("10.00"),
        )
        assert line.line_total == Decimal("30.00")

    def test_line_total_reflects_discount_and_tax(self):
        line = SaleLine.create(
            sale_id=_uid(), product_id=_uid(),
            quantity=Quantity(Decimal("1")), unit_price=Decimal("100.00"),
        )
        line.apply_discount(Decimal("10.00"), authorized=True)
        line.apply_tax(Decimal("16.00"))
        assert line.line_total == Decimal("106.00")

    def test_product_snapshot_preserved(self):
        line = SaleLine.create(
            sale_id=_uid(), product_id=_uid(),
            quantity=Quantity(Decimal("1")), unit_price=Decimal("10.00"),
            product_snapshot={"nombre": "Bistec", "sku": "BST-1"},
        )
        assert line.product_snapshot["nombre"] == "Bistec"


class TestSaleAggregate:
    def _new_sale(self) -> Sale:
        return Sale.start(branch_id=_uid(), cashier_user_id=_uid(), operation_id=_uid())

    def test_start_is_draft_with_zero_totals(self):
        sale = self._new_sale()
        assert sale.status is SaleStatus.DRAFT
        assert sale.totals.total == Decimal("0")
        assert sale.version == 1

    def test_first_line_activates_the_sale(self):
        sale = self._new_sale()
        sale.add_line(product_id=_uid(), quantity=Quantity(Decimal("2")), unit_price=Decimal("25.00"))
        assert sale.status is SaleStatus.ACTIVE
        assert sale.totals.total == Decimal("50.00")
        assert sale.version == 2

    def test_add_line_enforces_max_sellable(self):
        sale = self._new_sale()
        with pytest.raises(InvalidQuantityError):
            sale.add_line(product_id=_uid(), quantity=Quantity(Decimal("10")),
                          unit_price=Decimal("10.00"), max_sellable=Decimal("5"))
        assert sale.status is SaleStatus.DRAFT  # rejected line never committed

    def test_update_line_quantity_recalculates_totals(self):
        sale = self._new_sale()
        line = sale.add_line(product_id=_uid(), quantity=Quantity(Decimal("1")), unit_price=Decimal("10.00"))
        sale.update_line_quantity(line.id, Quantity(Decimal("4")))
        assert sale.totals.total == Decimal("40.00")

    def test_remove_line_recalculates_totals(self):
        sale = self._new_sale()
        line1 = sale.add_line(product_id=_uid(), quantity=Quantity(Decimal("1")), unit_price=Decimal("10.00"))
        sale.add_line(product_id=_uid(), quantity=Quantity(Decimal("1")), unit_price=Decimal("20.00"))
        sale.remove_line(line1.id)
        assert sale.totals.total == Decimal("20.00")
        assert len(sale.lines) == 1

    def test_unknown_line_raises(self):
        sale = self._new_sale()
        sale.add_line(product_id=_uid(), quantity=Quantity(Decimal("1")), unit_price=Decimal("10.00"))
        with pytest.raises(SaleLineNotFoundError):
            sale.remove_line(_uid())

    def test_apply_sale_discount_requires_authorization_above_threshold(self):
        sale = self._new_sale()
        sale.add_line(product_id=_uid(), quantity=Quantity(Decimal("1")), unit_price=Decimal("100.00"))
        with pytest.raises(DiscountNotAllowedError):
            sale.apply_sale_discount(Decimal("50.00"), authorized=False)
        sale.apply_sale_discount(Decimal("50.00"), authorized=True)
        assert sale.totals.total == Decimal("50.00")

    def test_assign_and_clear_customer(self):
        sale = self._new_sale()
        customer_id = _uid()
        sale.assign_customer(customer_id)
        assert sale.customer_id == customer_id
        sale.assign_customer(None)
        assert sale.customer_id is None

    def test_full_checkout_lifecycle(self):
        sale = self._new_sale()
        sale.add_line(product_id=_uid(), quantity=Quantity(Decimal("1")), unit_price=Decimal("100.00"))
        sale.begin_checkout()
        assert sale.status is SaleStatus.CHECKOUT_PENDING
        sale.mark_payment_pending()
        assert sale.status is SaleStatus.PAYMENT_PENDING
        sale.record_payment(method=PaymentMethod.CASH, amount=Decimal("100.00"),
                            captured_by_user_id=_uid())
        sale.complete()
        assert sale.status is SaleStatus.COMPLETED
        assert sale.completed_at is not None

    def test_checkout_pending_can_complete_directly_for_cash(self):
        sale = self._new_sale()
        sale.add_line(product_id=_uid(), quantity=Quantity(Decimal("1")), unit_price=Decimal("100.00"))
        sale.begin_checkout()
        sale.record_payment(method=PaymentMethod.CASH, amount=Decimal("100.00"),
                            captured_by_user_id=_uid())
        sale.complete()
        assert sale.status is SaleStatus.COMPLETED

    def test_cannot_add_line_after_checkout_started(self):
        sale = self._new_sale()
        sale.add_line(product_id=_uid(), quantity=Quantity(Decimal("1")), unit_price=Decimal("100.00"))
        sale.begin_checkout()
        with pytest.raises(SaleInvalidStateError):
            sale.add_line(product_id=_uid(), quantity=Quantity(Decimal("1")), unit_price=Decimal("5.00"))

    def test_suspend_and_resume(self):
        sale = self._new_sale()
        sale.add_line(product_id=_uid(), quantity=Quantity(Decimal("1")), unit_price=Decimal("10.00"))
        cashier = sale.cashier_user_id
        sale.suspend(current_suspended_count=0, max_suspended_sales=5, suspended_by_user_id=cashier)
        assert sale.status is SaleStatus.SUSPENDED
        assert sale.suspended_at is not None
        sale.resume(resuming_user_id=cashier)
        assert sale.status is SaleStatus.ACTIVE
        assert sale.suspended_at is None

    def test_draft_sale_cannot_be_suspended(self):
        """A DRAFT sale (no lines yet) can't even reach SUSPENDED — the
        aggregate's own lifecycle transition table blocks it before the
        empty-cart check in SaleSuspensionPolicy would matter; that check is
        exercised directly in TestSaleSuspensionPolicy for repository-row
        validation paths that don't go through this aggregate's API."""
        sale = self._new_sale()
        with pytest.raises(SaleInvalidStateError):
            sale.suspend(current_suspended_count=0, max_suspended_sales=5,
                         suspended_by_user_id=sale.cashier_user_id)

    def test_cancel_active_sale(self):
        sale = self._new_sale()
        sale.add_line(product_id=_uid(), quantity=Quantity(Decimal("1")), unit_price=Decimal("10.00"))
        sale.cancel("cliente se arrepintió")
        assert sale.status is SaleStatus.CANCELLED
        assert sale.cancelled_at is not None

    def test_completed_sale_cannot_be_cancelled(self):
        sale = self._new_sale()
        sale.add_line(product_id=_uid(), quantity=Quantity(Decimal("1")), unit_price=Decimal("10.00"))
        sale.begin_checkout()
        sale.record_payment(method=PaymentMethod.CASH, amount=Decimal("10.00"),
                            captured_by_user_id=_uid())
        sale.complete()
        with pytest.raises(SaleCancellationNotAllowedError):
            sale.cancel("motivo")

    def test_version_increments_on_every_mutation(self):
        sale = self._new_sale()
        assert sale.version == 1
        sale.add_line(product_id=_uid(), quantity=Quantity(Decimal("1")), unit_price=Decimal("10.00"))
        assert sale.version == 2
        sale.assign_customer(_uid())
        assert sale.version == 3


class TestSaleEvents:
    def test_canonical_event_names_present(self):
        for name in (
            "SALE_STARTED", "SALE_LINE_ADDED", "SALE_SUSPENDED", "SALE_RESUMED",
            "SALE_COMPLETED", "SALE_CANCELLED", "SALE_RETURNED", "SALE_REVERSED",
        ):
            assert name in ALL_SALE_EVENTS

    def test_payload_rejects_unknown_event(self):
        with pytest.raises(ValueError):
            sale_event_payload(
                "NOT_A_REAL_EVENT", operation_id=_uid(), entity_id=_uid(),
                branch_id=_uid(), user_id=_uid())

    def test_payload_shape(self):
        payload = sale_event_payload(
            SaleEvents.COMPLETED, operation_id=_uid(), entity_id=_uid(),
            branch_id=_uid(), user_id=_uid(), total="100.00")
        assert payload["event_name"] == SaleEvents.COMPLETED
        assert payload["source_module"] == "sales"
        assert payload["payload"]["total"] == "100.00"
        assert payload["event_id"] not in (payload["operation_id"], payload["entity_id"])
