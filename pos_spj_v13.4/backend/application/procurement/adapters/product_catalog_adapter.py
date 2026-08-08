"""ProcurementProductCatalogAdapter — implements ProcurementProductCatalogPort
over the canonical product master (§11's SearchPurchasableProductsQueryService).

Before this existed, direct-purchase and requisition/order line entry accepted
``product_id`` as free text with no lookup against any product store (a
"Código o ID de producto" field the buyer typed by hand) — a manual-ID-capture
gap. This adapter is what lets the UI replace that field with real
search-and-select against the canonical catalog.
"""

from __future__ import annotations

import sqlite3

from backend.application.procurement.ports import ProcurementProductOption
from backend.application.products.queries.product_selection_query_service import (
    SearchPurchasableProductsQueryService,
)


class ProcurementProductCatalogAdapter:
    def __init__(self, connection) -> None:
        self._connection = connection
        self._search_service = SearchPurchasableProductsQueryService(connection)

    def search(self, query: str, *, branch_id: str | None = None,
               limit: int = 20) -> list[ProcurementProductOption]:
        if not query or not query.strip():
            return []
        try:
            rows = self._search_service.search(
                query=query.strip(), branch_id=branch_id, limit=limit)
        except sqlite3.OperationalError:
            return []
        return [_to_option(row) for row in rows]

    def resolve(self, product_id: str) -> ProcurementProductOption | None:
        if not product_id:
            return None
        try:
            row = self._connection.execute(
                "SELECT id, code, name, base_unit_id, purchasable FROM products"
                " WHERE id=? AND lifecycle_status='ACTIVE'", (product_id,)).fetchone()
        except sqlite3.OperationalError:
            return None
        if row is None:
            return None
        return ProcurementProductOption(
            product_id=str(row[0]), code=str(row[1] or ""), name=str(row[2]),
            purchase_unit=row[3], purchasable=bool(row[4]))


def _to_option(dto) -> ProcurementProductOption:
    return ProcurementProductOption(
        product_id=dto.product_id, code=dto.code, name=dto.name,
        purchase_unit=dto.base_unit_id, purchasable=dto.purchasable)
