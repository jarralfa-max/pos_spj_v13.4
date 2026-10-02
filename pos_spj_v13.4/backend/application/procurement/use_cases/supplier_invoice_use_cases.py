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
from backend.domain.procurement.enums import PurchaseNature
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
    allocate_accepted_quantities,
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


def _nature_subtotals(lines) -> dict[str, str]:
    """Pre-tax subtotal per purchase_nature — lets the finance side recognize
    the payable's debit side (Inventario/Gasto/Activo) against the right
    account instead of dumping every purchase into Inventario."""
    totals: dict[str, Decimal] = {}
    for line in lines:
        nature = line.purchase_nature.value
        totals[nature] = totals.get(nature, Decimal("0")) + line.subtotal().amount
    return {nature: str(amount) for nature, amount in totals.items()}


#: Diferencias que un segundo usuario PUEDE liberar (decisión del usuario,
#: 2026-09-18): precio, cantidad o impuesto, y la factura sin documento de
#: compra — el §11 la pide como caso autorizado. Nunca una factura SIN
#: RECEPCIÓN (generaría deuda por mercancía que no llegó), una duplicada, una
#: con líneas que no están en la orden, ni una que nunca se concilió.
RELEASABLE_MATCH_RESULTS = frozenset({
    "PRICE_VARIANCE", "QUANTITY_VARIANCE", "TAX_VARIANCE", "MISSING_PURCHASE_DOCUMENT",
})


def _already_paid_in_cash(direct) -> bool:
    """¿La factura soporta una compra que YA se pagó de contado?

    Medido el 2026-09-18: conciliar la factura de una compra de contado creaba
    una cuenta por pagar a un proveedor YA PAGADO y un segundo asiento — el
    inventario se cargaba dos veces y la deuda invitaba a pagarle otra vez. El
    §11 lo dice explícito: la compra de contado termina como pago en Tesorería,
    no como CxP. La factura se concilia (es el soporte fiscal del pago), pero
    no genera deuda.
    """
    return (direct is not None
            and getattr(direct.payment_condition, "value", direct.payment_condition)
            == "IMMEDIATE_PAYMENT")


def _payment_term_days(payment_terms, supplier_id: str) -> int:
    """Días de crédito del proveedor para el vencimiento (decisión del usuario).
    Sin condiciones capturadas, vence el mismo día."""
    if payment_terms is None:
        return 0
    try:
        dias = payment_terms.credit_days(supplier_id)
    except Exception:
        return 0
    return max(0, int(dias or 0))


def _net_unit_price(quantity: Decimal, gross_price: Decimal, discount: Decimal) -> Decimal:
    """Precio pactado NETO de descuento: la factura no trae descuento por línea,
    así que su precio unitario debe ser ya el neto. Antes se comparaba contra
    el precio bruto y una factura sin el descuento pactado conciliaba."""
    if quantity <= 0:
        return gross_price
    return (quantity * gross_price - discount) / quantity


def _accepted_weight_by_line(uow, po) -> dict[str, Decimal]:
    """Peso real ACEPTADO por línea de orden (para lo que se paga por kg)."""
    from backend.application.procurement.use_cases.purchase_order_use_cases import (
        accepted_weight,
    )
    weights: dict[str, Decimal] = {}
    for receipt in uow.receipts.completed_for_document(purchase_order_id=po.id):
        for line in receipt.lines:
            weight = accepted_weight(line)
            if weight and line.purchase_order_line_id:
                weights[line.purchase_order_line_id] = (
                    weights.get(line.purchase_order_line_id, Decimal("0")) + weight)
    return weights


def _order_comparison(uow, po) -> dict[str, dict]:
    by_line, unlinked = uow.receipts.accepted_by_source(purchase_order_id=po.id)
    accepted = allocate_accepted_quantities(
        [(line.id, line.product_id, line.ordered_quantity) for line in po.lines],
        by_line, unlinked)
    weights = (_accepted_weight_by_line(uow, po)
               if any(line.priced_by_weight() for line in po.lines) else {})
    return {line.id: {
        # A $/kg la factura cobra kg: se compara contra el PESO REAL aceptado.
        "accepted_quantity": (weights.get(line.id, Decimal("0")) if line.priced_by_weight()
                              else accepted.get(line.id, Decimal("0"))),
        "unit_price": _net_unit_price(line.billable_quantity(), line.unit_price.amount,
                                      line.discount),
        # Impuesto declarado en la orden (FASE 7), por unidad. Una orden sin
        # impuesto capturado NO se compara (decisión del usuario 2026-09-18):
        # cero puede ser "tasa 0" o "nadie lo capturó", y no se distinguen.
        "tax_per_unit": (line.tax / line.billable_quantity()
                         if line.tax > 0 and line.billable_quantity() > 0 else None),
    } for line in po.lines}


