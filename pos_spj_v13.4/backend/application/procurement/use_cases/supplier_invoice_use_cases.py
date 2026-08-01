"""Supplier-invoice use cases (§60) — capture, three-way match, block/release,
and payable creation (CxP).

Duplicate captures are blocked structurally (UNIQUE supplier+invoice_number) and
detected by policy. Three-way matching compares order↔receipt↔invoice; a variance
must be released by a user who is NOT the one who captured it (segregation). A
matched/released invoice raises a payable via a post-commit event.
"""

from __future__ import annotations

import json
from decimal import Decimal

from backend.application.procurement.authorization import PurchaseAuthorizationPolicy
from backend.application.procurement.permissions import PurchasePermissions
from backend.application.procurement.result import ProcurementResult
from backend.domain.procurement.entities import SupplierInvoice, SupplierInvoiceLine
from backend.domain.procurement.events import ProcurementEvents, build_event_payload
from backend.domain.procurement.exceptions import (
    ProcurementDomainError,
    PurchasePermissionDeniedError,
)
from backend.domain.procurement.policies import SegregationOfDutiesPolicy
from backend.domain.procurement.receiving_matching_policies import (
    DuplicatePurchasePolicy,
    InvoiceMatchingPolicy,
    MatchResult,
)
from backend.domain.procurement.value_objects import Money, Tolerance
from backend.infrastructure.db.repositories.procurement.unit_of_work import (
    ProcurementUnitOfWork,
)


def _year() -> int:
    from datetime import date
    return date.today().year


def _emit(uow, event_name, *, document_id, operation_id, actor_user_id=None,
          deduplication_key=None, **extra):
    payload = build_event_payload(event_name, operation_id=operation_id,
                                  document_id=document_id, user_id=actor_user_id, **extra)
    uow.outbox.enqueue(event_id=payload["event_id"], event_name=event_name,
                       payload_json=json.dumps(payload), operation_id=operation_id,
                       deduplication_key=deduplication_key)


class CaptureSupplierInvoiceUseCase:
    def __init__(self, authorization=None, supplier_directory=None) -> None:
        self._auth = authorization or PurchaseAuthorizationPolicy()
        self._supplier_directory = supplier_directory
        self._duplicates = DuplicatePurchasePolicy()

    def execute(self, connection, *, actor_user_id: str, operation_id: str, supplier_id: str,
                invoice_number: str, total: str, currency_code: str = "MXN",
                lines: list[dict] | None = None,
                purchase_order_id: str | None = None,
                direct_purchase_id: str | None = None,
                uuid_fiscal: str | None = None) -> ProcurementResult:
        try:
            self._auth.require(actor_user_id, PurchasePermissions.INVOICE_CAPTURE)
        except PurchasePermissionDeniedError as exc:
            return ProcurementResult.fail(str(exc), "PERMISSION_DENIED",
                                          operation_id=operation_id)
        with ProcurementUnitOfWork(connection) as uow:
            existing = uow.invoices.get_by_operation(operation_id)
            if existing is not None:
                return ProcurementResult.ok("Factura ya capturada", entity_id=existing.id,
                                            operation_id=operation_id, status=existing.status)
            if uow.invoices.exists_for_supplier(supplier_id, invoice_number.strip()):
                return ProcurementResult.fail("Factura duplicada del proveedor",
                                              "DUPLICATE_INVOICE", operation_id=operation_id)
            try:
                if self._supplier_directory is not None:
                    self._supplier_directory.require_eligible(supplier_id)
                if not lines:
                    return ProcurementResult.fail(
                        "La factura requiere líneas reales", "EMPTY_INVOICE_LINES",
                        operation_id=operation_id)
                inv = SupplierInvoice.create(
                    uow.sequences.next_number("FPR", _year()), supplier_id, invoice_number,
                    Money(str(total), currency_code), purchase_order_id=purchase_order_id,
                    direct_purchase_id=direct_purchase_id, uuid_fiscal=uuid_fiscal,
                    captured_by_user_id=actor_user_id)
                for raw in lines:
                    inv.lines.append(SupplierInvoiceLine.create(
                        inv.id, raw["product_id"], raw["invoiced_quantity"],
                        Money(str(raw["unit_price"]), currency_code),
                        Money(str(raw.get("tax", "0")), currency_code),
                        purchase_order_line_id=raw.get("purchase_order_line_id"),
                        direct_purchase_line_id=raw.get("direct_purchase_line_id"),
                        receipt_line_id=raw.get("receipt_line_id")))
                subtotal = sum((line.subtotal().amount for line in inv.lines), Decimal("0"))
                taxes = sum((line.tax.amount for line in inv.lines), Decimal("0"))
                inv.subtotal = Money(subtotal, currency_code)
                inv.tax_total = Money(taxes, currency_code)
                if inv.total.amount != subtotal + taxes:
                    return ProcurementResult.fail(
                        "El total no coincide con las líneas de factura", "TOTAL_MISMATCH",
                        operation_id=operation_id)
            except (ProcurementDomainError, ValueError) as exc:
                return ProcurementResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.invoices.save(inv)
            uow.invoices.set_operation_id(inv.id, operation_id)
            uow.audit.record(action=ProcurementEvents.SUPPLIER_INVOICE_CAPTURED,
                             actor_user_id=actor_user_id, document_id=inv.id,
                             operation_id=operation_id)
            _emit(uow, ProcurementEvents.SUPPLIER_INVOICE_CAPTURED, document_id=inv.id,
                  operation_id=operation_id, actor_user_id=actor_user_id,
                  supplier_id=supplier_id, total=str(inv.total.amount))
        return ProcurementResult.ok("Factura capturada", entity_id=inv.id,
                                    operation_id=operation_id, status=inv.status)


