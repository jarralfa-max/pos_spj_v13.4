"""Display-ready DTOs for the direct-purchase UI (strings/decimals, color-free)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DirectPurchaseRowDTO:
    id: str
    document_number: str
    supplier_id: str
    branch_id: str
    status: str
    total: str
    currency_code: str
    payment_condition: str
    created_at: str


@dataclass(frozen=True)
class DirectPurchaseLineDTO:
    product_id: str
    description: str
    quantity: str
    unit_cost: str
    discount: str
    tax: str
    line_total: str
    purchase_unit: str = "PZA"
    inventory_unit: str = "PZA"
    conversion_factor: str = "1"


@dataclass(frozen=True)
class DirectPurchaseDetailDTO:
    id: str
    document_number: str
    supplier_id: str
    branch_id: str
    warehouse_id: str
    status: str
    mode: str
    payment_condition: str
    currency_code: str
    subtotal: str
    tax_total: str
    total: str
    authorization_reason: str = ""
    authorized_by_user_id: str | None = None
    created_by_user_id: str | None = None
    lines: list[DirectPurchaseLineDTO] = field(default_factory=list)
