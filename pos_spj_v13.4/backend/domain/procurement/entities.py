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
    PurchaseNature,
    PurchaseReturnReason,
    PurchaseReturnStatus,
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


#: Base de precio de Productos que cobra el PESO real (PriceBasis.PER_KILOGRAM).
WEIGHT_PRICING_BASIS = "PER_KILOGRAM"


# ── direct purchase ───────────────────────────────────────────────────────────
@dataclass(slots=True)
class DirectPurchaseLine:
    id: str
    product_id: str
    description: str
    quantity: Decimal
    unit_cost: Money
    purchase_nature: PurchaseNature = PurchaseNature.INVENTORY
    purchase_unit: str = "PZA"
    inventory_unit: str = "PZA"
    conversion_factor: Decimal = Decimal("1")
    discount: Money = None  # type: ignore[assignment]
    tax: Money = None  # type: ignore[assignment]
    destination_branch_id: str | None = None
    destination_warehouse_id: str | None = None
    # Peso variable (§17), decidido por Productos: «5 cajas, 127.850 kg reales a
    # $95/kg». `pricing_basis` = PER_KILOGRAM cobra el PESO REAL, no la cantidad;
    # `inventory_by_weight` = la unidad de inventario es de peso, así que entra
    # el peso real y no el nominal de la presentación.
    net_weight: Decimal | None = None
    pricing_basis: str = ""
    inventory_by_weight: bool = False

    @classmethod
    def create(cls, product_id: str, description: str, quantity, unit_cost: Money,
               **kwargs) -> "DirectPurchaseLine":
        q = _dec(quantity)
        if q <= 0:
            raise ProcurementDomainError("La cantidad debe ser mayor a cero")
        weight = kwargs.get("net_weight")
        if weight not in (None, ""):
            kwargs["net_weight"] = _dec(weight)
            if kwargs["net_weight"] <= 0:
                raise ProcurementDomainError("El peso real debe ser mayor a cero")
        elif kwargs.get("pricing_basis") == WEIGHT_PRICING_BASIS or kwargs.get(
                "inventory_by_weight"):
            raise ProcurementDomainError(
                "El producto se maneja por peso variable: captura el peso real")
        # Decisión del usuario (2026-09-18): el costo debe ser MAYOR a cero.
        # Aceptaba cero, y una línea en cero —casi siempre un precio olvidado—
        # entraba al inventario a costo 0 y hundía el costo promedio sin que
        # nadie se enterara. La mercancía regalada se captura con su costo real
        # y el descuento aparte.
        if not unit_cost.is_positive():
            raise ProcurementDomainError("El costo unitario debe ser mayor a cero")
        return cls(id=new_uuid(), product_id=product_id, description=description,
                   quantity=q, unit_cost=unit_cost, **kwargs)

    def __post_init__(self) -> None:
        self.quantity = _dec(self.quantity)
        self.conversion_factor = _dec(self.conversion_factor)
        if self.discount is None:
            self.discount = Money.zero(self.unit_cost.currency_code)
        if self.tax is None:
            self.tax = Money.zero(self.unit_cost.currency_code)

    def priced_by_weight(self) -> bool:
        return self.pricing_basis == WEIGHT_PRICING_BASIS

    def billable_quantity(self) -> Decimal:
        """Lo que se cobra: el peso real si el precio es por kg; si no, la
        cantidad en la unidad de compra."""
        return self.net_weight if self.priced_by_weight() and self.net_weight else self.quantity

    def inventory_quantity(self) -> Decimal:
        if self.inventory_by_weight and self.net_weight:
            return self.net_weight
        return self.quantity * self.conversion_factor

    def inventory_unit_cost(self) -> Decimal:
        """Costo por unidad de INVENTARIO: importe de la línea entre lo que entra."""
        quantity = self.inventory_quantity()
        if quantity <= 0:
            return Decimal("0")
        return self.line_subtotal().amount / quantity

    def line_subtotal(self) -> Money:
        return Money(self.billable_quantity() * self.unit_cost.amount,
                     self.unit_cost.currency_code)

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
    source_requisition_id: str | None = None
    # §11: cómo llega la mercancía, aparte de cómo se paga. Recolección en
    # proveedor lleva la bodega de origen (id + foto del domicilio, §13).
    fulfillment_mode: str = ""
    origin_supplier_address_id: str | None = None
    origin_address_snapshot: str | None = None

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
    purchase_nature: PurchaseNature = PurchaseNature.INVENTORY
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

    def can_be_sourced(self) -> bool:
        """Aprobada, o ya surtida en parte: una adjudicación dividida genera una
        orden por proveedor, y la segunda llega con la solicitud PARCIAL."""
        return self.status in (RequisitionStatus.APPROVED,
                               RequisitionStatus.PARTIALLY_SOURCED)

    def mark_sourced(self, *, partial: bool = False) -> None:
        if not self.can_be_sourced():
            raise InvalidPurchaseStateError("Solo se abastece una solicitud aprobada")
        self.status = (RequisitionStatus.PARTIALLY_SOURCED if partial
                       else RequisitionStatus.SOURCED)
        self.updated_at = _utcnow()


