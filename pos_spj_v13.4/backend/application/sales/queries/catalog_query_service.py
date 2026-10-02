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
        COALESCE(u.code, p.base_unit_id, '') AS unit,
        COALESCE(u.dimension, '') AS unit_dimension,
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
    LEFT JOIN units_of_measure u ON u.id = p.base_unit_id
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
        armables = self._reconstructible(rows, branch_id)
        return tuple(self._to_dto(row, armables.get(row["product_id"])) for row in rows)

    def _reconstructible(self, rows: list[dict], branch_id: str) -> dict:
        """ATP (§17, Fase 7): cuánto se puede ARMAR de cada producto con las
        partes en existencia, según su despiece reversible. Sólo para los
        productos que tienen uno (una consulta); para los demás no se calcula
        nada. Es un diagnóstico de vitrina: si la infraestructura de despiece no
        existe en esta base, el catálogo sigue mostrando la existencia directa.
        """
        try:
            from backend.application.inventory.queries.sellable_availability_query_service import (
                SellableAvailabilityQueryService,
            )
            from backend.infrastructure.db.repositories.products.cutting_scheme_repository import (
                CuttingSchemeRepository,
            )
            reversibles = CuttingSchemeRepository(self._conn).reversible_input_product_ids()
            if not reversibles:
                return {}
            atp = SellableAvailabilityQueryService(self._conn)
            return {
                row["product_id"]: atp.get_sellable_availability(
                    product_id=row["product_id"], branch_id=branch_id).reconstructible
                for row in rows if row["product_id"] in reversibles
            }
        except Exception:
            import logging
            logging.getLogger("spj.sales.catalog").exception(
                "ATP reconstruible no disponible; se muestra sólo existencia directa")
            return {}

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
        if row is None:
            return None
        fila = dict(zip(columns, row))
        return self._to_dto(fila, self._reconstructible([fila], branch_id).get(fila["product_id"]))

    def category_options(self) -> tuple[tuple[str, str], ...]:
        """(id, nombre) de las categorías activas, para el filtro del POS.
        `search(category_id=...)` filtra por ID: el combo mandaba el NOMBRE y
        elegir una categoría vaciaba la cuadrícula (re-auditoría POS)."""
        rows = self._conn.execute(
            "SELECT id, name FROM product_categories WHERE active = 1 ORDER BY name"
        ).fetchall()
        return tuple((str(row[0]), str(row[1])) for row in rows)

    def get_categories(self) -> tuple[str, ...]:
        rows = self._conn.execute(
            "SELECT name FROM product_categories WHERE active = 1 ORDER BY name"
        ).fetchall()
        return tuple(row[0] for row in rows)

    @staticmethod
    def _to_dto(row: dict, reconstructible=None) -> ProductCatalogEntryDTO:
        armable = Decimal(str(reconstructible or 0))
        available_quantity = to_decimal(row["available_quantity"]) + armable
        minimum_quantity = to_decimal(row["minimum_quantity"])
        state = ProductAvailabilityPolicy.classify(available_quantity, minimum_quantity)
        effective_price = to_decimal(row["effective_price"])
        priced = effective_price > 0
        # Sin precio no se vende (`SaleLinePolicy.ensure_priced`); se informa
        # aquí para que la tarjeta diga POR QUÉ en vez de no hacer nada.
        sellable = priced and ProductAvailabilityPolicy.is_sellable(
            state, is_composite=bool(row["is_composite"]))
        warnings: list[str] = []
        if not priced:
            warnings.append("Sin precio de venta: captúralo en Precios")
        if state.value == "OUT_OF_STOCK":
            warnings.append("Sin existencia: vender requiere autorización al cobrar")
        elif state.value == "CRITICAL_STOCK":
            warnings.append(f"Existencia baja: {available_quantity} disponible(s)")
        if armable > 0:
            warnings.append(f"{armable} se arman con partes en existencia")
        return ProductCatalogEntryDTO(
            product_id=row["product_id"], name=row["name"], sku=row["sku"] or "",
            barcode=row["barcode"] or None, unit=row["unit"] or "",
            effective_price=effective_price,
            stock_state=state.value, available_quantity=available_quantity,
            image_reference=row["image_reference"] or None, sellable=sellable,
            warnings=tuple(warnings), reconstructible_quantity=armable,
            sold_by_weight=(row.get("unit_dimension") or "").upper() == "WEIGHT",
            priced=priced,
        )
