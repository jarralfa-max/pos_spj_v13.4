"""Ports: narrow read contracts Procurement depends on from other bounded
contexts (Products, Logistics). A use case or presenter type-hints against
these Protocols, never against the concrete service in the other context;
the concrete adapter is wired at the composition root
(``enterprise_routes.py`` / ``direct_purchase_routes.py``).

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
