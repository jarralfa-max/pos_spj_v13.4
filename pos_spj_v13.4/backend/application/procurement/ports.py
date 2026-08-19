"""Ports: narrow read contracts Procurement depends on from other bounded
contexts (Products, Logistics, Suppliers, Finance, Inventory). A use case or
presenter type-hints against these Protocols, never against the concrete
service in the other context; the concrete adapter is wired at the
composition root (``enterprise_routes.py`` / ``direct_purchase_routes.py``).

Structural typing (``Protocol``): an existing service satisfies a port simply
by having the right method signature — no inheritance required. That is why
``WarehouseDirectoryQueryService`` (owned by Logistics) already satisfies
``BranchWarehouseContextPort`` unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ProcurementProductOption:
    product_id: str
    code: str
    name: str
    purchase_unit: str | None
    purchasable: bool


class ProcurementProductCatalogPort(Protocol):
    """Read-only access to the canonical product catalog (§11), scoped to
    products Compras may buy. Never reads the legacy ``productos`` table —
    see ``SearchPurchasableProductsQueryService``."""

    def search(self, query: str, *, branch_id: str | None = None,
               limit: int = 20) -> list[ProcurementProductOption]:
        ...

    def resolve(self, product_id: str) -> ProcurementProductOption | None:
        ...


class BranchWarehouseContextPort(Protocol):
    """Read-only lookup of the warehouses a branch may receive purchases
    into. Owned by Logistics (``WarehouseDirectoryQueryService``); Procurement
    only ever reads through this port, never the ``warehouses`` table itself."""

    def active_for_branch(self, branch_id: str) -> list[tuple[str, str]]:
        ...


@dataclass(frozen=True)
class SupplierProcurementProfile:
    supplier_id: str
    legal_name: str
    trade_name: str | None
    status: str
    purchasing_enabled: bool
    financially_blocked: bool
    risk_level: str | None
    rating_grade: str | None
    active_blocks: tuple[str, ...]


class SupplierProcurementProfilePort(Protocol):
    """Read-only commercial/eligibility profile of a supplier, owned by
    Suppliers. Satisfied by an adapter composing
    ``SupplierDetailQueryService.get_header()`` +
    ``SupplierDirectoryQueryService.get_eligibility()`` — Procurement never
    reads ``supplier_master``/``proveedores`` directly."""

    def profile(self, supplier_id: str) -> SupplierProcurementProfile | None:
        ...


@dataclass(frozen=True)
class SupplierFinancialStanding:
    supplier_id: str
    balance: str
    overdue: str
    open_documents: int


class ProcurementFinancePort(Protocol):
    """Read-only financial standing of a supplier (payable balance/overdue),
    owned by Finance. Satisfied structurally by
    ``SupplierFinancialSummaryQueryService`` — Procurement never reads the
    ``payables`` table directly."""

    def financial_standing(self, supplier_id: str) -> SupplierFinancialStanding:
        ...


@dataclass(frozen=True)
class InventoryReceiptStatus:
    goods_receipt_id: str
    status: str | None
    occurred_at: str | None


class InventoryReceiptStatusPort(Protocol):
    """Read-only posting status of a goods receipt into inventory, owned by
    Inventory. Satisfied structurally by ``ReceiptQueryService`` — Procurement
    never reads ``inventory_ledger`` directly."""

    def status_for_receipt(self, goods_receipt_id: str) -> InventoryReceiptStatus | None:
        ...
