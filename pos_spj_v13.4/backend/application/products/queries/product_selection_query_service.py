"""Canonical product-selection query services (§11) — contratos consumidores.

Permiten que POS, Compras, Inventario, Transferencias y Producción **busquen
productos canónicos** (por nombre/código/sucursal/canal/tipo/especie/capacidad)
sin conocer el UUID de antemano y **sin leer la tabla legacy `productos`**. Sólo
leen el maestro canónico `products` (+ habilitación por sucursal `branch_product`
y surtido por canal `assortments`/`assortment_products`). Read-only.

`ProductSelectionDTO` es el contrato base; cada consumidor puede ampliarlo, pero la
UI nunca debe consultar tablas de Productos directamente.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProductSelectionDTO:
    product_id: str
    code: str
    name: str
    short_name: str | None
    product_type: str
    base_unit_id: str | None
    species_id: str | None
    catch_weight_enabled: bool
    lot_controlled: bool
    inventory_managed: bool
    sellable: bool
    purchasable: bool
    producible: bool
    internal_only: bool


_COLUMNS = (
    "p.id, p.code, p.name, p.short_name, p.product_type, p.base_unit_id, "
    "p.species_id, p.catch_weight_enabled, p.lot_controlled, p.inventory_managed, "
    "p.sellable, p.purchasable, p.producible, p.internal_only"
)


def _row_to_dto(r) -> ProductSelectionDTO:
    return ProductSelectionDTO(
        product_id=r[0], code=r[1], name=r[2], short_name=r[3], product_type=r[4],
        base_unit_id=r[5], species_id=r[6], catch_weight_enabled=bool(r[7]),
        lot_controlled=bool(r[8]), inventory_managed=bool(r[9]), sellable=bool(r[10]),
        purchasable=bool(r[11]), producible=bool(r[12]), internal_only=bool(r[13]))


class _BaseProductSearch:
    """Búsqueda canónica con filtros comunes (§11). Las subclases fijan la
    capacidad requerida y si excluyen productos internos."""

    #: columna de capacidad requerida: 'sellable'|'purchasable'|'inventory_managed'|None
    capability_column: str | None = None
    #: excluir productos de uso interno (POS)
    exclude_internal: bool = False

    def __init__(self, connection) -> None:
        self._conn = connection

    def search(self, *, query: str | None = None, branch_id: str | None = None,
               channel_id: str | None = None, warehouse_id: str | None = None,
               product_type: str | None = None, species_id: str | None = None,
               category_id: str | None = None, active_only: bool = True,
               limit: int = 50, offset: int = 0) -> list[ProductSelectionDTO]:
        joins: list[str] = []
        join_params: list = []
        where: list[str] = []
        where_params: list = []

        if self.capability_column:
            where.append(f"p.{self.capability_column}=1")
        if self.exclude_internal:
            where.append("p.internal_only=0")
        if active_only:
            where.append("p.lifecycle_status='ACTIVE'")

        # habilitación por sucursal (branch_product)
        if branch_id:
            joins.append("JOIN branch_product bp ON bp.product_id=p.id "
                         "AND bp.branch_id=? AND bp.enabled=1")
            join_params.append(str(branch_id))
        # surtido por canal (assortments activo del canal que contiene el producto)
        if channel_id:
            join = ("JOIN assortment_products ap ON ap.product_id=p.id AND ap.enabled=1 "
                    "JOIN assortments a ON a.id=ap.assortment_id AND a.active=1 "
                    "AND a.channel=?")
            join_params.append(str(channel_id))
            if branch_id:
                join += " AND (a.branch_id=? OR a.branch_id='')"
                join_params.append(str(branch_id))
            joins.append(join)

        if query:
            where.append("(p.name LIKE ? OR COALESCE(p.code,'') LIKE ?)")
            where_params += [f"%{query}%", f"%{query}%"]
        if product_type:
            where.append("p.product_type=?")
            where_params.append(str(product_type))
        if species_id:
            where.append("p.species_id=?")
            where_params.append(str(species_id))
        if category_id:
            where.append("p.category_id=?")
            where_params.append(str(category_id))

        sql = f"SELECT DISTINCT {_COLUMNS} FROM products p " + " ".join(joins)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY p.name LIMIT ? OFFSET ?"
        params = join_params + where_params + [int(limit), int(offset)]
        return [_row_to_dto(r) for r in self._conn.execute(sql, params).fetchall()]


class SearchSellableProductsQueryService(_BaseProductSearch):
    """POS/venta: productos ACTIVE, vendibles, no internos, habilitados en la
    sucursal/canal indicados."""
    capability_column = "sellable"
    exclude_internal = True


class SearchPurchasableProductsQueryService(_BaseProductSearch):
    """Compras: productos ACTIVE, comprables, habilitados en la sucursal."""
    capability_column = "purchasable"


class SearchInventoryManagedProductsQueryService(_BaseProductSearch):
    """Inventario: productos que controlan inventario físico."""
    capability_column = "inventory_managed"


class SearchTransferableProductsQueryService(_BaseProductSearch):
    """Transferencias: productos inventariables habilitados en la sucursal origen.

    El destino se valida en el flujo de transferencias (unidad compatible + destino
    habilitado); aquí se filtra el catálogo transferible del origen."""
    capability_column = "inventory_managed"


class SearchProductionInputsQueryService(_BaseProductSearch):
    """Producción: insumos producibles/procesables (input de receta/rendimiento)."""
    capability_column = "inventory_managed"


class SearchWasteEligibleProductsQueryService(_BaseProductSearch):
    """Merma: productos inventariables sujetos a merma administrativa."""
    capability_column = "inventory_managed"