# ── RFQ / quotes ──────────────────────────────────────────────────────────────
@dataclass(slots=True)
class SupplierQuoteLine:
    id: str
    product_id: str
    quantity: Decimal
    unit_price: Money
    purchase_nature: PurchaseNature = PurchaseNature.INVENTORY
    tax: Money | None = None
    discount: Money | None = None

    @classmethod
    def create(cls, product_id: str, quantity, unit_price: Money,
               **kwargs) -> "SupplierQuoteLine":
        return cls(id=new_uuid(), product_id=product_id, quantity=_dec(quantity),
                   unit_price=unit_price, **kwargs)

    def line_total(self) -> Money:
        tax = self.tax.amount if self.tax else Decimal("0")
        discount = self.discount.amount if self.discount else Decimal("0")
        return Money(self.quantity * self.unit_price.amount - discount + tax,
                     self.unit_price.currency_code)


@dataclass(slots=True)
class RfqSupplierInvitation:
    id: str
    rfq_id: str
    supplier_id: str
    status: str = "INVITED"
    invited_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, rfq_id: str, supplier_id: str) -> "RfqSupplierInvitation":
        if not supplier_id:
            raise ProcurementDomainError("La invitación requiere proveedor")
        return cls(id=new_uuid(), rfq_id=rfq_id, supplier_id=supplier_id)


@dataclass(slots=True)
class SupplierQuote:
    id: str
    rfq_id: str
    supplier_id: str
    currency_code: str = "MXN"
    lead_time_days: int = 0
    lines: list[SupplierQuoteLine] = field(default_factory=list)
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, rfq_id: str, supplier_id: str, **kwargs) -> "SupplierQuote":
        return cls(id=new_uuid(), rfq_id=rfq_id, supplier_id=supplier_id, **kwargs)

    def total(self) -> Money:
        total = sum((ln.line_total().amount for ln in self.lines), Decimal("0"))
        return Money(total.quantize(_TWO), self.currency_code)

@dataclass(slots=True)
class RequestForQuotation:
    id: str
    document_number: str
    invitations: list[RfqSupplierInvitation] = field(default_factory=list)
    requisition_id: str | None = None
    response_deadline: date | None = None
    status: str = "DRAFT"   # DRAFT / SENT / CLOSED
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, document_number: DocumentNumber, supplier_ids: tuple[str, ...],
               **kwargs) -> "RequestForQuotation":
        if not supplier_ids:
            raise ProcurementDomainError("La RFQ requiere al menos un proveedor")
        rfq = cls(id=new_uuid(), document_number=str(document_number), **kwargs)
        rfq.invitations = [RfqSupplierInvitation.create(rfq.id, supplier_id)
                           for supplier_id in dict.fromkeys(supplier_ids)]
        return rfq

    @property
    def supplier_ids(self) -> tuple[str, ...]:
        return tuple(inv.supplier_id for inv in self.invitations)

    def close(self) -> None:
        """La ronda de cotización terminó (adjudicada): ya no se capturan
        cotizaciones. Antes la RFQ se quedaba en «Borrador» para siempre."""
        self.status = "CLOSED"

    def mark_sent(self) -> None:
        self.status = "SENT"