class MatchSupplierInvoiceUseCase:
    """Three-way match against the linked order + its receipts. On MATCHED it
    raises a payable; on a variance it stays WITH_DIFFERENCES pending release."""

    def __init__(self, authorization=None, *, price_tolerance: Tolerance | None = None,
                 tolerance_settings=None) -> None:
        self._auth = authorization or PurchaseAuthorizationPolicy()
        self._matcher = InvoiceMatchingPolicy(price_tolerance=price_tolerance)
        self._tolerance_settings = tolerance_settings

    def execute(self, connection, *, actor_user_id: str, operation_id: str,
                invoice_id: str) -> ProcurementResult:
        try:
            self._auth.require(actor_user_id, PurchasePermissions.INVOICE_MATCH)
        except PurchasePermissionDeniedError as exc:
            return ProcurementResult.fail(str(exc), "PERMISSION_DENIED",
                                          operation_id=operation_id)
        with ProcurementUnitOfWork(connection) as uow:
            inv = uow.invoices.get(invoice_id)
            if inv is None:
                return ProcurementResult.fail("Factura inexistente", "NOT_FOUND",
                                              operation_id=operation_id)
            if inv.status in ("MATCHED", "APPROVED", "POSTED"):
                return ProcurementResult.ok(
                    "Factura ya conciliada", entity_id=inv.id,
                    operation_id=operation_id, status=inv.status,
                    match_result=inv.match_result or "MATCHED")
            matcher = self._matcher
            if self._tolerance_settings is not None:
                configured = self._tolerance_settings.invoice_tolerances(
                    supplier_id=inv.supplier_id)
                matcher = InvoiceMatchingPolicy(
                    price_tolerance=configured.price,
                    quantity_tolerance=configured.quantity,
                    tax_tolerance=configured.tax)
            has_document = bool(inv.purchase_order_id or inv.direct_purchase_id)
            accepted = uow.receipts.accepted_by_product(
                purchase_order_id=inv.purchase_order_id,
                direct_purchase_id=inv.direct_purchase_id)
            has_receipt = bool(accepted)
            po = direct = None
            if inv.purchase_order_id:
                po = uow.orders.get(inv.purchase_order_id)
            elif inv.direct_purchase_id:
                direct = uow.direct_purchases.get(inv.direct_purchase_id)
            if not has_document:
                result = MatchResult.MISSING_PURCHASE_DOCUMENT
            elif not has_receipt:
                result = MatchResult.MISSING_RECEIPT
            elif inv.purchase_order_id and po is not None:
                result = matcher.match_lines(
                    ordered_lines={line.id: {
                        "accepted_quantity": accepted.get(line.product_id, Decimal("0")),
                        "unit_price": line.unit_price.amount,
                        "tax": "0",
                    } for line in po.lines},
                    invoice_lines=[{
                        "purchase_order_line_id": line.purchase_order_line_id,
                        "invoiced_quantity": line.invoiced_quantity +
                        uow.invoices.previously_invoiced_quantity(
                            line.purchase_order_line_id or "", inv.id),
                        "unit_price": line.unit_price.amount,
                        "tax": line.tax.amount,
                    } for line in inv.lines])
            elif inv.direct_purchase_id and direct is not None:
                ordered = {line.id: {
                    "accepted_quantity": accepted.get(line.product_id, Decimal("0")),
                    "unit_price": line.unit_cost.amount, "tax": line.tax.amount,
                } for line in direct.lines}
                result = matcher.match_lines(
                    ordered_lines=ordered,
                    invoice_lines=[{
                        "purchase_order_line_id": line.direct_purchase_line_id,
                        "invoiced_quantity": line.invoiced_quantity,
                        "unit_price": line.unit_price.amount, "tax": line.tax.amount,
                    } for line in inv.lines])
            else:
                result = MatchResult.MISSING_PURCHASE_DOCUMENT
            inv.matched_by_user_id = actor_user_id
            inv.record_match(result.value)
            uow.invoices.save(inv)
            uow.invoices.record_match(invoice_id=inv.id, result=result.value)
            uow.audit.record(action=ProcurementEvents.SUPPLIER_INVOICE_MATCHED,
                             actor_user_id=actor_user_id, document_id=inv.id,
                             reason=result.value, operation_id=operation_id)
            _emit(uow, ProcurementEvents.SUPPLIER_INVOICE_MATCHED, document_id=inv.id,
                  operation_id=operation_id, actor_user_id=actor_user_id,
                  supplier_id=inv.supplier_id, match_result=result.value)
            if result is MatchResult.MATCHED:
                _emit(uow, ProcurementEvents.ACCOUNT_PAYABLE_CREATE_REQUESTED,
                      document_id=inv.id,
                      operation_id=operation_id, actor_user_id=actor_user_id,
                      supplier_id=inv.supplier_id, amount=str(inv.total.amount),
                      source_type="SUPPLIER_INVOICE", source_id=inv.id,
                      deduplication_key=f"SUPPLIER_INVOICE:{inv.id}")
        return ProcurementResult.ok("Factura conciliada", entity_id=inv.id,
                                    operation_id=operation_id, status=inv.status,
                                    match_result=result.value)


