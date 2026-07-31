"""PosProductCatalogFacade (§12) — catálogo POS canónico compuesto.

El POS deja de leer la tabla legacy `productos`. Este facade **compone** tres
fuentes respetando los límites de contexto (no mete precio ni existencia en el
agregado `Product`):

- **Productos**: identidad, nombre, código, código de barras, flags,
  habilitación por sucursal/canal → `SearchSellableProductsQueryService`.
- **Pricing**: precio de venta vigente → `PricingReadFacade.sale_price_amount`.
- **Inventario**: existencia disponible → `InventoryAvailabilityQueryService`.

Cada colaborador es inyectable (composición/test); por defecto se arma con la
conexión. Read-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class PosCatalogItemDTO:
    product_id: str
    code: str
    name: str
    short_name: str | None
    barcode: str | None
    base_unit_id: str | None
    catch_weight_enabled: bool
    sale_price: Decimal | None      # de Pricing (None si no hay precio vigente)
    available: Decimal              # de Inventario (disponible canónico)


class PosProductCatalogFacade:
    def __init__(self, connection, *, search_service=None, pricing_facade=None,
                 availability_service=None) -> None:
        self._conn = connection
        if search_service is None:
            from backend.application.products.queries.product_selection_query_service import (
                SearchSellableProductsQueryService,
            )
            search_service = SearchSellableProductsQueryService(connection)
        if pricing_facade is None:
            from backend.application.pricing.queries.pricing_read_facade import (
                PricingReadFacade,
            )
            pricing_facade = PricingReadFacade(connection)
        if availability_service is None:
            from backend.application.inventory.queries import (
                InventoryAvailabilityQueryService,
            )
            availability_service = InventoryAvailabilityQueryService(connection)
        self._search = search_service
        self._pricing = pricing_facade
        self._availability = availability_service

    def search(self, *, branch_id: str, query: str | None = None,
               channel_id: str | None = None, limit: int = 50,
               offset: int = 0) -> list[PosCatalogItemDTO]:
        """Productos vendibles canónicos con precio vigente y disponible físico.

        `channel_id` es opcional: si se pasa (p. ej. "POS") además exige surtido de
        canal; si se omite, basta con vendible + ACTIVE + sucursal habilitada."""
        items = self._search.search(query=query, branch_id=branch_id,
                                    channel_id=channel_id, limit=limit, offset=offset)
        out: list[PosCatalogItemDTO] = []
        for it in items:
            price = self._pricing.sale_price_amount(it.product_id, branch_id=branch_id)
            available = self._availability.get_availability(
                product_id=it.product_id, branch_id=branch_id).available
            out.append(PosCatalogItemDTO(
                product_id=it.product_id, code=it.code, name=it.name,
                short_name=it.short_name, barcode=self._primary_barcode(it.product_id),
                base_unit_id=it.base_unit_id,
                catch_weight_enabled=it.catch_weight_enabled,
                sale_price=price, available=available))
        return out

    def _primary_barcode(self, product_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT barcode_value FROM product_barcodes "
            "WHERE product_id=? AND active=1 ORDER BY is_primary DESC LIMIT 1",
            (product_id,)).fetchone()
        return row[0] if row else None