@dataclass(slots=True)
class PurchaseAwardLine:
    id: str
    award_id: str
    quote_line_id: str
    supplier_id: str
    awarded_quantity: Decimal
    justification: str

    @classmethod
    def create(cls, award_id: str, quote_line_id: str, supplier_id: str,
               awarded_quantity, justification: str) -> "PurchaseAwardLine":
        quantity = _dec(awarded_quantity)
        if quantity <= 0 or not justification.strip():
            raise ProcurementDomainError(
                "La adjudicación requiere cantidad y justificación")
        return cls(new_uuid(), award_id, quote_line_id, supplier_id, quantity,
                   justification.strip())


@dataclass(frozen=True, slots=True)
class QuoteComparisonEntry:
    quote_id: str
    quote_line_id: str
    supplier_id: str
    product_id: str
    unit_price: Money
    lead_time_days: int


@dataclass(slots=True)
class QuoteComparison:
    id: str
    rfq_id: str
    entries: list[QuoteComparisonEntry]
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def build(cls, rfq_id: str, quotes: list[SupplierQuote]) -> "QuoteComparison":
        entries = [QuoteComparisonEntry(
            quote_id=quote.id, quote_line_id=line.id, supplier_id=quote.supplier_id,
            product_id=line.product_id, unit_price=line.unit_price,
            lead_time_days=quote.lead_time_days)
            for quote in quotes for line in quote.lines]
        return cls(new_uuid(), rfq_id, entries)

    def ranked_for_product(self, product_id: str) -> list[QuoteComparisonEntry]:
        return sorted(
            (entry for entry in self.entries if entry.product_id == product_id),
            key=lambda entry: (entry.unit_price.amount, entry.lead_time_days,
                               entry.supplier_id))


@dataclass(slots=True)
class PurchaseAward:
    id: str
    rfq_id: str
    approved_by_user_id: str
    lines: list[PurchaseAwardLine] = field(default_factory=list)
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, rfq_id: str, approved_by_user_id: str) -> "PurchaseAward":
        return cls(new_uuid(), rfq_id, approved_by_user_id)