class ReleaseInvoiceVarianceUseCase:
    """Releases a variance so the invoice can become payable. The releaser must be
    different from whoever captured the invoice (segregation of duties)."""

    def __init__(self, authorization=None) -> None:
        self._auth = authorization or PurchaseAuthorizationPolicy()
        self._sod = SegregationOfDutiesPolicy()

    def execute(self, connection, *, releaser_user_id: str, operation_id: str, invoice_id: str,
                reason: str, captured_by_user_id: str | None = None) -> ProcurementResult:
        try:
            self._auth.require(releaser_user_id, PurchasePermissions.INVOICE_RELEASE_VARIANCE)
        except PurchasePermissionDeniedError as exc:
            return ProcurementResult.fail(str(exc), "PERMISSION_DENIED",
                                          operation_id=operation_id)
        if not reason or not reason.strip():
            return ProcurementResult.fail("La liberación requiere un motivo", "VALIDATION",
                                          operation_id=operation_id)
        with ProcurementUnitOfWork(connection) as uow:
            inv = uow.invoices.get(invoice_id)
            if inv is None:
                return ProcurementResult.fail("Factura inexistente", "NOT_FOUND",
                                              operation_id=operation_id)
            if inv.status in ("APPROVED", "POSTED"):
                return ProcurementResult.ok("Diferencia ya liberada", entity_id=inv.id,
                                            operation_id=operation_id, status=inv.status)
            try:
                self._sod.enforce_invoice_clerk_not_variance_releaser(
                    inv.captured_by_user_id, releaser_user_id)
            except ProcurementDomainError as exc:
                return ProcurementResult.fail(str(exc), "SEGREGATION", operation_id=operation_id)
            inv.status = "APPROVED"
            inv.released_by_user_id = releaser_user_id
            uow.invoices.save(inv)
            uow.invoices.record_match(invoice_id=inv.id, result="VARIANCE_RELEASED",
                                      released_by_user_id=releaser_user_id, notes=reason.strip())
            uow.audit.record(action=ProcurementEvents.SUPPLIER_INVOICE_MATCHED,
                             actor_user_id=releaser_user_id, authorized_by=releaser_user_id,
                             document_id=inv.id, reason=reason.strip(), operation_id=operation_id)
            _emit(uow, ProcurementEvents.ACCOUNT_PAYABLE_CREATE_REQUESTED,
                  document_id=inv.id,
                  operation_id=operation_id, actor_user_id=releaser_user_id,
                  supplier_id=inv.supplier_id, amount=str(inv.total.amount),
                  source_type="SUPPLIER_INVOICE", source_id=inv.id,
                  deduplication_key=f"SUPPLIER_INVOICE:{inv.id}")
        return ProcurementResult.ok("Diferencia liberada; CxP generada", entity_id=inv.id,
                                    operation_id=operation_id, status=inv.status)
