"""Entities for the procurement bounded context.

Two operative routes over shared building blocks:
- DirectPurchase (fast: draft → [authorization] → confirmed → received/pending → reversible)
- Enterprise: PurchaseRequisition → RequestForQuotation/SupplierQuote →
  PurchaseOrder → GoodsReceipt → SupplierInvoice.

Money/weight/quantity are Decimal, never float. Totals are computed in the
domain (never in the widget). Confirmed documents are immutable; nothing is
physically deleted when history exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal

from backend.domain.procurement.enums import (
    DirectPurchaseMode,
    DiscrepancyType,
    DocumentStatus,
    PaymentCondition,
    PaymentSource,
    PurchaseOrderStatus,
    PurchaseType,
    RequisitionStatus,
    SourceChannel,
)
from backend.domain.procurement.exceptions import (
    InvalidPurchaseStateError,
    ProcurementDomainError,
)
from backend.domain.procurement.value_objects import DocumentNumber, Money
from backend.shared.ids import new_uuid

_TWO = Decimal("0.01")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dec(value) -> Decimal:
    if isinstance(value, float):
        raise ProcurementDomainError("No se permite float en montos/cantidades")
    return Decimal(str(value))


# ── direct purchase ───────────────────────────────────────────────────────────
@dataclass(slots=True)
class DirectPurchaseLine:
    id: str
    product_id: str
    description: str
    quantity: Decimal
    unit_cost: Money
    purchase_unit: str = "PZA"
    inventory_unit: str = "PZA"
    conversion_factor: Decimal = Decimal("1")
    discount: Money = None  # type: ignore[assignment]
    tax: Money = None  # type: ignore[assignment]
    destination_branch_id: str | None = None
    destination_warehouse_id: str | None = None

    @classmethod
    def create(cls, product_id: str, description: str, quantity, unit_cost: Money,
               **kwargs) -> "DirectPurchaseLine":
        q = _dec(quantity)
        if q <= 0:
            raise ProcurementDomainError("La cantidad debe ser mayor a cero")
        if unit_cost.is_negative():
            raise ProcurementDomainError("El costo no puede ser negativo")
        return cls(id=new_uuid(), product_id=product_id, description=description,
                   quantity=q, unit_cost=unit_cost, **kwargs)

    def __post_init__(self) -> None:
        self.quantity = _dec(self.quantity)
        self.conversion_factor = _dec(self.conversion_factor)
        if self.discount is None:
            self.discount = Money.zero(self.unit_cost.currency_code)
        if self.tax is None:
            self.tax = Money.zero(self.unit_cost.currency_code)

    def inventory_quantity(self) -> Decimal:
        return self.quantity * self.conversion_factor

    def line_subtotal(self) -> Money:
        return Money(self.quantity * self.unit_cost.amount, self.unit_cost.currency_code)

    def line_total(self) -> Money:
        total = self.line_subtotal().amount - self.discount.amount + self.tax.amount
        return Money(total, self.unit_cost.currency_code)


@dataclass(slots=True)
class PurchasePaymentInstruction:
    id: str
    source: PaymentSource
    amount: Money
    status: str = "REQUESTED"   # REQUESTED / CONFIRMED / CANCELLED

    @classmethod
    def create(cls, source: PaymentSource, amount: Money) -> "PurchasePaymentInstruction":
        return cls(id=new_uuid(), source=source, amount=amount)


@dataclass(slots=True)
class DirectPurchase:
    id: str
    document_number: str
    supplier_id: str
    branch_id: str
    warehouse_id: str
    mode: DirectPurchaseMode
    payment_condition: PaymentCondition
    currency_code: str = "MXN"
    source_channel: SourceChannel = SourceChannel.PROCUREMENT_DIRECT
    purchase_type: PurchaseType = PurchaseType.DIRECT
    status: DocumentStatus = DocumentStatus.DRAFT
    lines: list[DirectPurchaseLine] = field(default_factory=list)
    payment_instruction: PurchasePaymentInstruction | None = None
    created_by_user_id: str | None = None
    authorized_by_user_id: str | None = None
    authorization_reason: str = ""
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, document_number: DocumentNumber, supplier_id: str, branch_id: str,
               warehouse_id: str, mode: DirectPurchaseMode,
               payment_condition: PaymentCondition, *, created_by_user_id: str,
               currency_code: str = "MXN",
               source_channel: SourceChannel = SourceChannel.PROCUREMENT_DIRECT,
               purchase_type: PurchaseType = PurchaseType.DIRECT) -> "DirectPurchase":
        return cls(id=new_uuid(), document_number=str(document_number), supplier_id=supplier_id,
                   branch_id=branch_id, warehouse_id=warehouse_id, mode=mode,
                   payment_condition=payment_condition, currency_code=currency_code,
                   source_channel=source_channel, purchase_type=purchase_type,
                   created_by_user_id=created_by_user_id)

    def _assert_draft(self) -> None:
        if self.status not in (DocumentStatus.DRAFT, DocumentStatus.PENDING_AUTHORIZATION):
            raise InvalidPurchaseStateError(
                f"No se puede modificar una compra {self.status.value}")

    def add_line(self, line: DirectPurchaseLine) -> None:
        self._assert_draft()
        self.lines.append(line)
        self.updated_at = _utcnow()

    def remove_line(self, line_id: str) -> None:
        self._assert_draft()
        self.lines = [ln for ln in self.lines if ln.id != line_id]
        self.updated_at = _utcnow()

    def subtotal(self) -> Money:
        total = sum((ln.line_subtotal().amount for ln in self.lines), Decimal("0"))
        return Money(total, self.currency_code)

    def tax_total(self) -> Money:
        total = sum((ln.tax.amount for ln in self.lines), Decimal("0"))
        return Money(total, self.currency_code)

    def total(self) -> Money:
        total = sum((ln.line_total().amount for ln in self.lines), Decimal("0"))
        return Money(total.quantize(_TWO), self.currency_code)

    def request_authorization(self, reason: str) -> None:
        self._assert_draft()
        if not self.lines:
            raise InvalidPurchaseStateError("No se puede autorizar una compra sin líneas")
        self.status = DocumentStatus.PENDING_AUTHORIZATION
        self.authorization_reason = reason
        self.updated_at = _utcnow()

    def authorize(self, authorizer_user_id: str) -> None:
        if self.status is not DocumentStatus.PENDING_AUTHORIZATION:
            raise InvalidPurchaseStateError("La compra no está pendiente de autorización")
        self.authorized_by_user_id = authorizer_user_id
        self.status = DocumentStatus.DRAFT  # authorized → ready to confirm
        self.updated_at = _utcnow()

    def confirm(self) -> None:
        if self.status not in (DocumentStatus.DRAFT,):
            raise InvalidPurchaseStateError(
                f"Solo se confirma un borrador autorizado (está {self.status.value})")
        if not self.lines:
            raise InvalidPurchaseStateError("No se puede confirmar una compra sin líneas")
        self.status = DocumentStatus.CONFIRMED
        self.updated_at = _utcnow()

    def mark_received(self) -> None:
        if self.status is not DocumentStatus.CONFIRMED:
            raise InvalidPurchaseStateError("Solo se recibe una compra confirmada")
        self.status = DocumentStatus.RECEIVED
        self.updated_at = _utcnow()

    def reverse(self) -> None:
        if self.status not in (DocumentStatus.CONFIRMED, DocumentStatus.RECEIVED):
            raise InvalidPurchaseStateError("Solo se revierte una compra confirmada/recibida")
        self.status = DocumentStatus.REVERSED
        self.updated_at = _utcnow()

    def cancel_draft(self) -> None:
        if self.status not in (DocumentStatus.DRAFT, DocumentStatus.PENDING_AUTHORIZATION):
            raise InvalidPurchaseStateError("Solo se cancela un borrador")
        self.status = DocumentStatus.CANCELLED
        self.updated_at = _utcnow()

    def is_immediate_receipt(self) -> bool:
        return self.mode is DirectPurchaseMode.DIRECT_WITH_IMMEDIATE_RECEIPT


# ── requisition ───────────────────────────────────────────────────────────────
@dataclass(slots=True)
class RequisitionLine:
    id: str
    product_id: str
    quantity: Decimal
    estimated_unit_cost: Money | None = None
    required_date: date | None = None

    @classmethod
    def create(cls, product_id: str, quantity, **kwargs) -> "RequisitionLine":
        q = _dec(quantity)
        if q <= 0:
            raise ProcurementDomainError("La cantidad debe ser mayor a cero")
        return cls(id=new_uuid(), product_id=product_id, quantity=q, **kwargs)


@dataclass(slots=True)
class PurchaseRequisition:
    id: str
    document_number: str
    branch_id: str
    requested_by_user_id: str
    purchase_type: PurchaseType
    status: RequisitionStatus = RequisitionStatus.DRAFT
    priority: str = "NORMAL"
    business_reason: str = ""
    required_date: date | None = None
    source_channel: SourceChannel = SourceChannel.PROCUREMENT_DESKTOP
    source_reference_id: str | None = None
    lines: list[RequisitionLine] = field(default_factory=list)
    approved_by_user_id: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, document_number: DocumentNumber, branch_id: str,
               requested_by_user_id: str, purchase_type: PurchaseType,
               **kwargs) -> "PurchaseRequisition":
        return cls(id=new_uuid(), document_number=str(document_number), branch_id=branch_id,
                   requested_by_user_id=requested_by_user_id, purchase_type=purchase_type,
                   **kwargs)

    def add_line(self, line: RequisitionLine) -> None:
        if self.status is not RequisitionStatus.DRAFT:
            raise InvalidPurchaseStateError("Solo se editan solicitudes en borrador")
        self.lines.append(line)

    def submit(self) -> None:
        if self.status is not RequisitionStatus.DRAFT:
            raise InvalidPurchaseStateError("Solo se envía una solicitud en borrador")
        if not self.lines:
            raise InvalidPurchaseStateError("La solicitud requiere al menos una línea")
        self.status = RequisitionStatus.PENDING_APPROVAL
        self.updated_at = _utcnow()

    def approve(self, approver_user_id: str) -> None:
        if self.status is not RequisitionStatus.PENDING_APPROVAL:
            raise InvalidPurchaseStateError("Solo se aprueba una solicitud pendiente")
        self.status = RequisitionStatus.APPROVED
        self.approved_by_user_id = approver_user_id
        self.updated_at = _utcnow()

    def reject(self, approver_user_id: str) -> None:
        if self.status is not RequisitionStatus.PENDING_APPROVAL:
            raise InvalidPurchaseStateError("Solo se rechaza una solicitud pendiente")
        self.status = RequisitionStatus.REJECTED
        self.approved_by_user_id = approver_user_id
        self.updated_at = _utcnow()

    def cancel(self) -> None:
        if self.status in (RequisitionStatus.CLOSED, RequisitionStatus.SOURCED):
            raise InvalidPurchaseStateError("No se cancela una solicitud cerrada/abastecida")
        self.status = RequisitionStatus.CANCELLED
        self.updated_at = _utcnow()


# ── RFQ / quotes ──────────────────────────────────────────────────────────────
@dataclass(slots=True)
class SupplierQuoteLine:
    id: str
    product_id: str
    quantity: Decimal
    unit_price: Money

    @classmethod
    def create(cls, product_id: str, quantity, unit_price: Money) -> "SupplierQuoteLine":
        return cls(id=new_uuid(), product_id=product_id, quantity=_dec(quantity),
                   unit_price=unit_price)

    def line_total(self) -> Money:
        return Money(self.quantity * self.unit_price.amount, self.unit_price.currency_code)


@dataclass(slots=True)
class SupplierQuote:
    id: str
    rfq_id: str
    supplier_id: str
    currency_code: str = "MXN"
    lead_time_days: int = 0
    lines: list[SupplierQuoteLine] = field(default_factory=list)
    awarded: bool = False
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, rfq_id: str, supplier_id: str, **kwargs) -> "SupplierQuote":
        return cls(id=new_uuid(), rfq_id=rfq_id, supplier_id=supplier_id, **kwargs)

    def total(self) -> Money:
        total = sum((ln.line_total().amount for ln in self.lines), Decimal("0"))
        return Money(total.quantize(_TWO), self.currency_code)

    def award(self) -> None:
        self.awarded = True


@dataclass(slots=True)
class RequestForQuotation:
    id: str
    document_number: str
    supplier_ids: tuple[str, ...]
    response_deadline: date | None = None
    status: str = "DRAFT"   # DRAFT / SENT / CLOSED
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, document_number: DocumentNumber, supplier_ids: tuple[str, ...],
               **kwargs) -> "RequestForQuotation":
        if not supplier_ids:
            raise ProcurementDomainError("La RFQ requiere al menos un proveedor")
        return cls(id=new_uuid(), document_number=str(document_number),
                   supplier_ids=tuple(supplier_ids), **kwargs)

    def mark_sent(self) -> None:
        self.status = "SENT"


# ── purchase order ────────────────────────────────────────────────────────────
@dataclass(slots=True)
class PurchaseOrderLine:
    id: str
    product_id: str
    description: str
    ordered_quantity: Decimal
    unit_price: Money
    conversion_factor: Decimal = Decimal("1")
    received_quantity: Decimal = Decimal("0")
    accepted_quantity: Decimal = Decimal("0")
    rejected_quantity: Decimal = Decimal("0")
    invoiced_quantity: Decimal = Decimal("0")
    destination_warehouse_id: str | None = None

    @classmethod
    def create(cls, product_id: str, description: str, ordered_quantity, unit_price: Money,
               **kwargs) -> "PurchaseOrderLine":
        q = _dec(ordered_quantity)
        if q <= 0:
            raise ProcurementDomainError("La cantidad ordenada debe ser mayor a cero")
        return cls(id=new_uuid(), product_id=product_id, description=description,
                   ordered_quantity=q, unit_price=unit_price, **kwargs)

    def line_total(self) -> Money:
        return Money(self.ordered_quantity * self.unit_price.amount,
                     self.unit_price.currency_code)

    def pending_quantity(self) -> Decimal:
        return self.ordered_quantity - self.received_quantity


@dataclass(slots=True)
class PurchaseOrder:
    id: str
    document_number: str
    supplier_id: str
    branch_id: str
    warehouse_id: str
    currency_code: str = "MXN"
    purchase_type: PurchaseType = PurchaseType.INVENTORY
    status: PurchaseOrderStatus = PurchaseOrderStatus.DRAFT
    lines: list[PurchaseOrderLine] = field(default_factory=list)
    version: int = 1
    created_by_user_id: str | None = None
    approved_by_user_id: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, document_number: DocumentNumber, supplier_id: str, branch_id: str,
               warehouse_id: str, *, created_by_user_id: str,
               **kwargs) -> "PurchaseOrder":
        return cls(id=new_uuid(), document_number=str(document_number), supplier_id=supplier_id,
                   branch_id=branch_id, warehouse_id=warehouse_id,
                   created_by_user_id=created_by_user_id, **kwargs)

    def total(self) -> Money:
        total = sum((ln.line_total().amount for ln in self.lines), Decimal("0"))
        return Money(total.quantize(_TWO), self.currency_code)

    def submit(self) -> None:
        if self.status is not PurchaseOrderStatus.DRAFT:
            raise InvalidPurchaseStateError("Solo se envía a aprobación una orden en borrador")
        if not self.lines:
            raise InvalidPurchaseStateError("La orden requiere al menos una línea")
        self.status = PurchaseOrderStatus.PENDING_APPROVAL
        self.updated_at = _utcnow()

    def approve(self, approver_user_id: str) -> None:
        if self.status is not PurchaseOrderStatus.PENDING_APPROVAL:
            raise InvalidPurchaseStateError("Solo se aprueba una orden pendiente")
        self.status = PurchaseOrderStatus.APPROVED
        self.approved_by_user_id = approver_user_id
        self.updated_at = _utcnow()

    def send(self) -> None:
        if self.status is not PurchaseOrderStatus.APPROVED:
            raise InvalidPurchaseStateError("Solo se envía una orden aprobada")
        self.status = PurchaseOrderStatus.SENT
        self.updated_at = _utcnow()

    def acknowledge(self) -> None:
        if self.status is not PurchaseOrderStatus.SENT:
            raise InvalidPurchaseStateError("Solo se confirma una orden enviada")
        self.status = PurchaseOrderStatus.ACKNOWLEDGED
        self.updated_at = _utcnow()

    def register_receipt(self, quantities: dict[str, Decimal]) -> None:
        """Update received quantities per line; recompute the order status."""
        if self.status not in (PurchaseOrderStatus.SENT, PurchaseOrderStatus.ACKNOWLEDGED,
                               PurchaseOrderStatus.PARTIALLY_RECEIVED, PurchaseOrderStatus.APPROVED):
            raise InvalidPurchaseStateError(
                f"No se puede recibir sobre una orden {self.status.value}")
        for line in self.lines:
            if line.id in quantities:
                line.received_quantity += _dec(quantities[line.id])
        fully = all(ln.received_quantity >= ln.ordered_quantity for ln in self.lines)
        self.status = (PurchaseOrderStatus.RECEIVED if fully
                       else PurchaseOrderStatus.PARTIALLY_RECEIVED)
        self.updated_at = _utcnow()

    def create_new_version(self, reason: str) -> None:
        """A sensitive change after approval/send bumps the version (§36)."""
        if self.status in (PurchaseOrderStatus.DRAFT, PurchaseOrderStatus.PENDING_APPROVAL):
            return
        if not reason.strip():
            raise InvalidPurchaseStateError("El cambio de una orden aprobada requiere motivo")
        self.version += 1
        self.status = PurchaseOrderStatus.PENDING_APPROVAL  # re-approval
        self.updated_at = _utcnow()

    def cancel(self) -> None:
        if self.status in (PurchaseOrderStatus.RECEIVED, PurchaseOrderStatus.CLOSED,
                           PurchaseOrderStatus.INVOICED):
            raise InvalidPurchaseStateError("No se cancela una orden recibida/facturada")
        self.status = PurchaseOrderStatus.CANCELLED
        self.updated_at = _utcnow()


# ── goods receipt ─────────────────────────────────────────────────────────────
@dataclass(slots=True)
class ReceiptDiscrepancy:
    id: str
    discrepancy_type: DiscrepancyType
    expected: Decimal
    actual: Decimal
    reason: str = ""

    @classmethod
    def create(cls, discrepancy_type: DiscrepancyType, expected, actual,
               reason: str = "") -> "ReceiptDiscrepancy":
        return cls(id=new_uuid(), discrepancy_type=discrepancy_type,
                   expected=_dec(expected), actual=_dec(actual), reason=reason)

    def difference(self) -> Decimal:
        return self.actual - self.expected


@dataclass(slots=True)
class GoodsReceiptLine:
    id: str
    product_id: str
    ordered_quantity: Decimal
    received_quantity: Decimal
    accepted_quantity: Decimal
    rejected_quantity: Decimal = Decimal("0")
    lot: str | None = None
    expiration: date | None = None
    temperature: Decimal | None = None

    @classmethod
    def create(cls, product_id: str, ordered_quantity, received_quantity,
               accepted_quantity, **kwargs) -> "GoodsReceiptLine":
        received = _dec(received_quantity)
        accepted = _dec(accepted_quantity)
        if accepted > received:
            raise ProcurementDomainError("Lo aceptado no puede exceder lo recibido")
        rejected = received - accepted
        return cls(id=new_uuid(), product_id=product_id, ordered_quantity=_dec(ordered_quantity),
                   received_quantity=received, accepted_quantity=accepted,
                   rejected_quantity=rejected, **kwargs)

    def inventory_quantity(self) -> Decimal:
        """Only accepted quantity enters available inventory (§38, §50)."""
        return self.accepted_quantity


@dataclass(slots=True)
class GoodsReceipt:
    id: str
    document_number: str
    supplier_id: str
    branch_id: str
    warehouse_id: str
    purchase_order_id: str | None = None
    direct_purchase_id: str | None = None
    status: str = "STARTED"   # STARTED / COMPLETED / REVERSED
    lines: list[GoodsReceiptLine] = field(default_factory=list)
    discrepancies: list[ReceiptDiscrepancy] = field(default_factory=list)
    received_by_user_id: str | None = None
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, document_number: DocumentNumber, supplier_id: str, branch_id: str,
               warehouse_id: str, *, received_by_user_id: str,
               purchase_order_id: str | None = None,
               direct_purchase_id: str | None = None) -> "GoodsReceipt":
        return cls(id=new_uuid(), document_number=str(document_number), supplier_id=supplier_id,
                   branch_id=branch_id, warehouse_id=warehouse_id,
                   received_by_user_id=received_by_user_id,
                   purchase_order_id=purchase_order_id, direct_purchase_id=direct_purchase_id)

    def add_line(self, line: GoodsReceiptLine) -> None:
        if self.status != "STARTED":
            raise InvalidPurchaseStateError("Solo se editan recepciones iniciadas")
        self.lines.append(line)

    def add_discrepancy(self, discrepancy: ReceiptDiscrepancy) -> None:
        self.discrepancies.append(discrepancy)

    def complete(self) -> None:
        if self.status != "STARTED":
            raise InvalidPurchaseStateError("Solo se completa una recepción iniciada")
        if not self.lines:
            raise InvalidPurchaseStateError("La recepción requiere al menos una línea")
        self.status = "COMPLETED"

    def reverse(self) -> None:
        if self.status != "COMPLETED":
            raise InvalidPurchaseStateError("Solo se revierte una recepción completada")
        self.status = "REVERSED"

    def total_accepted(self) -> Decimal:
        return sum((ln.accepted_quantity for ln in self.lines), Decimal("0"))


# ── supplier invoice ──────────────────────────────────────────────────────────
@dataclass(slots=True)
class SupplierInvoice:
    id: str
    document_number: str
    supplier_id: str
    invoice_number: str
    total: Money
    purchase_order_id: str | None = None
    direct_purchase_id: str | None = None
    receipt_ids: tuple[str, ...] = ()
    uuid_fiscal: str | None = None
    status: str = "CAPTURED"   # CAPTURED/PENDING_MATCH/MATCHED/WITH_DIFFERENCES/APPROVED/BLOCKED/POSTED/CANCELLED
    match_result: str | None = None
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, document_number: DocumentNumber, supplier_id: str, invoice_number: str,
               total: Money, **kwargs) -> "SupplierInvoice":
        if not invoice_number.strip():
            raise ProcurementDomainError("La factura requiere número")
        return cls(id=new_uuid(), document_number=str(document_number), supplier_id=supplier_id,
                   invoice_number=invoice_number.strip(), total=total, **kwargs)

    def record_match(self, result: str) -> None:
        self.match_result = result
        if result == "MATCHED":
            self.status = "MATCHED"
        else:
            self.status = "WITH_DIFFERENCES"

    def block(self) -> None:
        self.status = "BLOCKED"


@dataclass(slots=True)
class PurchaseAuthorization:
    """A hot-authorization record (§64): who authorized which exception and why."""

    id: str
    operation_id: str
    permission_code: str
    requested_by_user_id: str
    authorized_by_user_id: str
    reason: str
    amount: Money
    terminal_id: str | None = None
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, *, operation_id: str, permission_code: str, requested_by_user_id: str,
               authorized_by_user_id: str, reason: str, amount: Money,
               terminal_id: str | None = None) -> "PurchaseAuthorization":
        if not reason.strip():
            raise ProcurementDomainError("La autorización requiere un motivo")
        return cls(id=new_uuid(), operation_id=operation_id, permission_code=permission_code,
                   requested_by_user_id=requested_by_user_id,
                   authorized_by_user_id=authorized_by_user_id, reason=reason.strip(),
                   amount=amount, terminal_id=terminal_id)
