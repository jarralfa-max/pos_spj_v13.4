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
from backend.domain.procurement.entities import SupplierInvoice
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


def _emit(uow, event_name, *, document_id, operation_id, actor_user_id=None, **extra):
    payload = build_event_payload(event_name, operation_id=operation_id,
                                  document_id=document_id, user_id=actor_user_id, **extra)
    uow.outbox.enqueue(event_id=payload["event_id"], event_name=event_name,
                       payload_json=json.dumps(payload), operation_id=operation_id)


class CaptureSupplierInvoiceUseCase:
    def __init__(self, authorization=None) -> None:
        self._auth = authorization or PurchaseAuthorizationPolicy()
        self._duplicates = DuplicatePurchasePolicy()

    def execute(self, connection, *, actor_user_id: str, operation_id: str, supplier_id: str,
                invoice_number: str, total: str, currency_code: str = "MXN",
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
                inv = SupplierInvoice.create(
                    uow.sequences.next_number("FPR", _year()), supplier_id, invoice_number,
                    Money(str(total), currency_code), purchase_order_id=purchase_order_id,
                    direct_purchase_id=direct_purchase_id, uuid_fiscal=uuid_fiscal)
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

    def __init__(self, authorization=None, *, price_tolerance: Tolerance | None = None) -> None:
        self._auth = authorization or PurchaseAuthorizationPolicy()
        self._matcher = InvoiceMatchingPolicy(price_tolerance=price_tolerance)

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
            has_document = bool(inv.purchase_order_id or inv.direct_purchase_id)
            ordered_total = None
            received_qty = None
            invoiced_qty = None
            has_receipt = inv.direct_purchase_id is not None
            if inv.purchase_order_id:
                po = uow.orders.get(inv.purchase_order_id)
                if po is not None:
                    ordered_total = po.total()
                    received_qty = sum((ln.received_quantity for ln in po.lines), Decimal("0"))
                    invoiced_qty = received_qty
                    has_receipt = po.status in ("PARTIALLY_RECEIVED", "RECEIVED") or any(
                        ln.received_quantity > 0 for ln in po.lines)
            result = self._matcher.match(
                has_purchase_document=has_document, has_receipt=has_receipt,
                ordered_total=ordered_total, received_quantity=received_qty,
                invoiced_quantity=invoiced_qty, invoice_total=inv.total)
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
                _emit(uow, ProcurementEvents.PURCHASE_PAYABLE_CREATED, document_id=inv.id,
                      operation_id=operation_id, actor_user_id=actor_user_id,
                      supplier_id=inv.supplier_id, amount=str(inv.total.amount))
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
                captured_by_user_id: str, reason: str) -> ProcurementResult:
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
            try:
                self._sod.enforce_invoice_clerk_not_variance_releaser(
                    captured_by_user_id, releaser_user_id)
            except ProcurementDomainError as exc:
                return ProcurementResult.fail(str(exc), "SEGREGATION", operation_id=operation_id)
            inv.status = "APPROVED"
            uow.invoices.save(inv)
            uow.invoices.record_match(invoice_id=inv.id, result="VARIANCE_RELEASED",
                                      released_by_user_id=releaser_user_id, notes=reason.strip())
            uow.audit.record(action=ProcurementEvents.SUPPLIER_INVOICE_MATCHED,
                             actor_user_id=releaser_user_id, authorized_by=releaser_user_id,
                             document_id=inv.id, reason=reason.strip(), operation_id=operation_id)
            _emit(uow, ProcurementEvents.PURCHASE_PAYABLE_CREATED, document_id=inv.id,
                  operation_id=operation_id, actor_user_id=releaser_user_id,
                  supplier_id=inv.supplier_id, amount=str(inv.total.amount))
        return ProcurementResult.ok("Diferencia liberada; CxP generada", entity_id=inv.id,
                                    operation_id=operation_id, status=inv.status)
