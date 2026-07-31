from __future__ import annotations

from typing import Any, Dict, List


class ProductCatalogQueryService:
    """Read-only queries for the POS product catalog — canónico (P0-B slice 6).

    El POS ya NO lee la tabla legacy ``productos``. Compone el maestro canónico
    ``products`` con sus satélites, preservando el contrato de salida que consume
    ``modulos/ventas.py``:

    - precio: lista BASE de ``product_price`` (sucursal global ``''``);
    - unidad: ``products.base_unit_id`` (unidad conservada por el backfill 148);
    - categoría: ``product_categories.name`` (via ``category_id``, backfill 166/167);
    - stock mínimo: regla global de ``inventory_replenishment_rule`` (backfill 168);
    - imagen: ``product_images`` primaria (backfill 170);
    - código de barras: ``product_barcodes`` primario (backfill 170);
    - ``es_compuesto`` = ``bundle_allowed OR recipe_allowed``;
    - ``es_subproducto`` = ``product_type IN ('BY_PRODUCT','CO_PRODUCT')``;
    - existencia: proyección canónica ``inventory_balances`` (INV-27, gated).

    No hay precio/existencia en el agregado ``Product``; se componen aquí.
    """

    def __init__(self, db_conn):
        self.db = db_conn

    def get_categories(self) -> List[str]:
        if not self._table_exists("product_categories"):
            return []
        rows = self.db.execute(
            "SELECT name FROM product_categories "
            "WHERE COALESCE(active,1)=1 AND COALESCE(name,'') != '' "
            "ORDER BY name"
        ).fetchall()
        return [r[0] if not hasattr(r, "keys") else r["name"] for r in rows]

    def list_visible_products(self, branch_id, filtro: str = "",
                              categoria: str = "") -> List[Dict[str, Any]]:
        stock_expr, stock_join, params = self._stock_source_sql(branch_id)
        base_list = "(SELECT id FROM price_list WHERE code='BASE')"
        query = (
            "SELECT p.id, p.name AS nombre, "
            "CAST(COALESCE(pp.sale_price,'0') AS REAL) AS precio, "
            f"{stock_expr} AS stock_sucursal, "
            "COALESCE(p.base_unit_id,'') AS unidad, "
            "COALESCE(pc.name,'') AS categoria, "
            "CAST(COALESCE(rr.min_quantity,'0') AS REAL) AS stock_minimo, "
            "COALESCE(pi.uri,'') AS imagen_path, "
            "CASE WHEN COALESCE(p.bundle_allowed,0)=1 OR COALESCE(p.recipe_allowed,0)=1 "
            "     THEN 1 ELSE 0 END AS es_compuesto, "
            "CASE WHEN p.product_type IN ('BY_PRODUCT','CO_PRODUCT') THEN 1 ELSE 0 END "
            "     AS es_subproducto, "
            "COALESCE(pb.barcode_value,'') AS codigo_barras, "
            "COALESCE(p.code,'') AS codigo "
            "FROM products p "
            "LEFT JOIN product_price pp ON pp.product_id=p.id AND pp.branch_id='' "
            f"  AND pp.price_list_id={base_list} "
            "LEFT JOIN product_categories pc ON pc.id=p.category_id "
            "LEFT JOIN inventory_replenishment_rule rr ON rr.product_id=p.id "
            "  AND rr.branch_id='' AND rr.warehouse_id='' "
            "LEFT JOIN product_images pi ON pi.product_id=p.id AND pi.is_primary=1 "
            "LEFT JOIN product_barcodes pb ON pb.product_id=p.id AND pb.is_primary=1 "
            "  AND COALESCE(pb.active,1)=1 "
            f"{stock_join}"
            "WHERE p.lifecycle_status='ACTIVE' AND COALESCE(p.internal_only,0)=0"
        )
        if filtro:
            query += (
                " AND (p.name LIKE ? OR p.id = ? OR COALESCE(pc.name,'') LIKE ? "
                "OR EXISTS (SELECT 1 FROM product_barcodes b WHERE b.product_id=p.id "
                "           AND b.barcode_value = ?) "
                "OR COALESCE(p.code,'') = ?)"
            )
            params += [f"%{filtro}%", filtro, f"%{filtro}%", filtro, filtro]
        if categoria:
            query += " AND COALESCE(pc.name,'') = ?"
            params.append(categoria)
        query += " ORDER BY p.name"

        rows = self.db.execute(query, params).fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            get = (lambda k, i: r[k] if hasattr(r, "keys") else r[i])
            out.append({
                "id": get("id", 0),
                "nombre": get("nombre", 1),
                "codigo": get("codigo", 11),
                "precio": float(get("precio", 2) or 0),
                "unidad": get("unidad", 4),
                "existencia": float(get("stock_sucursal", 3) or 0),
                "stock_state": "ok",
                "imagen_path": get("imagen_path", 7),
                "categoria": get("categoria", 5),
                "stock_minimo": float(get("stock_minimo", 6) or 0),
                "es_compuesto": int(get("es_compuesto", 8) or 0),
                "es_subproducto": int(get("es_subproducto", 9) or 0),
                "codigo_barras": get("codigo_barras", 10),
            })
        return out

    def _stock_source_sql(self, branch_id) -> tuple[str, str, List[Any]]:
        """Existencia POS desde la proyección canónica ``inventory_balances``
        (INV-27: las lecturas siguen a las escrituras; flag ON en toda DB
        bootstrapped). Sin la tabla, la existencia se muestra en cero (nunca una
        lectura legacy silenciosa)."""
        if self._table_exists("inventory_balances"):
            return (
                "COALESCE(icanon.qty, 0)",
                "LEFT JOIN (SELECT product_id, branch_id,"
                " SUM(CAST(quantity AS REAL) - CAST(reserved_quantity AS REAL)) AS qty"
                " FROM inventory_balances WHERE inventory_status='AVAILABLE'"
                " GROUP BY product_id, branch_id) icanon"
                " ON icanon.product_id=p.id AND icanon.branch_id=? ",
                [branch_id],
            )
        return "0", "", []

    def _table_exists(self, table_name: str) -> bool:
        row = self.db.execute(
            "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name=? LIMIT 1",
            (table_name,),
        ).fetchone()
        return row is not None

    def get_product_by_barcode(self, branch_id, barcode: str) -> Dict[str, Any] | None:
        rows = self.list_visible_products(branch_id=branch_id, filtro=str(barcode or ""))
        for p in rows:
            if p.get("codigo_barras") == barcode or p.get("codigo") == barcode:
                return p
        return None
