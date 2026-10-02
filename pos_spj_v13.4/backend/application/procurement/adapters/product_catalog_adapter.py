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

from decimal import Decimal, InvalidOperation

from backend.application.procurement.ports import (
    ProcurementProductOption,
    PurchaseProductProfile,
    PurchaseUnitOption,
)
from backend.application.products.queries.integration_query_services import (
    PurchaseProductConfigQueryService,
)
from backend.application.products.queries.product_selection_query_service import (
    ProductSearchQuery,
    SearchPurchasableProductsQueryService,
)


class ProcurementProductCatalogAdapter:
    def __init__(self, connection) -> None:
        self._connection = connection
        self._search_service = SearchPurchasableProductsQueryService(connection)
        self._purchase_config = PurchaseProductConfigQueryService(connection)

    def search(self, query: str, *, branch_id: str | None = None,
               limit: int = 20) -> list[ProcurementProductOption]:
        if not query or not query.strip():
            return []
        # Las compras son GLOBALES (decisión del usuario 2026-09-25): se busca en
        # todo el catálogo comprable y la sucursal sólo sirve para MARCAR los
        # productos que no están habilitados en ella.
        try:
            rows = self._search_service.search(query=query.strip(), limit=limit)
        except sqlite3.OperationalError:
            return []
        enabled = (self._search_service.enabled_in_branch(
            [row.product_id for row in rows], branch_id) if branch_id else None)
        return [_to_option(row, None if enabled is None else row.product_id in enabled)
                for row in rows]

    def explain_empty(self, query: str, *, branch_id: str | None = None) -> str | None:
        """Por qué la búsqueda no trajo nada, en texto para el comprador."""
        try:
            # Búsqueda global: la habilitación por sucursal nunca explica un vacío.
            razon = self._search_service.explain_empty(ProductSearchQuery(
                text=(query or "").strip() or None))
        except sqlite3.OperationalError:
            return None
        return razon.message if razon is not None else None

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


    def purchase_profile(self, product_id: str) -> PurchaseProductProfile | None:
        """Unidades de compra, conversión y base de precio, tal como las define
        Productos. ``None`` si el producto no existe."""
        if not product_id:
            return None
        config = self._purchase_config.get(product_id)
        if config is None:
            return None
        units = []
        for unit in config.purchase_units:
            try:
                factor = Decimal(unit.factor_to_base)
            except (InvalidOperation, ValueError):
                continue
            units.append(PurchaseUnitOption(code=unit.code, name=unit.name,
                                            factor_to_base=factor, dimension=unit.dimension,
                                            is_base=unit.is_base,
                                            fractional_receipt=bool(getattr(
                                                unit, "fractional_receipt", True))))
        return PurchaseProductProfile(
            product_id=config.product_id, code=config.code, name=config.name,
            base_unit=config.base_unit_code, base_unit_name=config.base_unit_name,
            base_unit_dimension=config.base_unit_dimension, units=tuple(units),
            purchasable=config.purchasable, catch_weight=config.catch_weight_enabled,
            price_basis=config.price_basis, lot_controlled=config.lot_controlled,
            expiration_controlled=config.expiration_controlled,
            temperature_tracked=config.temperature_required,
            serial_tracked=config.serial_controlled)


def _to_option(dto, enabled_in_branch: bool | None = None) -> ProcurementProductOption:
    return ProcurementProductOption(
        product_id=dto.product_id, code=dto.code, name=dto.name,
        purchase_unit=dto.base_unit_id, purchasable=dto.purchasable,
        enabled_in_branch=enabled_in_branch)
