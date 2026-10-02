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
    supplier_name: str = "—"


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
    net_weight: str | None = None
    pricing_basis: str = ""


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
    #: Nombres para mostrar: la pantalla nunca enseña un UUID (resueltos por el
    #: servicio de consulta, no por la pantalla).
    supplier_name: str = "—"
    branch_name: str = "—"
    warehouse_name: str = "—"
    #: Fuente de pago con que se confirmó (sólo compras de contado ya confirmadas).
    payment_source: str | None = None
    #: Surtido (§11) y, con recolección, la bodega de origen tal como se eligió.
    fulfillment_mode: str = ""
    origin_display: str = ""