# ── purchase order ────────────────────────────────────────────────────────────
@dataclass(slots=True)
class PurchaseOrderLine:
    id: str
    product_id: str
    description: str
    ordered_quantity: Decimal
    unit_price: Money
    purchase_nature: PurchaseNature = PurchaseNature.INVENTORY
    conversion_factor: Decimal = Decimal("1")
    received_quantity: Decimal = Decimal("0")
    accepted_quantity: Decimal = Decimal("0")
    rejected_quantity: Decimal = Decimal("0")
    invoiced_quantity: Decimal = Decimal("0")
    destination_warehouse_id: str | None = None
    # Unidad en que se ordena y unidad de inventario, ambas de Productos; el
    # factor convierte la primera en la segunda. Vacías = unidad base.
    purchase_unit: str = ""
    inventory_unit: str = ""
    # Importes de la línea (misma moneda que el precio) y lo que el proveedor
    # CONFIRMÓ surtir (None = aún sin confirmar).
    discount: Decimal = Decimal("0")
    tax: Decimal = Decimal("0")
    confirmed_quantity: Decimal | None = None
    # Peso variable (§16-17): «5 cajas a $95/kg». El precio es POR KG; el
    # importe de la orden se ESTIMA con el peso nominal de la presentación y la
    # recepción (peso real) y la factura (kg) deciden lo que se paga.
    pricing_basis: str = ""
    inventory_by_weight: bool = False

    @classmethod
    def create(cls, product_id: str, description: str, ordered_quantity, unit_price: Money,
               **kwargs) -> "PurchaseOrderLine":
        q = _dec(ordered_quantity)
        if q <= 0:
            raise ProcurementDomainError("La cantidad ordenada debe ser mayor a cero")
        # Misma regla que la compra rápida. Aquí ni siquiera se rechazaba un
        # precio NEGATIVO; la recepción de la orden lo llevaría al costo.
        if not unit_price.is_positive():
            raise ProcurementDomainError("El precio unitario debe ser mayor a cero")
        discount = _dec(kwargs.pop("discount", None) or "0")
        tax = _dec(kwargs.pop("tax", None) or "0")
        if discount < 0 or tax < 0:
            raise ProcurementDomainError("El descuento y el impuesto no pueden ser negativos")
        estimate = q * unit_price.amount
        if kwargs.get("pricing_basis") == WEIGHT_PRICING_BASIS:
            estimate *= _dec(kwargs.get("conversion_factor") or "1")
        if discount > estimate:
            raise ProcurementDomainError("El descuento no puede superar el importe de la línea")
        return cls(id=new_uuid(), product_id=product_id, description=description,
                   ordered_quantity=q, unit_price=unit_price, discount=discount, tax=tax,
                   **kwargs)

    def priced_by_weight(self) -> bool:
        return self.pricing_basis == WEIGHT_PRICING_BASIS

    def billable_quantity(self) -> Decimal:
        """Lo que se pacta cobrar: kg nominales si el precio es por kg."""
        if self.priced_by_weight():
            return self.ordered_quantity * (self.conversion_factor or Decimal("1"))
        return self.ordered_quantity

    def line_subtotal(self) -> Money:
        return Money(self.billable_quantity() * self.unit_price.amount - self.discount,
                     self.unit_price.currency_code)

    def line_total(self) -> Money:
        return Money(self.line_subtotal().amount + self.tax, self.unit_price.currency_code)

    def inventory_quantity(self) -> Decimal:
        return self.ordered_quantity * (self.conversion_factor or Decimal("1"))

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
    source_requisition_id: str | None = None
    source_rfq_id: str | None = None
    source_award_id: str | None = None
    payment_terms: str | None = None
    # Encabezado enterprise (§23).
    exchange_rate: Decimal | None = None
    required_date: str | None = None
    promised_date: str | None = None
    delivery_method: str | None = None
    delivery_address: str | None = None
    cost_center: str | None = None
    project_reference: str | None = None
    contract_reference: str | None = None
    notes: str | None = None
    # Confirmación del proveedor (§24): «enviada» NO es «aceptada».
    supplier_reference: str | None = None
    confirmed_at: str | None = None
    confirmed_delivery_date: str | None = None
    confirmation_exceptions: str | None = None
    confirmation_comments: str | None = None
    confirmed_by_user_id: str | None = None
    # §13: recolección en proveedor — de qué bodega/punto sale (id + foto JSON).
    origin_supplier_address_id: str | None = None
    origin_address_snapshot: str | None = None

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

    def acknowledge(self, *, supplier_reference: str = "",
                    confirmed_delivery_date: str | None = None,
                    confirmed_quantities: dict[str, Decimal] | None = None,
                    comments: str = "", confirmed_by_user_id: str | None = None,
                    line_labels: dict[str, str] | None = None) -> list[str]:
        """El proveedor CONFIRMA la orden enviada (§24).

        Registra su referencia, la fecha de entrega que promete y la cantidad que
        confirma por línea (la ordenada si no dice otra). Devuelve las
        EXCEPCIONES — diferencias contra lo pedido — que también quedan guardadas:
        confirmar menos (o más) de lo ordenado, o prometer después de la fecha
        requerida."""
        if self.status is not PurchaseOrderStatus.SENT:
            raise InvalidPurchaseStateError("Solo se confirma una orden enviada")
        confirmed_quantities = confirmed_quantities or {}
        labels = line_labels or {}
        exceptions: list[str] = []
        for line in self.lines:
            quantity = _dec(confirmed_quantities.get(line.id, line.ordered_quantity))
            if quantity < 0:
                raise ProcurementDomainError("La cantidad confirmada no puede ser negativa")
            line.confirmed_quantity = quantity
            if quantity != line.ordered_quantity:
                name = labels.get(line.id) or line.description or "Producto"
                exceptions.append(f"{name}: confirma {quantity.normalize():f} de "
                                  f"{line.ordered_quantity.normalize():f}")
        if (confirmed_delivery_date and self.required_date
                and str(confirmed_delivery_date) > str(self.required_date)):
            exceptions.append(f"Entrega prometida {confirmed_delivery_date}, posterior a la "
                              f"requerida {self.required_date}")
        self.supplier_reference = (supplier_reference or "").strip() or None
        self.confirmed_delivery_date = confirmed_delivery_date or None
        self.confirmation_comments = (comments or "").strip() or None
        self.confirmation_exceptions = "\n".join(exceptions) or None
        self.confirmed_by_user_id = confirmed_by_user_id
        self.confirmed_at = _utcnow()
        if confirmed_delivery_date:
            self.promised_date = str(confirmed_delivery_date)
        self.status = PurchaseOrderStatus.ACKNOWLEDGED
        self.updated_at = _utcnow()
        return exceptions

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

    def unregister_receipt(self, quantities: dict[str, Decimal]) -> None:
        """Symmetric undo of ``register_receipt`` for a reversed goods receipt
        (§41: compensating, never negative). Clamps at zero per line — a
        reversal never removes more than a line ever received."""
        if self.status not in (PurchaseOrderStatus.RECEIVED,
                               PurchaseOrderStatus.PARTIALLY_RECEIVED):
            raise InvalidPurchaseStateError(
                f"No hay recepción que reversar en una orden {self.status.value}")
        for line in self.lines:
            if line.id in quantities:
                line.received_quantity = max(
                    Decimal("0"), line.received_quantity - _dec(quantities[line.id]))
        if all(ln.received_quantity <= 0 for ln in self.lines):
            self.status = PurchaseOrderStatus.SENT
        else:
            self.status = PurchaseOrderStatus.PARTIALLY_RECEIVED
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
    # §26: peso real y piezas cuando el producto se maneja por peso variable
    # ("3 canales, 814.700 kg").
    net_weight: Decimal | None = None
    piece_count: int | None = None
    purchase_order_line_id: str | None = None

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
    # Compra en origen: el embarque de Logística del que salió esta recepción.
    shipment_id: str | None = None

    @classmethod
    def create(cls, document_number: DocumentNumber, supplier_id: str, branch_id: str,
               warehouse_id: str, *, received_by_user_id: str,
               purchase_order_id: str | None = None,
               direct_purchase_id: str | None = None,
               shipment_id: str | None = None) -> "GoodsReceipt":
        return cls(id=new_uuid(), document_number=str(document_number), supplier_id=supplier_id,
                   branch_id=branch_id, warehouse_id=warehouse_id,
                   received_by_user_id=received_by_user_id,
                   purchase_order_id=purchase_order_id, direct_purchase_id=direct_purchase_id,
                   shipment_id=shipment_id)

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


