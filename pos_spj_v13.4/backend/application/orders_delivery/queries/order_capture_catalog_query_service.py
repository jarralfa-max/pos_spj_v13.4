"""OrderCaptureCatalogQueryService — los productos que se pueden pedir en una sucursal.

POR QUÉ NO EL CATÁLOGO DEL POS
------------------------------
`SalesCatalogQueryService` (el panel del POS vivo) no filtra por habilitación en
la sucursal ni por `sellable`, devuelve `base_unit_id` crudo en vez del código de
unidad y no dice si el producto se vende por peso. Para capturar un pedido hacen
falta las tres cosas, así que esta consulta compone las lecturas canónicas de cada
contexto sin copiar sus reglas:

- Productos: `SearchSellableProductsQueryService` (ACTIVE, vendible, no interno,
  habilitado en la sucursal).
- Precio: `PricingReadFacade.sale_price_amount` (sucursal → lista base).
- Unidad: `UnitCatalogQueryService` (código y dimensión; WEIGHT = se pide por peso).

Un producto sin precio vigente aparece con `price=None`: la pantalla lo enseña y el
caso de uso lo rechaza, en vez de capturarlo a $0.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.application.pricing.queries.pricing_read_facade import PricingReadFacade
from backend.application.products.queries.product_selection_query_service import (
    SearchSellableProductsQueryService,
)
from backend.application.products.queries.unit_catalog_query_service import (
    UnitCatalogQueryService,
)

#: Dimensión de `units_of_measure` que significa "se pide por peso".
WEIGHT_DIMENSION = "WEIGHT"


@dataclass(frozen=True, slots=True)
class CaptureCatalogItem:
    product_id: str
    code: str
    name: str
    unit_code: str
    weighed: bool
    catch_weight_enabled: bool
    #: Precio vigente en la sucursal; `None` si Pricing no tiene uno.
    price: Decimal | None


class OrderCaptureCatalogQueryService:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._products = SearchSellableProductsQueryService(connection)
        self._pricing = PricingReadFacade(connection)
        self._units = UnitCatalogQueryService(connection)

    def search(self, *, branch_id: str, query: str = "", limit: int = 20) -> list[CaptureCatalogItem]:
        productos = self._products.search(query=query or None, branch_id=branch_id, limit=limit)
        return [self._item(producto, branch_id) for producto in productos]

    def get(self, *, branch_id: str, product_id: str) -> CaptureCatalogItem | None:
        """El producto si se puede pedir en la sucursal; `None` si no existe, no es
        vendible o no está habilitado ahí. Pasa por la MISMA búsqueda que la
        pantalla, así que no hay una regla de "vendible" distinta para validar."""
        fila = self._conn.execute(
            "SELECT code FROM products WHERE id=?", (product_id,)).fetchone()
        if fila is None:
            return None
        for producto in self._products.search(query=fila[0], branch_id=branch_id, limit=50):
            if producto.product_id == product_id:
                return self._item(producto, branch_id)
        return None

    def _item(self, producto, branch_id: str) -> CaptureCatalogItem:
        unidad = self._units.get_unit(producto.base_unit_id) if producto.base_unit_id else None
        return CaptureCatalogItem(
            product_id=producto.product_id, code=producto.code, name=producto.name,
            unit_code=(unidad or {}).get("code") or "",
            weighed=bool(unidad and unidad.get("dimension") == WEIGHT_DIMENSION),
            catch_weight_enabled=bool(producto.catch_weight_enabled),
            price=self._pricing.sale_price_amount(producto.product_id, branch_id=branch_id))
