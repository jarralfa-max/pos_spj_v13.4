from __future__ import annotations

from typing import Any, Dict, List


class ProductCatalogQueryService:
    """Read-only queries for POS product catalog."""

    def __init__(self, db_conn):
        self.db = db_conn

    def get_categories(self) -> List[str]:
        rows = self.db.execute(
            "SELECT DISTINCT COALESCE(categoria,'') AS categoria "
            "FROM productos "
            "WHERE COALESCE(oculto,0)=0 AND COALESCE(activo,1)=1 "
            "AND categoria IS NOT NULL AND categoria != '' "
            "ORDER BY categoria"
        ).fetchall()
        return [r[0] if not hasattr(r, 'keys') else r['categoria'] for r in rows]

    def list_visible_products(self, branch_id: int, filtro: str = "", categoria: str = "") -> List[Dict[str, Any]]:
        stock_expr, stock_join, params = self._stock_source_sql(branch_id)
        query = (
            "SELECT p.id, p.nombre, p.precio, "
            f"{stock_expr} as stock_sucursal, "
            "p.unidad, p.categoria, p.stock_minimo, p.imagen_path, "
            "p.es_compuesto, p.es_subproducto, "
            "COALESCE(p.codigo_barras,'') as codigo_barras, COALESCE(p.codigo,'') as codigo "
            "FROM productos p "
            f"{stock_join}"
            "WHERE p.oculto = 0 AND COALESCE(p.activo,1)=1"
        )
        if filtro:
            query += (
                " AND (p.nombre LIKE ? OR p.id = ? OR p.categoria LIKE ? "
                "OR COALESCE(p.codigo_barras,'') = ? OR COALESCE(p.codigo,'') = ?)"
            )
            params += [f"%{filtro}%", filtro, f"%{filtro}%", filtro, filtro]
        if categoria:
            query += " AND COALESCE(p.categoria,'') = ?"
            params.append(categoria)
        query += " ORDER BY p.nombre"

        rows = self.db.execute(query, params).fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            get = (lambda k, i: r[k] if hasattr(r, 'keys') else r[i])
            out.append({
                'id': get('id', 0),
                'nombre': get('nombre', 1),
                'codigo': get('codigo', 11),
                'precio': float(get('precio', 2) or 0),
                'unidad': get('unidad', 4),
                'existencia': float(get('stock_sucursal', 3) or 0),
                'stock_state': 'ok',
                'imagen_path': get('imagen_path', 7),
                'categoria': get('categoria', 5),
                'stock_minimo': float(get('stock_minimo', 6) or 0),
                'es_compuesto': int(get('es_compuesto', 8) or 0),
                'es_subproducto': int(get('es_subproducto', 9) or 0),
                'codigo_barras': get('codigo_barras', 10),
            })
        return out


    def _stock_source_sql(self, branch_id: int) -> tuple[str, str, List[Any]]:
        """Return stock expression/join for the schema available in this DB.

        Some development/customer databases have already archived the legacy
        branch_inventory table but have not populated it again. The POS catalog
        must still render products using canonical inventory_stock when present,
        or productos.existencia as a read-only fallback. This method never creates
        schema; migrations remain the only schema owner.
        """
        if self._table_exists("branch_inventory"):
            return (
                "COALESCE(bi.quantity, p.existencia, 0)",
                "LEFT JOIN branch_inventory bi ON bi.product_id=p.id AND bi.branch_id=? ",
                [branch_id],
            )
        if self._table_exists("inventory_stock"):
            return (
                "COALESCE(istock.quantity, p.existencia, 0)",
                "LEFT JOIN inventory_stock istock ON istock.product_id=p.id AND istock.branch_id=? ",
                [branch_id],
            )
        return "COALESCE(p.existencia, 0)", "", []

    def _table_exists(self, table_name: str) -> bool:
        row = self.db.execute(
            "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name=? LIMIT 1",
            (table_name,),
        ).fetchone()
        return row is not None

    def get_product_by_barcode(self, branch_id: int, barcode: str) -> Dict[str, Any] | None:
        rows = self.list_visible_products(branch_id=branch_id, filtro=str(barcode or ""))
        for p in rows:
            if p.get('codigo_barras') == barcode or p.get('codigo') == barcode:
                return p
        return None
