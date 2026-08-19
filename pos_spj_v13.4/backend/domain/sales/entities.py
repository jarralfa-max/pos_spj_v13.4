"""SALES-3 aggregate: Sale (aggregate root) and SaleLine (owned entity).
Mirrors backend/domain/cash_register/entities.py's shape: `slots=True`
dataclasses, `new_uuid()`/`validate_uuidv7()` for identity, classmethod
factories, mutation methods that delegate to policies before touching state.

Sale owns its lines and its own SaleTotals — no caller ever assembles totals
by hand (see `backend/domain/sales/services/sale_totals_service.py`'s own
docstring for why: "Una sola evaluación de precios", master prompt §73).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Mapping

from backend.shared.ids import new_uuid, validate_uuidv7
from backend.domain.sales.enums import InvoiceStatus, PaymentMethod, SaleStatus
from backend.domain.sales.exceptions import (
    InvoiceRequestNotFoundError,
    SaleLineNotFoundError,
    SaleReversalNotAllowedError,
)
from backend.domain.sales.policies.customer_assignment_policy import CustomerAssignmentPolicy
from backend.domain.sales.policies.discount_policy import SaleDiscountPolicy
from backend.domain.sales.policies.invoice_policy import SaleInvoicePolicy
from backend.domain.sales.policies.lifecycle_policies import (
    CheckoutPolicy,
    SaleCancellationPolicy,
    SaleLifecyclePolicy,
)
from backend.domain.sales.policies.line_policies import QuantityPolicy, SaleLinePolicy
from backend.domain.sales.policies.loyalty_policy import LoyaltyPolicy
from backend.domain.sales.policies.payment_policy import SalePaymentPolicy
from backend.domain.sales.policies.return_policy import SaleReturnPolicy
from backend.domain.sales.policies.suspension_policies import (
    SaleResumptionPolicy,
    SaleSuspensionPolicy,
)
from backend.domain.sales.services.sale_totals_service import SaleTotalsService
from backend.domain.sales.value_objects.money import money
from backend.domain.sales.value_objects.quantity import Quantity
from backend.domain.sales.value_objects.sale_payment import SalePayment
from backend.domain.sales.value_objects.sale_return import SaleReturn
from backend.domain.sales.value_objects.sale_totals import SaleTotals


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ids(*values: str) -> None:
    for value in values:
        validate_uuidv7(value)


@dataclass(slots=True)
class SaleLine:
    id: str
    sale_id: str
    product_id: str
    quantity: Quantity
    unit_price: Decimal
    product_snapshot: Mapping[str, Any] = field(default_factory=dict)
    pricing_snapshot_id: str | None = None
    discount_total: Decimal = Decimal("0")
    tax_total: Decimal = Decimal("0")
    weight_source: str | None = None
    lot_reference: str | None = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    @classmethod
    def create(
        cls, *, sale_id: str, product_id: str, quantity: Quantity, unit_price: Decimal,
        product_snapshot: Mapping[str, Any] | None = None,
        pricing_snapshot_id: str | None = None,
        weight_source: str | None = None, lot_reference: str | None = None,
    ) -> "SaleLine":
        _ids(sale_id, product_id)
        if pricing_snapshot_id is not None:
            _ids(pricing_snapshot_id)
        return cls(
            id=new_uuid(), sale_id=sale_id, product_id=product_id, quantity=quantity,
            unit_price=money(unit_price, allow_zero=True),
            product_snapshot=dict(product_snapshot or {}),
            pricing_snapshot_id=pricing_snapshot_id,
            weight_source=weight_source, lot_reference=lot_reference,
        )

    @property
    def line_total(self) -> Decimal:
        """Derived, never stored — so it can never drift from
        quantity/unit_price/discount_total/tax_total (§11 lists line_total as
        its own field, but storing it redundantly risks exactly the kind of
        drift this domain layer exists to prevent)."""
        return (self.quantity.value * self.unit_price) - self.discount_total + self.tax_total

    def update_quantity(self, quantity: Quantity, *, max_sellable: Decimal | None = None) -> None:
        QuantityPolicy.ensure_valid(quantity, max_sellable=max_sellable)
        self.quantity = quantity
        self.updated_at = _now()

    def apply_discount(self, discount_total: Decimal, *, authorized: bool = False) -> None:
        base = self.quantity.value * self.unit_price
        SaleDiscountPolicy.ensure_valid_discount(
            discount_amount=discount_total, base_amount=base, authorized=authorized)
        self.discount_total = money(discount_total)
        self.updated_at = _now()

    def apply_tax(self, tax_total: Decimal) -> None:
        self.tax_total = money(tax_total)
        self.updated_at = _now()


@dataclass(slots=True)
class SaleInvoiceRequest:
    """POS-18/§15/§46: a CFDI invoice request against a COMPLETED Sale.
    Mutable (unlike `SalePayment`/`SaleReturn`) because it genuinely has a
    lifecycle — REQUESTED -> ISSUED/ERROR — resolved later by whatever
    real Fiscal/PAC integration eventually exists (none does today,
    confirmed by research); this repository does not fabricate one."""

    id: str
    sale_id: str
    tax_identifier: str
    legal_name: str
    cfdi_use: str
    requested_by_user_id: str
    status: InvoiceStatus = InvoiceStatus.REQUESTED
    uuid_fiscal: str | None = None
    error_message: str | None = None
    requested_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    @classmethod
    def create(cls, *, sale_id: str, tax_identifier: str, legal_name: str, cfdi_use: str,
               requested_by_user_id: str) -> "SaleInvoiceRequest":
        _ids(sale_id, requested_by_user_id)
        return cls(
            id=new_uuid(), sale_id=sale_id, tax_identifier=tax_identifier.strip(),
            legal_name=(legal_name or "").strip() or "PUBLICO EN GENERAL",
            cfdi_use=(cfdi_use or "S01").strip(), requested_by_user_id=requested_by_user_id,
        )

    def mark_issued(self, *, uuid_fiscal: str) -> None:
        SaleInvoicePolicy.ensure_can_resolve(self.status)
        self.status = InvoiceStatus.ISSUED
        self.uuid_fiscal = uuid_fiscal
        self.updated_at = _now()

    def mark_error(self, *, error_message: str) -> None:
        SaleInvoicePolicy.ensure_can_resolve(self.status)
        self.status = InvoiceStatus.ERROR
        self.error_message = error_message
        self.updated_at = _now()


@dataclass(slots=True)
class Sale:
    id: str
    branch_id: str
    cashier_user_id: str
    operation_id: str
    status: SaleStatus = SaleStatus.DRAFT
    sale_number: str | None = None
    workstation_id: str | None = None
    cash_session_id: str | None = None
    customer_id: str | None = None
    channel: str = "POS"
    currency_code: str = "MXN"
    lines: list[SaleLine] = field(default_factory=list)
    totals: SaleTotals = field(default_factory=SaleTotals.zero)
    created_at: str = field(default_factory=_now)
    suspended_at: str | None = None
    completed_at: str | None = None
    cancelled_at: str | None = None
    version: int = 1
    sale_level_discount: Decimal = Decimal("0")
    # POS-14/§38-41: committed loyalty-point redemption amount, flows into
    # `SaleTotals.loyalty_total` via `_recalculate_totals` — distinct from
    # `sale_level_discount` (a commercial discount), never conflated.
    loyalty_redeemed_amount: Decimal = Decimal("0")
    suspended_by_user_id: str | None = None
    suspended_workstation_id: str | None = None
    # Cross-context reference only (§6: Ventas no es dueño de inventario) —
    # the id of the stock hold this sale currently owns in Inventory's own
    # `stock_reservas` table (SALES-9/POS-9), set/cleared by
    # backend/infrastructure/integrations/sales_inventory_client.py. Sale
    # never interprets or validates this value itself, only carries it.
    inventory_reservation_id: str | None = None
    # POS-13/§30-36: recorded payment lines. A sale is "mixed" the moment
    # more than one distinct PaymentMethod appears here — see
    # `is_mixed_payment` — never a status/label set up front.
    payments: list[SalePayment] = field(default_factory=list)
    # POS-16/§42-44: recorded partial-line returns against a COMPLETED sale.
    returns: list[SaleReturn] = field(default_factory=list)
    reversed_at: str | None = None
    # POS-18/§15/§46: CFDI invoice requests against this sale.
    invoice_requests: list[SaleInvoiceRequest] = field(default_factory=list)

    @classmethod
    def start(
        cls, *, branch_id: str, cashier_user_id: str, operation_id: str,
        workstation_id: str | None = None, cash_session_id: str | None = None,
        channel: str = "POS", currency_code: str = "MXN",
    ) -> "Sale":
        _ids(branch_id, cashier_user_id, operation_id)
        if workstation_id is not None:
            _ids(workstation_id)
        if cash_session_id is not None:
            _ids(cash_session_id)
        return cls(
            id=new_uuid(), branch_id=branch_id, cashier_user_id=cashier_user_id,
            operation_id=operation_id, workstation_id=workstation_id,
            cash_session_id=cash_session_id, channel=channel, currency_code=currency_code,
        )

    # ── internals ────────────────────────────────────────────────────────

    def _recalculate_totals(self) -> None:
        self.totals = SaleTotalsService.calculate(
            self.lines, sale_level_discount=self.sale_level_discount,
            loyalty_total=self.loyalty_redeemed_amount)

    def _bump_version(self) -> None:
        self.version += 1

    def _find_line(self, line_id: str) -> SaleLine:
        for line in self.lines:
            if line.id == line_id:
                return line
        raise SaleLineNotFoundError(f"No existe la línea {line_id} en esta venta")

    # ── cart ─────────────────────────────────────────────────────────────

    def add_line(
        self, *, product_id: str, quantity: Quantity, unit_price: Decimal,
        product_snapshot: Mapping[str, Any] | None = None,
        pricing_snapshot_id: str | None = None,
        weight_source: str | None = None, lot_reference: str | None = None,
        max_sellable: Decimal | None = None,
    ) -> SaleLine:
        SaleLinePolicy.ensure_can_add_line(self.status)
        QuantityPolicy.ensure_valid(quantity, max_sellable=max_sellable)
        line = SaleLine.create(
            sale_id=self.id, product_id=product_id, quantity=quantity,
            unit_price=unit_price, product_snapshot=product_snapshot,
            pricing_snapshot_id=pricing_snapshot_id,
            weight_source=weight_source, lot_reference=lot_reference,
        )
        self.lines.append(line)
        if self.status is SaleStatus.DRAFT:
            SaleLifecyclePolicy.ensure_transition(current=self.status, target=SaleStatus.ACTIVE)
            self.status = SaleStatus.ACTIVE
        self._recalculate_totals()
        self._bump_version()
        return line

    def update_line_quantity(self, line_id: str, quantity: Quantity, *,
                              max_sellable: Decimal | None = None) -> None:
        SaleLinePolicy.ensure_can_modify_line(self.status)
        self._find_line(line_id).update_quantity(quantity, max_sellable=max_sellable)
        self._recalculate_totals()
        self._bump_version()

    def remove_line(self, line_id: str) -> None:
        SaleLinePolicy.ensure_can_modify_line(self.status)
        self.lines.remove(self._find_line(line_id))
        self._recalculate_totals()
        self._bump_version()

    def apply_line_discount(self, line_id: str, discount_total: Decimal, *,
                             authorized: bool = False) -> None:
        SaleLinePolicy.ensure_can_modify_line(self.status)
        self._find_line(line_id).apply_discount(discount_total, authorized=authorized)
        self._recalculate_totals()
        self._bump_version()

    def apply_sale_discount(self, discount_total: Decimal, *, authorized: bool = False) -> None:
        SaleLinePolicy.ensure_can_modify_line(self.status)
        SaleDiscountPolicy.ensure_valid_discount(
            discount_amount=discount_total, base_amount=self.totals.gross_subtotal,
            authorized=authorized)
        self.sale_level_discount = money(discount_total)
        self._recalculate_totals()
        self._bump_version()

    def apply_loyalty_redemption(self, amount: Decimal) -> None:
        """POS-14/§38-41. `amount` is the ALREADY-VALIDATED discount a real
        loyalty redemption produced (capped/clamped by
        `SalesLoyaltyClient.redeem()`, itself delegating to `LoyaltyService`
        — this domain method does not re-derive or re-cap the amount, only
        records it and re-totals; Loyalty owns that business rule, not
        Sales, per §6)."""
        LoyaltyPolicy.ensure_can_redeem(self.status)
        self.loyalty_redeemed_amount = money(amount)
        self._recalculate_totals()
        self._bump_version()

    def assign_customer(self, customer_id: str | None) -> None:
        CustomerAssignmentPolicy.ensure_can_assign(self.status)
        if customer_id is not None:
            _ids(customer_id)
        self.customer_id = customer_id
        self._bump_version()

    # ── checkout / lifecycle ─────────────────────────────────────────────

    def begin_checkout(self) -> None:
        CheckoutPolicy.ensure_can_checkout(
            status=self.status, line_count=len(self.lines), total=self.totals.total)
        self.status = SaleStatus.CHECKOUT_PENDING
        self._bump_version()

    def mark_payment_pending(self) -> None:
        SaleLifecyclePolicy.ensure_transition(current=self.status, target=SaleStatus.PAYMENT_PENDING)
        self.status = SaleStatus.PAYMENT_PENDING
        self._bump_version()

    @property
    def total_paid(self) -> Decimal:
        total = Decimal("0")
        for payment in self.payments:
            total += payment.amount
        return total

    @property
    def is_mixed_payment(self) -> bool:
        return len({payment.method for payment in self.payments}) > 1

    def record_payment(
        self, *, method: PaymentMethod, amount: Decimal, captured_by_user_id: str,
        reference: str | None = None,
    ) -> SalePayment:
        """POS-13/§30-36. Legal from CHECKOUT_PENDING or PAYMENT_PENDING —
        does NOT itself force a PAYMENT_PENDING transition (the lifecycle
        table already allows completing straight from CHECKOUT_PENDING for
        the common single-method case; callers that want an explicit
        "awaiting payment" state call `mark_payment_pending()` themselves)."""
        SalePaymentPolicy.ensure_can_record_payment(self.status)
        payment = SalePayment.create(
            sale_id=self.id, method=method, amount=amount,
            captured_by_user_id=captured_by_user_id, reference=reference)
        self.payments.append(payment)
        self._bump_version()
        return payment

    def complete(self) -> None:
        SaleLifecyclePolicy.ensure_transition(current=self.status, target=SaleStatus.COMPLETED)
        SalePaymentPolicy.ensure_fully_paid(total_paid=self.total_paid, sale_total=self.totals.total)
        self.status = SaleStatus.COMPLETED
        self.completed_at = _now()
        self._bump_version()

    def suspend(self, *, current_suspended_count: int, max_suspended_sales: int,
                suspended_by_user_id: str, workstation_id: str | None = None) -> None:
        SaleSuspensionPolicy.ensure_can_suspend(
            status=self.status, line_count=len(self.lines),
            current_suspended_count=current_suspended_count,
            max_suspended_sales=max_suspended_sales)
        _ids(suspended_by_user_id)
        self.status = SaleStatus.SUSPENDED
        self.suspended_at = _now()
        self.suspended_by_user_id = suspended_by_user_id
        self.suspended_workstation_id = workstation_id or self.workstation_id
        self._bump_version()

    def resume(self, *, resuming_user_id: str, resuming_workstation_id: str | None = None,
               allow_cross_user_resume: bool = True,
               allow_cross_workstation_resume: bool = True) -> None:
        _ids(resuming_user_id)
        SaleResumptionPolicy.ensure_can_resume(
            status=self.status,
            suspended_by_user_id=self.suspended_by_user_id or resuming_user_id,
            resuming_user_id=resuming_user_id,
            suspended_at_workstation_id=self.suspended_workstation_id or "",
            resuming_workstation_id=resuming_workstation_id or "",
            allow_cross_user_resume=allow_cross_user_resume,
            allow_cross_workstation_resume=allow_cross_workstation_resume,
        )
        self.status = SaleStatus.ACTIVE
        self.suspended_at = None
        self._bump_version()

    def cancel(self, reason: str) -> None:
        SaleCancellationPolicy.ensure_can_cancel(status=self.status, reason=reason)
        self.status = SaleStatus.CANCELLED
        self.cancelled_at = _now()
        self._bump_version()

    # ── post-payment: returns / reversal (§42-44) ───────────────────────────

    def return_line(
        self, *, line_id: str, quantity: Decimal, reason: str, requested_by_user_id: str,
        authorized_by_user_id: str,
    ) -> SaleReturn:
        """POS-16/§42-44. Only legal once a sale is COMPLETED (or already
        RETURNED_PARTIALLY, for a follow-up return) — pre-payment abandon is
        `cancel()`'s job, not this one. The original `SaleLine` is never
        mutated (it stays the point-in-time record of what was actually
        sold, same reasoning `product_snapshot` already applies) — returned
        quantity is tracked only via the accumulated `SaleReturn` records
        for that line."""
        SaleReturnPolicy.ensure_can_return(self.status)
        line = self._find_line(line_id)
        already_returned = sum(
            (r.quantity for r in self.returns if r.line_id == line_id), Decimal("0"))
        SaleReturnPolicy.ensure_quantity_within_line(
            line_quantity=line.quantity.value, already_returned=already_returned,
            requested=quantity)

        per_unit_value = (line.line_total / line.quantity.value).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP)
        amount = money(per_unit_value * quantity)
        sale_return = SaleReturn.create(
            sale_id=self.id, line_id=line_id, quantity=quantity, amount=amount, reason=reason,
            requested_by_user_id=requested_by_user_id,
            authorized_by_user_id=authorized_by_user_id)
        self.returns.append(sale_return)

        total_sold = sum((l.quantity.value for l in self.lines), Decimal("0"))
        total_returned = sum((r.quantity for r in self.returns), Decimal("0"))
        target = SaleStatus.RETURNED_FULLY if total_returned >= total_sold else SaleStatus.RETURNED_PARTIALLY
        if target != self.status:
            SaleLifecyclePolicy.ensure_transition(current=self.status, target=target)
            self.status = target
        self._bump_version()
        return sale_return

    def reverse(self, reason: str) -> None:
        """POS-16/§42-44: voids a COMPLETED sale outright — a distinct
        concept from a physical-goods return (§27's `RETURNED_*` states):
        wrong transaction, fraud, a sale that must be undone in full rather
        than settled item by item. Only legal from COMPLETED (never from an
        already-returned/cancelled/reversed sale) — enforced twice, once by
        `SaleReturnPolicy.ensure_can_reverse` (the specific business rule)
        and once by the lifecycle transition table (the structural
        guarantee), same double-guard style `cancel()` already uses via
        `SaleCancellationPolicy` wrapping `SaleLifecyclePolicy`."""
        if not (reason or "").strip():
            raise SaleReversalNotAllowedError("La reversa requiere un motivo")
        SaleReturnPolicy.ensure_can_reverse(self.status)
        SaleLifecyclePolicy.ensure_transition(current=self.status, target=SaleStatus.REVERSED)
        self.status = SaleStatus.REVERSED
        self.reversed_at = _now()
        self._bump_version()

    # ── fiscal: CFDI invoice requests (§15, §46, POS-18) ────────────────────

    def _find_invoice_request(self, request_id: str) -> SaleInvoiceRequest:
        for request in self.invoice_requests:
            if request.id == request_id:
                return request
        raise InvoiceRequestNotFoundError(
            f"No existe la solicitud de factura {request_id} en esta venta")

    def request_invoice(
        self, *, tax_identifier: str, legal_name: str, cfdi_use: str, requested_by_user_id: str,
    ) -> SaleInvoiceRequest:
        """POS-18 "Invoice request". Sales never validates the RFC's real
        format/existence against the SAT — that belongs to a real Fiscal
        bounded context this repository doesn't have; this only enforces
        what Sales itself can know: the sale is in an invoiceable state,
        a RFC was actually given, and no other request is still pending."""
        SaleInvoicePolicy.ensure_can_request(
            status=self.status, tax_identifier=tax_identifier,
            existing_requests=self.invoice_requests)
        request = SaleInvoiceRequest.create(
            sale_id=self.id, tax_identifier=tax_identifier, legal_name=legal_name,
            cfdi_use=cfdi_use, requested_by_user_id=requested_by_user_id)
        self.invoice_requests.append(request)
        self._bump_version()
        return request

    def mark_invoice_issued(self, request_id: str, *, uuid_fiscal: str) -> None:
        """POS-18 "Status": resolves a pending request once a real
        Fiscal/PAC integration (or a manual reconciliation) has an actual
        UUID fiscal to report — never called speculatively."""
        self._find_invoice_request(request_id).mark_issued(uuid_fiscal=uuid_fiscal)
        self._bump_version()

    def mark_invoice_error(self, request_id: str, *, error_message: str) -> None:
        """POS-18 "Errors": resolves a pending request with a real failure
        reason (PAC timeout, SAT rejection, etc.) — the request stays as
        permanent history; a cashier retries by requesting a NEW one."""
        self._find_invoice_request(request_id).mark_error(error_message=error_message)
        self._bump_version()
