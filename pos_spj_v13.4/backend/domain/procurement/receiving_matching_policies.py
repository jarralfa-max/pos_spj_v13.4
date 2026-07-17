"""Receiving, invoice-matching, emergency and duplicate policies (PUR-3).

Pure rules. Tolerances decide warn/block/authorize; three-way matching compares
order↔receipt↔invoice; emergency requires justification + authorization with
pending documentary regularization; duplicates are detected, never merged.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum

from backend.domain.procurement.exceptions import (
    AuthorizationRequiredError,
    ProcurementDomainError,
)
from backend.domain.procurement.value_objects import Money, Tolerance


class ToleranceOutcome(str, Enum):
    WITHIN = "WITHIN"
    OVER_TOLERANCE = "OVER_TOLERANCE"


class ReceiptTolerancePolicy:
    """Compares received/price vs expected against a tolerance."""

    def evaluate_quantity(self, ordered: Decimal, received: Decimal,
                          tolerance: Tolerance) -> ToleranceOutcome:
        return (ToleranceOutcome.WITHIN if tolerance.within(Decimal(str(ordered)),
                                                            Decimal(str(received)))
                else ToleranceOutcome.OVER_TOLERANCE)

    def enforce_over_receipt(self, ordered: Decimal, received: Decimal,
                             tolerance: Tolerance, *, has_override_permission: bool) -> None:
        """Over-receipt beyond tolerance needs an explicit override/authorization."""
        if Decimal(str(received)) <= Decimal(str(ordered)):
            return
        if self.evaluate_quantity(ordered, received, tolerance) is ToleranceOutcome.WITHIN:
            return
        if not has_override_permission:
            raise AuthorizationRequiredError(
                "La cantidad recibida excede la tolerancia; requiere autorización")


class MatchResult(str, Enum):
    MATCHED = "MATCHED"
    QUANTITY_VARIANCE = "QUANTITY_VARIANCE"
    PRICE_VARIANCE = "PRICE_VARIANCE"
    TAX_VARIANCE = "TAX_VARIANCE"
    DUPLICATE_INVOICE = "DUPLICATE_INVOICE"
    MISSING_RECEIPT = "MISSING_RECEIPT"
    MISSING_ORDER = "MISSING_ORDER"
    MISSING_PURCHASE_DOCUMENT = "MISSING_PURCHASE_DOCUMENT"


class InvoiceMatchingPolicy:
    """Three-way match (order↔receipt↔invoice) or two-way for direct purchases."""

    def __init__(self, *, price_tolerance: Tolerance | None = None,
                 quantity_tolerance: Tolerance | None = None) -> None:
        self._price_tol = price_tolerance or Tolerance(Decimal("0"))
        self._qty_tol = quantity_tolerance or Tolerance(Decimal("0"))

    def match(self, *, has_purchase_document: bool, has_receipt: bool,
              ordered_total: Money | None, received_quantity: Decimal | None,
              invoiced_quantity: Decimal | None, invoice_total: Money,
              is_duplicate: bool = False) -> MatchResult:
        if is_duplicate:
            return MatchResult.DUPLICATE_INVOICE
        if not has_purchase_document:
            return MatchResult.MISSING_PURCHASE_DOCUMENT
        if not has_receipt:
            return MatchResult.MISSING_RECEIPT
        if received_quantity is not None and invoiced_quantity is not None:
            if not self._qty_tol.within(Decimal(str(received_quantity)),
                                        Decimal(str(invoiced_quantity))):
                return MatchResult.QUANTITY_VARIANCE
        if ordered_total is not None:
            if not self._price_tol.within(ordered_total.amount, invoice_total.amount):
                return MatchResult.PRICE_VARIANCE
        return MatchResult.MATCHED


class EmergencyPurchasePolicy:
    """Emergency purchases require justification + authorization; documentary
    regularization stays pending afterwards (§ emergency flow)."""

    def enforce(self, *, justification: str, authorized_by_user_id: str | None) -> None:
        if not justification or not justification.strip():
            raise ProcurementDomainError("La compra de emergencia requiere justificación")
        if not authorized_by_user_id:
            raise AuthorizationRequiredError(
                "La compra de emergencia requiere autorización")

    def requires_regularization(self) -> bool:
        return True


class DuplicatePurchasePolicy:
    """Detects duplicate supplier invoices and repeated occasional suppliers.
    Never merges automatically."""

    def is_duplicate_invoice(self, supplier_id: str, invoice_number: str,
                             existing: list[dict]) -> bool:
        target = (supplier_id, (invoice_number or "").strip().upper())
        return any((row.get("supplier_id"), (row.get("invoice_number") or "").strip().upper())
                   == target for row in existing)

    def occasional_supplier_needs_registration(self, occurrences: int, *,
                                               threshold: int = 3) -> bool:
        """A recurring 'occasional' supplier must be registered in the master (§13)."""
        return occurrences >= threshold


class PurchaseApprovalPolicy:
    """Separation of duties for order/requisition approval."""

    def enforce_buyer_not_self_approving(self, buyer_id: str, approver_id: str, *,
                                         within_limit: bool) -> None:
        if not within_limit and buyer_id and buyer_id == approver_id:
            from backend.domain.procurement.exceptions import SegregationOfDutiesError
            raise SegregationOfDutiesError(
                "Separación de funciones: quien realiza la compra elevada no la autoriza")