# ── purchase return (devolución a proveedor) ───────────────────────────────────
@dataclass(slots=True)
class PurchaseReturnLine:
    id: str
    product_id: str
    quantity: Decimal
    unit_cost: Money | None = None
    lot: str | None = None
    goods_receipt_line_id: str | None = None
    notes: str = ""

    @classmethod
    def create(cls, product_id: str, quantity, **kwargs) -> "PurchaseReturnLine":
        q = _dec(quantity)
        if q <= 0:
            raise ProcurementDomainError("La cantidad a devolver debe ser mayor a cero")
        return cls(id=new_uuid(), product_id=product_id, quantity=q, **kwargs)


@dataclass(slots=True)
class PurchaseReturn:
    """A return of previously received goods to the supplier.

    References — but never deletes — the original ``GoodsReceipt``/``PurchaseOrder``.
    Deliberately simple lifecycle (DRAFT → CONFIRMED, or DRAFT → CANCELLED): this
    is not a multi-stage approval workflow like ``PurchaseRequisition``.
    """

    id: str
    document_number: str
    supplier_id: str
    branch_id: str
    warehouse_id: str
    reason: PurchaseReturnReason
    status: PurchaseReturnStatus = PurchaseReturnStatus.DRAFT
    goods_receipt_id: str | None = None
    purchase_order_id: str | None = None
    lines: list[PurchaseReturnLine] = field(default_factory=list)
    created_by_user_id: str | None = None
    created_at: str = field(default_factory=_utcnow)
    confirmed_at: str | None = None

    @classmethod
    def create(cls, document_number: DocumentNumber, supplier_id: str, branch_id: str,
               warehouse_id: str, reason: PurchaseReturnReason, *,
               created_by_user_id: str, goods_receipt_id: str | None = None,
               purchase_order_id: str | None = None) -> "PurchaseReturn":
        return cls(id=new_uuid(), document_number=str(document_number), supplier_id=supplier_id,
                   branch_id=branch_id, warehouse_id=warehouse_id, reason=reason,
                   created_by_user_id=created_by_user_id, goods_receipt_id=goods_receipt_id,
                   purchase_order_id=purchase_order_id)

    def _assert_draft(self) -> None:
        if self.status is not PurchaseReturnStatus.DRAFT:
            raise InvalidPurchaseStateError(
                f"No se puede modificar una devolución {self.status.value}")

    def add_line(self, line: PurchaseReturnLine) -> None:
        self._assert_draft()
        self.lines.append(line)

    def total_quantity(self) -> Decimal:
        return sum((ln.quantity for ln in self.lines), Decimal("0"))

    def confirm(self) -> None:
        self._assert_draft()
        if not self.lines:
            raise InvalidPurchaseStateError("La devolución requiere al menos una línea")
        self.status = PurchaseReturnStatus.CONFIRMED
        self.confirmed_at = _utcnow()

    def cancel(self) -> None:
        self._assert_draft()
        self.status = PurchaseReturnStatus.CANCELLED