def _direct_comparison(uow, direct) -> dict[str, dict]:
    # La recepción de la compra rápida se guarda en unidad de INVENTARIO
    # (125 kg) y la factura cobra lo FACTURABLE: la unidad de compra (5
    # costales) o, con peso variable a $/kg, el peso real (127.850 kg). Se
    # reparte en inventario y se convierte a lo facturable de cada línea.
    by_line, unlinked = uow.receipts.accepted_by_source(direct_purchase_id=direct.id)
    accepted = allocate_accepted_quantities(
        [(line.id, line.product_id, line.inventory_quantity()) for line in direct.lines],
        by_line, unlinked)
    result = {}
    for line in direct.lines:
        billable, inventory = line.billable_quantity(), line.inventory_quantity()
        accepted_inventory = accepted.get(line.id, Decimal("0"))
        result[line.id] = {
            "accepted_quantity": (accepted_inventory * billable / inventory
                                  if inventory > 0 else Decimal("0")),
            "unit_price": _net_unit_price(billable, line.unit_cost.amount,
                                          line.discount.amount),
            # La compra rápida siempre captura su impuesto (cero incluido).
            "tax_per_unit": line.tax.amount / billable if billable > 0 else Decimal("0"),
        }
    return result


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
            uuid_fiscal = (uuid_fiscal or "").strip() or None
            if uuid_fiscal and uow.invoices.exists_fiscal_uuid(uuid_fiscal):
                return ProcurementResult.fail(
                    "Ese folio fiscal (UUID) ya está capturado en otra factura",
                    "DUPLICATE_INVOICE", operation_id=operation_id)
            try:
                if self._supplier_directory is not None:
                    self._supplier_directory.require_eligible(supplier_id)
                if not lines:
                    return ProcurementResult.fail(
                        "La factura requiere líneas reales", "EMPTY_INVOICE_LINES",
                        operation_id=operation_id)
                inv = SupplierInvoice.create(
                    uow.sequences.next_number("FPR", _year()), supplier_id,
                    invoice_number.strip(),
                    Money(str(total), currency_code), purchase_order_id=purchase_order_id,
                    direct_purchase_id=direct_purchase_id, uuid_fiscal=uuid_fiscal,
                    captured_by_user_id=actor_user_id)
                for raw in lines:
                    inv.lines.append(SupplierInvoiceLine.create(
                        inv.id, raw["product_id"], raw["invoiced_quantity"],
                        Money(str(raw["unit_price"]), currency_code),
                        Money(str(raw.get("tax", "0")), currency_code),
                        purchase_nature=PurchaseNature(
                            raw.get("purchase_nature", PurchaseNature.INVENTORY.value)),
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
                 tolerance_settings=None, payment_terms=None) -> None:
        self._auth = authorization or PurchaseAuthorizationPolicy()
        self._matcher = InvoiceMatchingPolicy(price_tolerance=price_tolerance)
        self._tolerance_settings = tolerance_settings
        #: `SupplierPaymentTermsPort`: días de crédito para el vencimiento.
        self._payment_terms = payment_terms

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
                    ordered_lines=_order_comparison(uow, po),
                    invoice_lines=[{
                        "purchase_order_line_id": line.purchase_order_line_id,
                        "invoiced_quantity": line.invoiced_quantity +
                        uow.invoices.previously_invoiced_quantity(
                            line.purchase_order_line_id or "", inv.id),
                        "this_quantity": line.invoiced_quantity,
                        "unit_price": line.unit_price.amount,
                        "tax": line.tax.amount,
                    } for line in inv.lines])
            elif inv.direct_purchase_id and direct is not None:
                result = matcher.match_lines(
                    ordered_lines=_direct_comparison(uow, direct),
                    invoice_lines=[{
                        "purchase_order_line_id": line.direct_purchase_line_id,
                        "invoiced_quantity": line.invoiced_quantity +
                        uow.invoices.previously_invoiced_direct_quantity(
                            line.direct_purchase_line_id or "", inv.id),
                        "this_quantity": line.invoiced_quantity,
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
            ya_pagada = _already_paid_in_cash(direct)
            if result is MatchResult.MATCHED and not ya_pagada:
                branch_id = (po.branch_id if po is not None
                            else direct.branch_id if direct is not None else None)
                _emit(uow, ProcurementEvents.ACCOUNT_PAYABLE_CREATE_REQUESTED,
                      payment_term_days=_payment_term_days(self._payment_terms,
                                                           inv.supplier_id),
                      document_id=inv.id, document_number=inv.document_number,
                      branch_id=branch_id,
                      operation_id=operation_id, actor_user_id=actor_user_id,
                      supplier_id=inv.supplier_id, amount=str(inv.total.amount),
                      currency_code=inv.total.currency_code,
                      nature_subtotals=_nature_subtotals(inv.lines),
                      tax_total=str(inv.tax_total.amount if inv.tax_total else "0"),
                      source_type="SUPPLIER_INVOICE", source_id=inv.id,
                      deduplication_key=f"SUPPLIER_INVOICE:{inv.id}")
        mensaje = ("Factura conciliada; la compra ya se pagó de contado, no genera "
                   "cuenta por pagar" if ya_pagada and result is MatchResult.MATCHED
                   else "Factura conciliada")
        return ProcurementResult.ok(mensaje, entity_id=inv.id,
                                    operation_id=operation_id, status=inv.status,
                                    match_result=result.value)


class ReleaseInvoiceVarianceUseCase:
    """Releases a variance so the invoice can become payable. The releaser must be
    different from whoever captured the invoice (segregation of duties)."""

    def __init__(self, authorization=None, *, payment_terms=None) -> None:
        self._auth = authorization or PurchaseAuthorizationPolicy()
        self._sod = SegregationOfDutiesPolicy()
        self._payment_terms = payment_terms

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
            # Antes se liberaba DESDE CUALQUIER ESTADO, incluida una factura sin
            # recepción: generaba deuda por mercancía que no había llegado.
            if (inv.match_result or "") not in RELEASABLE_MATCH_RESULTS:
                motivo = {
                    "MISSING_RECEIPT": "no hay recepción de la mercancía; primero debe "
                                       "recibirse",
                    "DUPLICATE_INVOICE": "la factura está duplicada",
                    "MISSING_ORDER": "tiene líneas que no están en la orden",
                    "MATCHED": "la factura ya concilió sin diferencias",
                }.get(inv.match_result or "", "la factura aún no se ha conciliado")
                return ProcurementResult.fail(
                    f"No se puede liberar: {motivo}.", "NOT_RELEASABLE",
                    operation_id=operation_id)
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
            po = uow.orders.get(inv.purchase_order_id) if inv.purchase_order_id else None
            direct = (uow.direct_purchases.get(inv.direct_purchase_id)
                     if inv.direct_purchase_id else None)
            branch_id = (po.branch_id if po is not None
                        else direct.branch_id if direct is not None else None)
            if _already_paid_in_cash(direct):
                return ProcurementResult.ok(
                    "Diferencia liberada; la compra ya se pagó de contado, no genera "
                    "cuenta por pagar", entity_id=inv.id, operation_id=operation_id,
                    status=inv.status)
            _emit(uow, ProcurementEvents.ACCOUNT_PAYABLE_CREATE_REQUESTED,
                  payment_term_days=_payment_term_days(self._payment_terms, inv.supplier_id),
                  document_id=inv.id, document_number=inv.document_number,
                  branch_id=branch_id,
                  operation_id=operation_id, actor_user_id=releaser_user_id,
                  supplier_id=inv.supplier_id, amount=str(inv.total.amount),
                  currency_code=inv.total.currency_code,
                  nature_subtotals=_nature_subtotals(inv.lines),
                  tax_total=str(inv.tax_total.amount if inv.tax_total else "0"),
                  source_type="SUPPLIER_INVOICE", source_id=inv.id,
                  deduplication_key=f"SUPPLIER_INVOICE:{inv.id}")
        return ProcurementResult.ok("Diferencia liberada; CxP generada", entity_id=inv.id,
                                    operation_id=operation_id, status=inv.status)
