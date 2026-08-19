"""SalesCatalogQueryService — the master prompt §14 `ProductCatalogQueryService`
for the Sales/POS bounded context: the left catalog panel's ONLY read path
(§14: "No consultar Productos o Inventario directamente desde UI").

This is a NEW, canonical implementation — not a duplicate of
`core/services/sales/product_catalog_query_service.py` (the legacy service
`modulos/ventas.py` still calls today, untouched by this phase). That legacy
service was rebuilt fresh here for the same reason `Sale`/`SaleLine` were
rebuilt fresh in SALES-3 rather than reused: it stores money as `float`
(REGLA CERO violation) and its own `stock_state` output column is DEAD CODE
— always the hardcoded literal `"ok"`, never actually computed (confirmed by
reading it line by line before writing this file) — which is exactly why
`modulos/ventas.py::ProductCard` had to compute stock classification itself
in the widget, the precise anti-pattern master prompt §16 forbids. This
service resolves `stock_state`/`sellable` via `ProductAvailabilityPolicy`
instead, and returns Decimal, never float.

Sales does not own product/price/inventory data (§6) — this service is Sales'
own READ MODEL composed by joining the Products/Pricing/Inventory bounded
contexts' own canonical tables (`products`, `product_price`, `price_list`,
`product_categories`, `inventory_replenishment_rule`, `product_images`,
`product_barcodes`, `inventory_balances`), the same tables the legacy service
already joins — verified against those contexts' real schema files before
writing this SQL, not guessed.
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.sales.dto import ProductCatalogEntryDTO
from backend.domain.sales.policies.product_availability_policy import ProductAvailabilityPolicy
from backend.infrastructure.db.repositories.sales.base import to_decimal

_BASE_QUERY = """
    SELECT
        p.id AS product_id,
        p.name AS name,
        p.code AS sku,
        COALESCE(pb.barcode_value, '') AS barcode,
        COALESCE(p.base_unit_id, '') AS unit,
        COALESCE(pp.sale_price, '0') AS effective_price,
        COALESCE(pi.uri, '') AS image_reference,
        CASE WHEN COALESCE(p.bundle_allowed,0)=1 OR COALESCE(p.recipe_allowed,0)=1
             THEN 1 ELSE 0 END AS is_composite,
        COALESCE(rr.min_quantity, '0') AS minimum_quantity,
        COALESCE(icanon.qty, '0') AS available_quantity
    FROM products p
    LEFT JOIN product_price pp
        ON pp.product_id = p.id AND pp.branch_id = ''
       AND pp.price_list_id = (SELECT id FROM price_list WHERE code = 'BASE')
    LEFT JOIN product_categories pc ON pc.id = p.category_id
    LEFT JOIN inventory_replenishment_rule rr
        ON rr.product_id = p.id AND rr.branch_id = '' AND rr.warehouse_id = ''
    LEFT JOIN product_images pi ON pi.product_id = p.id AND pi.is_primary = 1
    LEFT JOIN product_barcodes pb
        ON pb.product_id = p.id AND pb.is_primary = 1 AND COALESCE(pb.active,1) = 1
    LEFT JOIN (
        SELECT product_id, branch_id,
               SUM(CAST(quantity AS REAL) - CAST(reserved_quantity AS REAL)) AS qty
        FROM inventory_balances
        WHERE inventory_status = 'AVAILABLE'
        GROUP BY product_id, branch_id
    ) icanon ON icanon.product_id = p.id AND icanon.branch_id = ?
    WHERE p.lifecycle_status = 'ACTIVE' AND COALESCE(p.internal_only, 0) = 0
"""


class SalesCatalogQueryService:
    def __init__(self, connection) -> None:
        self._conn = connection

    def search(
        self, *, branch_id: str, search: str = "", category_id: str | None = None,
        limit: int = 200,
    ) -> tuple[ProductCatalogEntryDTO, ...]:
        query = _BASE_QUERY
        params: list = [branch_id]
        if search:
            query += (
                " AND (p.name LIKE ? OR p.code = ?"
                " OR EXISTS (SELECT 1 FROM product_barcodes b"
                "            WHERE b.product_id = p.id AND b.barcode_value = ?))"
            )
            params += [f"%{search}%", search, search]
        if category_id:
            query += " AND p.category_id = ?"
            params.append(category_id)
        query += " ORDER BY p.name LIMIT ?"
        params.append(limit)

        cursor = self._conn.execute(query, params)
        columns = [col[0] for col in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return tuple(self._to_dto(row) for row in rows)

    def find_by_code(self, *, branch_id: str, code: str) -> ProductCatalogEntryDTO | None:
        """POS-12/§17: exact SKU-or-barcode resolution for a scanned code —
        distinct from `search()`, which does a fuzzy `LIKE` match against
        name too and is meant for the catalog grid, not for a scanner that
        must resolve to exactly one product or none at all."""
        query = _BASE_QUERY + " AND (p.code = ? OR EXISTS (" \
            "SELECT 1 FROM product_barcodes b WHERE b.product_id = p.id AND b.barcode_value = ?))"
        cursor = self._conn.execute(query, [branch_id, code, code])
        columns = [col[0] for col in cursor.description]
        row = cursor.fetchone()
        return None if row is None else self._to_dto(dict(zip(columns, row)))

    def get_categories(self) -> tuple[str, ...]:
        rows = self._conn.execute(
            "SELECT name FROM product_categories WHERE active = 1 ORDER BY name"
        ).fetchall()
        return tuple(row[0] for row in rows)

    @staticmethod
    def _to_dto(row: dict) -> ProductCatalogEntryDTO:
        available_quantity = to_decimal(row["available_quantity"])
        minimum_quantity = to_decimal(row["minimum_quantity"])
        state = ProductAvailabilityPolicy.classify(available_quantity, minimum_quantity)
        sellable = ProductAvailabilityPolicy.is_sellable(
            state, is_composite=bool(row["is_composite"]))
        warnings: list[str] = []
        if state.value in ("CRITICAL_STOCK", "OUT_OF_STOCK"):
            warnings.append(f"Existencia baja: {available_quantity} disponible(s)")
        return ProductCatalogEntryDTO(
            product_id=row["product_id"], name=row["name"], sku=row["sku"] or "",
            barcode=row["barcode"] or None, unit=row["unit"] or "",
            effective_price=to_decimal(row["effective_price"]),
            stock_state=state.value, available_quantity=available_quantity,
            image_reference=row["image_reference"] or None, sellable=sellable,
            warnings=tuple(warnings),
        )
