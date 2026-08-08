"""Display-ready DTOs for the enterprise procurement UI (requisitions, orders,
invoices, receipts, documental history). Strings/decimals only, no raw sqlite
rows or technical ids reach the UI — the read services resolve names before
building these."""

from __future__ import annotations

from dataclasses import dataclass, field


# ── requisitions ──────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class RequisitionLineDTO:
    id: str
    product_id: str
    quantity: str
    estimated_unit_cost: str | None
    purchase_nature: str


@dataclass(frozen=True)
class RequisitionRowDTO:
    id: str
    document_number: str
    branch_id: str
    branch_name: str
    requested_by_user_id: str
    purchase_type: str
    priority: str
    status: str
    created_at: str


@dataclass(frozen=True)
class RequisitionDetailDTO:
    id: str
    document_number: str
    branch_id: str
    requested_by_user_id: str
    purchase_type: str
    priority: str
    business_reason: str
    status: str
    source_channel: str
    created_at: str
    updated_at: str
    requested_by_name: str = "—"
    required_date: str | None = None
    source_reference_id: str | None = None
    approved_by_user_id: str | None = None
    operation_id: str | None = None
    lines: list[RequisitionLineDTO] = field(default_factory=list)
    related_documents: list[dict] = field(default_factory=list)
    timeline: list[dict] = field(default_factory=list)


# ── purchase orders ───────────────────────────────────────────────────────────
@dataclass(frozen=True)
class OrderLineDTO:
    product_id: str
    description: str
    ordered_quantity: str
    unit_price: str
    received_quantity: str
    accepted_quantity: str


@dataclass(frozen=True)
class OrderVersionDTO:
    version: int
    reason: str
    changed_by_user_id: str | None
    created_at: str


@dataclass(frozen=True)
class OrderRowDTO:
    id: str
    document_number: str
    supplier_id: str
    supplier_name: str
    branch_id: str
    status: str
    total: str
    version: int
    currency_code: str
    created_at: str


@dataclass(frozen=True)
class OrderDetailDTO:
    id: str
    document_number: str
    supplier_id: str
    branch_id: str
    warehouse_id: str
    currency_code: str
    purchase_type: str
    status: str
    total: str
    version: int
    created_at: str
    updated_at: str
    supplier_name: str = "—"
    created_by_user_id: str | None = None
    approved_by_user_id: str | None = None
    source_requisition_id: str | None = None
    source_rfq_id: str | None = None
    source_award_id: str | None = None
    operation_id: str | None = None
    lines: list[OrderLineDTO] = field(default_factory=list)
    versions: list[OrderVersionDTO] = field(default_factory=list)
    related_documents: list[dict] = field(default_factory=list)
    timeline: list[dict] = field(default_factory=list)


# ── supplier invoices ─────────────────────────────────────────────────────────
@dataclass(frozen=True)
class InvoiceLineDTO:
    id: str
    product_id: str
    invoiced_quantity: str
    unit_price: str
    tax: str
    purchase_order_line_id: str | None
    direct_purchase_line_id: str | None
    receipt_line_id: str | None


@dataclass(frozen=True)
class InvoiceMatchDTO:
    result: str
    released_by_user_id: str | None
    notes: str
    created_at: str


@dataclass(frozen=True)
class InvoiceRowDTO:
    id: str
    document_number: str
    supplier_id: str
    supplier_name: str
    invoice_number: str
    total: str
    currency_code: str
    status: str
    match_result: str | None
    purchase_order_id: str | None
    created_at: str


@dataclass(frozen=True)
class InvoiceDetailDTO:
    id: str
    document_number: str
    supplier_id: str
    invoice_number: str
    subtotal: str
    tax_total: str
    total: str
    currency_code: str
    status: str
    captured_by_user_id: str
    created_at: str
    supplier_name: str = "—"
    purchase_order_id: str | None = None
    direct_purchase_id: str | None = None
    match_result: str | None = None
    matched_by_user_id: str | None = None
    released_by_user_id: str | None = None
    operation_id: str | None = None
    lines: list[InvoiceLineDTO] = field(default_factory=list)
    matches: list[InvoiceMatchDTO] = field(default_factory=list)
    comparison: list[dict] = field(default_factory=list)


# ── goods receipts ────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class GoodsReceiptLineDTO:
    id: str
    product_id: str
    ordered_quantity: str
    received_quantity: str
    accepted_quantity: str
    rejected_quantity: str
    lot: str | None
    expiration: str | None
    temperature: str | None


@dataclass(frozen=True)
class ReceiptDiscrepancyDTO:
    discrepancy_type: str
    expected: str
    actual: str
    reason: str


@dataclass(frozen=True)
class ReceiptRowDTO:
    id: str
    document_number: str
    supplier_id: str
    supplier_name: str
    status: str
    created_at: str
    received: object
    accepted: object
    rejected: object
    differences: int


@dataclass(frozen=True)
class ReceiptDetailDTO:
    id: str
    document_number: str
    supplier_id: str
    branch_id: str
    warehouse_id: str
    status: str
    created_at: str
    purchase_order_id: str | None = None
    direct_purchase_id: str | None = None
    received_by_user_id: str | None = None
    operation_id: str | None = None
    lines: list[GoodsReceiptLineDTO] = field(default_factory=list)
    differences: list[ReceiptDiscrepancyDTO] = field(default_factory=list)
    invoices: list[dict] = field(default_factory=list)


# ── documental purchase history ───────────────────────────────────────────────
@dataclass(frozen=True)
class PurchaseHistoryRowDTO:
    document_number: str
    supplier_id: str
    supplier_name: str
    status: str
    created_at: str
    direct_purchase_id: str | None = None
    purchase_order_id: str | None = None
