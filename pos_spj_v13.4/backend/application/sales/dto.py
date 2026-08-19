"""Read-side DTOs for the Sales/POS application layer — flat, frozen
projections a caller (UI/API) can use without touching domain entities
directly. Mirrors the flatter style seen in
backend/application/cash_register/shift_query_service.py::CashShiftRow
(rather than customers' CustomerProfile, which embeds the entity itself) —
appropriate here since Sale/SaleLine's Decimal/enum-typed fields are already
exactly what a caller needs, just flattened out of the aggregate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Mapping

from backend.domain.sales.entities import Sale, SaleInvoiceRequest, SaleLine
from backend.domain.sales.value_objects.sale_payment import SalePayment
from backend.domain.sales.value_objects.sale_return import SaleReturn


@dataclass(frozen=True, slots=True)
class SaleLineDTO:
    id: str
    product_id: str
    product_snapshot: Mapping[str, Any]
    quantity: Decimal
    quantity_unit: str
    unit_price: Decimal
    discount_total: Decimal
    tax_total: Decimal
    line_total: Decimal
    weight_source: str | None
    lot_reference: str | None

    @classmethod
    def from_entity(cls, line: SaleLine) -> "SaleLineDTO":
        return cls(
            id=line.id, product_id=line.product_id,
            product_snapshot=dict(line.product_snapshot),
            quantity=line.quantity.value, quantity_unit=line.quantity.unit,
            unit_price=line.unit_price, discount_total=line.discount_total,
            tax_total=line.tax_total, line_total=line.line_total,
            weight_source=line.weight_source, lot_reference=line.lot_reference,
        )


@dataclass(frozen=True, slots=True)
class SalePaymentDTO:
    id: str
    method: str
    amount: Decimal
    reference: str | None
    captured_by_user_id: str
    captured_at: str

    @classmethod
    def from_entity(cls, payment: SalePayment) -> "SalePaymentDTO":
        return cls(
            id=payment.id, method=payment.method.value, amount=payment.amount,
            reference=payment.reference, captured_by_user_id=payment.captured_by_user_id,
            captured_at=payment.captured_at,
        )


@dataclass(frozen=True, slots=True)
class SaleReturnDTO:
    id: str
    line_id: str
    quantity: Decimal
    amount: Decimal
    reason: str
    requested_by_user_id: str
    authorized_by_user_id: str
    created_at: str

    @classmethod
    def from_entity(cls, sale_return: SaleReturn) -> "SaleReturnDTO":
        return cls(
            id=sale_return.id, line_id=sale_return.line_id, quantity=sale_return.quantity,
            amount=sale_return.amount, reason=sale_return.reason,
            requested_by_user_id=sale_return.requested_by_user_id,
            authorized_by_user_id=sale_return.authorized_by_user_id,
            created_at=sale_return.created_at,
        )


@dataclass(frozen=True, slots=True)
class SaleDTO:
    id: str
    branch_id: str
    cashier_user_id: str
    operation_id: str
    status: str
    sale_number: str | None
    workstation_id: str | None
    customer_id: str | None
    channel: str
    currency_code: str
    lines: tuple[SaleLineDTO, ...] = field(default_factory=tuple)
    payments: tuple[SalePaymentDTO, ...] = field(default_factory=tuple)
    total_paid: Decimal = Decimal("0")
    is_mixed_payment: bool = False
    returns: tuple[SaleReturnDTO, ...] = field(default_factory=tuple)
    reversed_at: str | None = None
    invoice_requests: tuple[SaleInvoiceRequestDTO, ...] = field(default_factory=tuple)
    gross_subtotal: Decimal = Decimal("0")
    discount_total: Decimal = Decimal("0")
    promotion_total: Decimal = Decimal("0")
    coupon_total: Decimal = Decimal("0")
    loyalty_total: Decimal = Decimal("0")
    tax_total: Decimal = Decimal("0")
    rounding_adjustment: Decimal = Decimal("0")
    total: Decimal = Decimal("0")
    created_at: str = ""
    suspended_at: str | None = None
    completed_at: str | None = None
    cancelled_at: str | None = None
    version: int = 1

    @classmethod
    def from_entity(cls, sale: Sale) -> "SaleDTO":
        return cls(
            id=sale.id, branch_id=sale.branch_id, cashier_user_id=sale.cashier_user_id,
            operation_id=sale.operation_id, status=sale.status.value,
            sale_number=sale.sale_number, workstation_id=sale.workstation_id,
            customer_id=sale.customer_id, channel=sale.channel,
            currency_code=sale.currency_code,
            lines=tuple(SaleLineDTO.from_entity(line) for line in sale.lines),
            payments=tuple(SalePaymentDTO.from_entity(payment) for payment in sale.payments),
            total_paid=sale.total_paid, is_mixed_payment=sale.is_mixed_payment,
            returns=tuple(SaleReturnDTO.from_entity(r) for r in sale.returns),
            reversed_at=sale.reversed_at,
            invoice_requests=tuple(
                SaleInvoiceRequestDTO.from_entity(i) for i in sale.invoice_requests),
            gross_subtotal=sale.totals.gross_subtotal,
            discount_total=sale.totals.discount_total,
            promotion_total=sale.totals.promotion_total,
            coupon_total=sale.totals.coupon_total,
            loyalty_total=sale.totals.loyalty_total,
            tax_total=sale.totals.tax_total,
            rounding_adjustment=sale.totals.rounding_adjustment,
            total=sale.totals.total,
            created_at=sale.created_at, suspended_at=sale.suspended_at,
            completed_at=sale.completed_at, cancelled_at=sale.cancelled_at,
            version=sale.version,
        )


@dataclass(frozen=True, slots=True)
class SaleBenefitEvaluationDTO:
    """§24's `SaleBenefitEvaluationDTO` — one composed breakdown across the
    bounded contexts that decide what reduces a sale's total: descuento
    comercial (Sales' own, always real), promoción/cupón/vale (no owning
    bounded context exists in this repo yet — always 0, see `warnings`),
    puntos (real, via SalesLoyaltyClient when a customer is assigned),
    autorización manual (real, from SaleDiscountPolicy).
    """

    sale_id: str
    commercial_discount: Decimal
    requires_manual_authorization: bool
    promotion_discount: Decimal = Decimal("0")
    coupon_discount: Decimal = Decimal("0")
    voucher_amount: Decimal = Decimal("0")
    loyalty_points_available: int = 0
    loyalty_max_redemption_value: Decimal = Decimal("0")
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class CustomerDisplayLineDTO:
    name: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal


@dataclass(frozen=True, slots=True)
class CustomerDisplayStateDTO:
    """POS-12/§50: what a customer-facing second screen should render right
    now. Master prompt §6/§50: Sales only PUBLISHES state for this device,
    it never controls it — no consumer/hardware for a real customer display
    exists anywhere in this repository yet (confirmed by research), so this
    is a pure read projection over `Sale`'s own already-real state, not a
    push mechanism to a device that does not exist. Every cart/lifecycle
    mutation already enqueues to `sales_outbox` with this exact vocabulary
    (`SaleEvents.LINE_ADDED` etc.) — a future display consumer polls this
    query or subscribes to that same outbox stream; neither needed new
    plumbing built here."""

    sale_id: str
    screen: str
    customer_name: str | None
    lines: tuple[CustomerDisplayLineDTO, ...]
    subtotal: Decimal
    discount_total: Decimal
    total: Decimal
    message: str = ""


@dataclass(frozen=True, slots=True)
class DeviceHealthDTO:
    """POS-12/§49-51: what the cashier bar's device-status strip can
    honestly report. Reads `hardware_config` directly — the one real,
    canonical source every hardware driver in this repository already reads
    from (`HardwareService`, `PrinterService`). `configured=False` for a
    device type means exactly that: no row, or an inactive/empty row — not
    a live connectivity ping this repository has no way to perform for a
    passive serial/USB device without attempting an actual I/O operation
    against it, which a status-strip query has no business doing."""

    device_type: str
    configured: bool
    enabled: bool
    detail: str = ""


@dataclass(frozen=True, slots=True)
class SaleReceiptLineDTO:
    name: str
    unit: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal


@dataclass(frozen=True, slots=True)
class SaleReceiptDataDTO:
    """POS-17/§46: "Ventas proporciona SaleReceiptDataDTO... Document Output
    administra plantilla/render/impresión" — this is that DTO. Decimal
    end-to-end; `SalesReceiptClient` converts to the legacy float-typed
    `ticket_data` dict `PrinterService.print_ticket()` expects only at its
    own boundary, never here."""

    sale_id: str
    folio: str
    created_at: str
    cajero_nombre: str
    cliente_nombre: str
    lines: tuple[SaleReceiptLineDTO, ...]
    subtotal: Decimal
    discount_total: Decimal
    tax_total: Decimal
    total: Decimal
    forma_pago: str
    efectivo_recibido: Decimal
    cambio: Decimal


@dataclass(frozen=True, slots=True)
class PrintJobStatusDTO:
    """POS-17: a real, queryable row from `print_job_log` (`core/services/
    printer_service.py::PrintQueue._log_job_to_db`) — not a guess at what
    `PrinterService`'s async worker did with a job after `print_ticket()`
    returned a bare job id."""

    job_id: str
    status: str
    folio: str
    retries: int
    error_msg: str
    finished_at: str | None


@dataclass(frozen=True, slots=True)
class SaleInvoiceRequestDTO:
    id: str
    tax_identifier: str
    legal_name: str
    cfdi_use: str
    status: str
    requested_by_user_id: str
    uuid_fiscal: str | None
    error_message: str | None
    requested_at: str
    updated_at: str

    @classmethod
    def from_entity(cls, invoice: SaleInvoiceRequest) -> "SaleInvoiceRequestDTO":
        return cls(
            id=invoice.id, tax_identifier=invoice.tax_identifier, legal_name=invoice.legal_name,
            cfdi_use=invoice.cfdi_use, status=invoice.status.value,
            requested_by_user_id=invoice.requested_by_user_id, uuid_fiscal=invoice.uuid_fiscal,
            error_message=invoice.error_message, requested_at=invoice.requested_at,
            updated_at=invoice.updated_at,
        )


@dataclass(frozen=True, slots=True)
class ProductCatalogEntryDTO:
    """§14's exact output field list for `ProductCatalogQueryService` — what
    the left catalog panel (§16, product cards) is allowed to render from."""

    product_id: str
    name: str
    sku: str
    barcode: str | None
    unit: str
    effective_price: Decimal
    stock_state: str
    available_quantity: Decimal
    image_reference: str | None
    sellable: bool
    warnings: tuple[str, ...] = field(default_factory=tuple)
