"""Read-only BI query service for sales metrics and sales charts.

All SQL for the sales side of the dashboard lives here (backend layer). The UI
consumes the returned read models only. Cost of goods uses the real captured
line cost with a fallback to product cost columns.

FUENTE: `v_ventas_unificada` / `v_detalles_venta_unificada` (migraciones
256/257), no las tablas legacy. Leer `ventas`/`detalles_venta` dejaba fuera de
TODOS estos KPIs las ventas del POS, que desde SALES-19..22 nacen en el
agregado canónico `sales` y nunca pasan por la tabla legacy. Las vistas son la
única fuente que contiene ambas mientras queden escritores legacy; su criterio
de eliminación está en las propias migraciones.

`COST_LINE` no cambia y sigue siendo correcto sobre la vista: su primer término
(`dv.costo_unitario_real`) está vacío en la práctica —ningún código productivo
escribe esa columna— así que el costo real de toda venta, canónica o legacy,
lo aporta el fallback a `product_cost.average_cost`.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("spj.bi.sales")

# Costo robusto por línea: costo capturado primero, luego el costo promedio
# canónico (`product_cost`, sucursal global branch_id=''). El maestro `products`
# NO guarda costo (§11); las consultas hacen LEFT JOIN product_cost pcost.
COST_LINE = ("COALESCE(NULLIF(dv.costo_unitario_real,0), "
             "NULLIF(CAST(pcost.average_cost AS REAL),0), 0)")
# Fragmento reutilizable: costo canónico por línea de venta.
_COST_JOIN = ("LEFT JOIN product_cost pcost "
              "ON pcost.product_id=dv.producto_id AND pcost.branch_id=''")


def _sales_where(f, alias: str = "v") -> tuple[str, list]:
    """Build a WHERE clause for header-level sales queries from filters.

    Supported: date range, branch, payment method, customer, category (EXISTS).
    Channel/product_type are not yet backed by schema columns and are ignored.
    """
    clauses = [f"{alias}.estado='completada'",
               f"DATE({alias}.fecha) BETWEEN ? AND ?"]
    params: list = [f.date_from, f.date_to]
    if f.branch_id:
        clauses.append(f"{alias}.sucursal_id = ?")
        params.append(str(f.branch_id))
    if f.payment_method:
        clauses.append(f"{alias}.forma_pago = ?")
        params.append(f.payment_method)
    if f.customer_id:
        clauses.append(f"{alias}.cliente_id = ?")
        params.append(str(f.customer_id))
    if f.category:
        clauses.append(
            f"EXISTS (SELECT 1 FROM v_detalles_venta_unificada dv JOIN products p "
            f"ON p.id=dv.producto_id "
            f"JOIN product_categories pcat ON pcat.id=p.category_id "
            f"WHERE dv.venta_id={alias}.id AND pcat.name=?)")
        params.append(f.category)
    return " AND ".join(clauses), params


class BiSalesQueryService:
    def __init__(self, conn):
        self._conn = conn

    def _q(self, sql, params=()):
        try:
            return self._conn.execute(sql, params).fetchall()
        except Exception as e:
            logger.warning("BiSalesQueryService: %s", e)
            return []

    def _one(self, sql, params=()):
        rows = self._q(sql, params)
        return rows[0] if rows else None

    # ── Aggregate KPIs ────────────────────────────────────────────────────────

    def sales_totals(self, f) -> dict:
        """Ventas netas, número de órdenes y ticket promedio del periodo."""
        where, params = _sales_where(f)
        row = self._one(
            f"SELECT COALESCE(SUM(v.total),0), COUNT(*) FROM v_ventas_unificada v WHERE {where}",
            params)
        ventas = float(row[0]) if row else 0.0
        ordenes = int(row[1]) if row else 0
        ticket = ventas / ordenes if ordenes else 0.0
        return {"ventas_netas": ventas, "ordenes": ordenes, "ticket_promedio": ticket}

    def cost_of_goods(self, f) -> float:
        """Costo de ventas (COGS) del periodo, con costo robusto por línea."""
        where, params = _sales_where(f)
        row = self._one(
            f"SELECT COALESCE(SUM(dv.cantidad*{COST_LINE}),0) "
            "FROM v_detalles_venta_unificada dv JOIN v_ventas_unificada v ON v.id=dv.venta_id "
            f"{_COST_JOIN} "
            f"WHERE {where}", params)
        return float(row[0]) if row else 0.0

    # ── Chart series ──────────────────────────────────────────────────────────

    def by_branch(self, f) -> list[tuple[str, float]]:
        where, params = _sales_where(f)
        return [(r[0], float(r[1] or 0)) for r in self._q(
            "SELECT COALESCE(s.nombre,'(sin sucursal)') n, COALESCE(SUM(v.total),0) t "
            "FROM v_ventas_unificada v LEFT JOIN sucursales s ON s.id=v.sucursal_id "
            f"WHERE {where} GROUP BY v.sucursal_id ORDER BY t DESC LIMIT 12", params)]

    def top_products(self, f, limit: int = 10) -> list[tuple[str, float]]:
        where, params = _sales_where(f)
        return [(r[0], float(r[1] or 0)) for r in self._q(
            "SELECT COALESCE(p.name, dv.nombre,'—') n, SUM(dv.subtotal) ing "
            "FROM v_detalles_venta_unificada dv JOIN v_ventas_unificada v ON v.id=dv.venta_id "
            "LEFT JOIN products p ON p.id=dv.producto_id "
            f"WHERE {where} GROUP BY dv.producto_id ORDER BY ing DESC LIMIT ?",
            params + [limit])]

    def by_category(self, f) -> list[tuple[str, float]]:
        where, params = _sales_where(f)
        return [(r[0], float(r[1] or 0)) for r in self._q(
            "SELECT COALESCE(NULLIF(pcat.name,''),'(sin categoría)') c, SUM(dv.subtotal) ing "
            "FROM v_detalles_venta_unificada dv JOIN v_ventas_unificada v ON v.id=dv.venta_id "
            "LEFT JOIN products p ON p.id=dv.producto_id "
            "LEFT JOIN product_categories pcat ON pcat.id=p.category_id "
            f"WHERE {where} GROUP BY c ORDER BY ing DESC LIMIT 10", params)]

    def payment_methods(self, f) -> list[tuple[str, float]]:
        where, params = _sales_where(f)
        return [(r[0], float(r[1] or 0)) for r in self._q(
            "SELECT COALESCE(NULLIF(v.forma_pago,''),'Otro') m, COALESCE(SUM(v.total),0) t "
            f"FROM v_ventas_unificada v WHERE {where} GROUP BY m ORDER BY t DESC", params)]

    def peak_hours(self, f) -> list[tuple[str, float]]:
        where, params = _sales_where(f)
        return [(f"{r[0]}:00", float(r[1] or 0)) for r in self._q(
            "SELECT strftime('%H', v.fecha) h, COALESCE(SUM(v.total),0) t "
            f"FROM v_ventas_unificada v WHERE {where} GROUP BY h ORDER BY h", params)]

    def profitability_by_category(self, f) -> list[tuple[str, float, float]]:
        """(categoría, margen $, margen %) del periodo."""
        where, params = _sales_where(f)
        rows = self._q(
            f"SELECT COALESCE(NULLIF(pcat.name,''),'(sin categoría)') c, "
            "COALESCE(SUM(dv.subtotal),0) ing, "
            f"COALESCE(SUM(dv.cantidad*{COST_LINE}),0) cogs "
            "FROM v_detalles_venta_unificada dv JOIN v_ventas_unificada v ON v.id=dv.venta_id "
            "LEFT JOIN products p ON p.id=dv.producto_id "
            "LEFT JOIN product_categories pcat ON pcat.id=p.category_id "
            f"{_COST_JOIN} "
            f"WHERE {where} GROUP BY c ORDER BY (ing-cogs) DESC LIMIT 10", params)
        out = []
        for r in rows:
            ing = float(r[1] or 0)
            margen = ing - float(r[2] or 0)
            out.append((r[0], margen, (margen / ing * 100) if ing else 0.0))
        return out

    def monthly_evolution(self, year: str | None = None) -> dict:
        """Evolución mensual (ventas e utilidad bruta) del año dado o el actual."""
        yr = str(year) if year else None
        year_clause = "strftime('%Y', v.fecha)=?" if yr else \
            "strftime('%Y', v.fecha)=strftime('%Y','now')"
        params = [yr] if yr else []
        rows = self._q(
            "SELECT strftime('%m', v.fecha) mes, COALESCE(SUM(dv.subtotal),0) ing, "
            f"COALESCE(SUM(dv.cantidad*{COST_LINE}),0) cogs "
            "FROM v_ventas_unificada v JOIN v_detalles_venta_unificada dv ON dv.venta_id=v.id "
            f"{_COST_JOIN} "
            f"WHERE v.estado='completada' AND {year_clause} "
            "GROUP BY mes ORDER BY mes", params)
        meses = ["ene", "feb", "mar", "abr", "may", "jun",
                 "jul", "ago", "sep", "oct", "nov", "dic"]
        by = {r[0]: (float(r[1] or 0), float(r[2] or 0)) for r in rows}
        labels, ventas, utilidad = [], [], []
        for i in range(1, 13):
            ing, cogs = by.get(f"{i:02d}", (0.0, 0.0))
            labels.append(meses[i - 1])
            ventas.append(round(ing, 2))
            utilidad.append(round(ing - cogs, 2))
        return {"labels": labels, "ventas": ventas, "utilidad": utilidad}

    def top_customers(self, f, limit: int = 10) -> list[dict]:
        where, params = _sales_where(f)
        return [{"nombre": r[0], "visitas": int(r[1] or 0), "total": float(r[2] or 0)}
                for r in self._q(
            "SELECT COALESCE(c.nombre,'Público General') n, COUNT(v.id) vis, "
            "COALESCE(SUM(v.total),0) tot "
            "FROM v_ventas_unificada v LEFT JOIN clientes c ON c.id=v.cliente_id "
            f"WHERE {where} GROUP BY v.cliente_id ORDER BY tot DESC LIMIT ?",
            params + [limit])]