# ── supplier invoice ──────────────────────────────────────────────────────────
@dataclass(slots=True)
class SupplierInvoice:
    id: str
    document_number: str
    supplier_id: str
    invoice_number: str
    total: Money
    subtotal: Money | None = None
    tax_total: Money | None = None
    lines: list["SupplierInvoiceLine"] = field(default_factory=list)
    captured_by_user_id: str | None = None
    matched_by_user_id: str | None = None
    released_by_user_id: str | None = None
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
class SupplierInvoiceLine:
    id: str
    supplier_invoice_id: str
    product_id: str
    invoiced_quantity: Decimal
    unit_price: Money
    tax: Money
    purchase_nature: PurchaseNature = PurchaseNature.INVENTORY
    purchase_order_line_id: str | None = None
    direct_purchase_line_id: str | None = None
    receipt_line_id: str | None = None

    @classmethod
    def create(cls, supplier_invoice_id: str, product_id: str, invoiced_quantity,
               unit_price: Money, tax: Money, **kwargs) -> "SupplierInvoiceLine":
        quantity = _dec(invoiced_quantity)
        if quantity <= 0:
            raise ProcurementDomainError("La cantidad facturada debe ser mayor a cero")
        return cls(new_uuid(), supplier_invoice_id, product_id, quantity, unit_price,
                   tax, **kwargs)

    def subtotal(self) -> Money:
        return Money(self.invoiced_quantity * self.unit_price.amount,
                     self.unit_price.currency_code)

    def total(self) -> Money:
        return Money(self.subtotal().amount + self.tax.amount,
                     self.unit_price.currency_code)


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
