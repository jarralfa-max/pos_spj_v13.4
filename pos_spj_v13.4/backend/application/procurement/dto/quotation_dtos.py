"""Display-ready DTOs for the Cotizaciones/Adjudicación UI (RFQ → supplier
quotes → comparison → award). Strings/decimals only, resolved names never
raw ids — the UI never touches raw sqlite rows."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RfqRowDTO:
    id: str
    document_number: str
    status: str
    requisition_id: str | None
    invited_count: int
    quoted_count: int
    awarded: bool
    created_at: str


@dataclass(frozen=True)
class RfqInvitationDTO:
    supplier_id: str
    supplier_name: str
    status: str
    has_quote: bool


@dataclass(frozen=True)
class RfqQuoteSummaryDTO:
    quote_id: str
    supplier_id: str
    supplier_name: str
    total: str
    currency_code: str
    lead_time_days: int
    line_count: int


@dataclass(frozen=True)
class RfqDetailDTO:
    id: str
    document_number: str
    status: str
    created_at: str
    requisition_id: str | None = None
    response_deadline: str | None = None
    awarded: bool = False
    invitations: list[RfqInvitationDTO] = field(default_factory=list)
    quotes: list[RfqQuoteSummaryDTO] = field(default_factory=list)


@dataclass(frozen=True)
class QuoteLineOptionDTO:
    """One requisition line a supplier may be asked to quote."""
    product_id: str
    quantity: str
    estimated_unit_cost: str | None
    purchase_nature: str


@dataclass(frozen=True)
class ComparisonRowDTO:
    """One (product, supplier) quoted price, ranked within its product group."""
    product_id: str
    quote_id: str
    quote_line_id: str
    supplier_id: str
    supplier_name: str
    quantity: str
    unit_price: str
    lead_time_days: int
    currency_code: str
    is_best: bool
