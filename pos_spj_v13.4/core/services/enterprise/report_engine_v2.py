
# core/services/enterprise/report_engine_v2.py
# ── ReportEngineV2 — Motor de Reportes BI Completo ───────────────────────────
#
# Extiende ReportEngine original y agrega:
#   • get_sales_summary()       — resumen ejecutivo de ventas
#   • get_sales_by_product()    — ventas desglosadas por producto
#   • get_sales_by_branch()     — comparativo entre sucursales
#   • get_inventory_status()    — estado actual de inventario
#   • get_top_clients()         — ranking de clientes
#   • get_loss_report()         — reporte de mermas
#   • get_forecast_demand()     — predicción de demanda
#   • save_daily_snapshot()     — guarda snapshot en ventas_diarias
#   • KPIs corregidos (usa costo_unitario_real y activo)
#
# REGLA: ninguna UI ejecuta SQL directamente. Todo pasa por este engine.
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from core.services.enterprise.demand_forecasting import DemandForecastingEngine

logger = logging.getLogger("spj.report_engine_v2")


class ReportEngineV2:

    def __init__(self, db):
        self.db = db
        self._forecast = DemandForecastingEngine(db)

    def _now(self) -> str:
        return datetime.utcnow().isoformat()

    # ═════════════════════════════════════════════════════════════════════════
    # KPI CARDS (CORREGIDO)
    # ═════════════════════════════════════════════════════════════════════════

    def get_kpi_cards(
        self,
        branch_id: Optional[int],
        date_from: str,
        date_to: str,
    ) -> Dict:
        """KPIs ejecutivos — usa costo_unitario_real (columna real de DB)."""
        bf = "AND v.sucursal_id = ?" if branch_id else ""
        params_s = ([branch_id] if branch_id else []) + [date_from, date_to]

        sales_row = self.db.fetchone(f"""
            SELECT
                COALESCE(SUM(v.total), 0)                            AS total_revenue,
                COALESCE(SUM(dv.costo_unitario_real * dv.cantidad), 0) AS total_cost,
                COUNT(DISTINCT v.id)                                  AS ticket_count,
                COALESCE(SUM(dv.cantidad), 0)                         AS units_sold
            FROM ventas v
            JOIN detalles_venta dv ON dv.venta_id = v.id
            WHERE v.estado = 'completada' {bf}
              AND DATE(v.fecha) BETWEEN DATE(?) AND DATE(?)
        """, params_s)

        revenue     = float(sales_row["total_revenue"] or 0)
        cost        = float(sales_row["total_cost"] or 0)
        tickets     = int(sales_row["ticket_count"] or 0)
        units_sold  = float(sales_row["units_sold"] or 0)
        margin      = revenue - cost
        margin_pct  = (margin / revenue * 100) if revenue else 0
        avg_ticket  = (revenue / tickets) if tickets else 0

        # Clientes activos en el período
        clients_row = self.db.fetchone(f"""
            SELECT COUNT(DISTINCT v.cliente_id) AS active
            FROM ventas v
            WHERE v.estado='completada' AND v.cliente_id IS NOT NULL {bf}
              AND DATE(v.fecha) BETWEEN DATE(?) AND DATE(?)
        """, params_s)
        active_clients = int((clients_row["active"] or 0) if clients_row else 0)

        # Clientes nuevos registrados en el período
        new_row = self.db.fetchone("""
            SELECT COUNT(*) AS cnt FROM clientes
            WHERE activo=1 AND DATE(fecha_registro) BETWEEN DATE(?) AND DATE(?)
        """, (date_from, date_to))
        new_clients = int(new_row["cnt"] or 0) if new_row else 0

        # Inventario valor total (usa `activo` no `is_active`)
        inv_row = self.db.fetchone("""
            SELECT COALESCE(SUM(existencia * COALESCE(precio_compra,costo,0)), 0) AS inv_val
            FROM productos WHERE activo = 1
        """)
        inv_value = float(inv_row["inv_val"] or 0) if inv_row else 0

        # Mermas del período
        merma_row = self.db.fetchone(f"""
            SELECT COALESCE(SUM(m.cantidad), 0) AS total_merma
            FROM mermas m
            WHERE DATE(m.created_at) BETWEEN DATE(?) AND DATE(?)
            {("AND m.sucursal_id = ?" if branch_id else "")}
        """, [date_from, date_to] + ([branch_id] if branch_id else []))
        merma_total = float(merma_row["total_merma"] or 0) if merma_row else 0

        # Puntos de fidelidad
        pts_row = self.db.fetchone("""
            SELECT COALESCE(SUM(puntos), 0) AS pts
            FROM historico_puntos
            WHERE tipo='GANADOS'
              AND DATE(fecha) BETWEEN DATE(?) AND DATE(?)
        """, (date_from, date_to)) if self._has_col("historico_puntos", "fecha") else None
        points_issued = int(pts_row["pts"] or 0) if pts_row else 0

        return {
            "branch_id":        branch_id,
            "date_from":        date_from,
            "date_to":          date_to,
            "total_revenue":    round(revenue, 2),
            "total_cost":       round(cost, 2),
            "gross_margin":     round(margin, 2),
            "gross_margin_pct": round(margin_pct, 2),
            "ticket_count":     tickets,
            "avg_ticket":       round(avg_ticket, 2),
            "units_sold":       round(units_sold, 3),
            "inventory_value":  round(inv_value, 2),
            "active_clients":   active_clients,
            "new_clients":      new_clients,
            "merma_total":      round(merma_total, 3),
            "points_issued":    points_issued,
        }

    # ═════════════════════════════════════════════════════════════════════════
    # VENTAS
    # ═════════════════════════════════════════════════════════════════════════

    def get_sales_summary(
        self, branch_id: Optional[int], date_from: str, date_to: str
    ) -> List[Dict]:
        """Ventas diarias para gráfica de líneas/área."""
        bf = "AND v.sucursal_id = ?" if branch_id else ""
        params = ([branch_id] if branch_id else []) + [date_from, date_to]
        rows = self.db.fetchall(f"""
            SELECT
                DATE(v.fecha) AS dia,
                COALESCE(SUM(v.total), 0) AS revenue,
                COALESCE(SUM(dv.costo_unitario_real * dv.cantidad), 0) AS costo,
                COUNT(DISTINCT v.id) AS tickets,
                COUNT(DISTINCT v.cliente_id) AS clientes
            FROM ventas v
            LEFT JOIN detalles_venta dv ON dv.venta_id = v.id
            WHERE v.estado = 'completada' {bf}
              AND DATE(v.fecha) BETWEEN DATE(?) AND DATE(?)
            GROUP BY dia ORDER BY dia
        """, params)
        result = []
        for r in rows:
            rev = float(r["revenue"] or 0)
            costo = float(r["costo"] or 0)
            result.append({
                "dia": r["dia"],
                "revenue": round(rev, 2),
                "costo": round(costo, 2),
                "margen": round(rev - costo, 2),
                "margen_pct": round((rev - costo) / rev * 100 if rev else 0, 2),
                "tickets": int(r["tickets"] or 0),
                "clientes": int(r["clientes"] or 0),
            })
        return result

    def get_sales_by_product(
        self, branch_id: Optional[int], date_from: str, date_to: str,
        limit: int = 20
    ) -> List[Dict]:
        """Ventas por producto ordenadas por revenue."""
        bf = "AND v.sucursal_id = ?" if branch_id else ""
        params = ([branch_id] if branch_id else []) + [date_from, date_to, limit]
        rows = self.db.fetchall(f"""
            SELECT
                dv.producto_id,
                COALESCE(dv.nombre_producto, p.nombre, '?') AS nombre,
                p.unidad,
                c.nombre AS categoria,
                SUM(dv.cantidad)  AS qty,
                SUM(dv.subtotal)  AS revenue,
                SUM(dv.costo_unitario_real * dv.cantidad) AS costo,
                AVG(dv.precio_unitario) AS precio_prom
            FROM detalles_venta dv
            JOIN ventas v ON v.id = dv.venta_id
            LEFT JOIN productos p ON p.id = dv.producto_id
            LEFT JOIN categorias c ON c.id = p.categoria_id
            WHERE v.estado = 'completada' {bf}
              AND DATE(v.fecha) BETWEEN DATE(?) AND DATE(?)
            GROUP BY dv.producto_id
            ORDER BY revenue DESC LIMIT ?
        """, params)
        return [dict(r) for r in rows]

    def get_sales_by_branch(
        self, date_from: str, date_to: str
    ) -> List[Dict]:
        """Comparativo de ventas entre todas las sucursales."""
        rows = self.db.fetchall("""
            SELECT
                v.sucursal_id,
                COALESCE(s.nombre,'Sucursal '||v.sucursal_id) AS sucursal,
                COUNT(DISTINCT v.id)  AS tickets,
                SUM(v.total)          AS revenue,
                SUM(dv.costo_unitario_real * dv.cantidad) AS costo,
                COUNT(DISTINCT v.cliente_id) AS clientes
            FROM ventas v
            LEFT JOIN detalles_venta dv ON dv.venta_id = v.id
            LEFT JOIN sucursales s ON s.id = v.sucursal_id
            WHERE v.estado = 'completada'
              AND DATE(v.fecha) BETWEEN DATE(?) AND DATE(?)
            GROUP BY v.sucursal_id ORDER BY revenue DESC
        """, (date_from, date_to))
        result = []
        for r in rows:
            rev = float(r["revenue"] or 0)
            costo = float(r["costo"] or 0)
            result.append({
                "sucursal_id": r["sucursal_id"],
                "sucursal": r["sucursal"],
                "tickets": int(r["tickets"] or 0),
                "revenue": round(rev, 2),
                "costo": round(costo, 2),
                "margen": round(rev - costo, 2),
                "margen_pct": round((rev - costo) / rev * 100 if rev else 0, 2),
                "clientes": int(r["clientes"] or 0),
            })
        return result

    def get_top_products(
        self, branch_id: Optional[int], date_from: str, date_to: str,
        limit: int = 10
    ) -> List[Dict]:
        return self.get_sales_by_product(branch_id, date_from, date_to, limit)

    def get_product_margins(
        self, branch_id: Optional[int], date_from: str, date_to: str
    ) -> List[Dict]:
        """Márgenes reales por producto."""
        bf = "AND v.sucursal_id = ?" if branch_id else ""
        params = ([branch_id] if branch_id else []) + [date_from, date_to]
        rows = self.db.fetchall(f"""
            SELECT
                dv.producto_id,
                COALESCE(dv.nombre_producto, p.nombre) AS nombre,
                SUM(dv.subtotal) AS revenue,
                SUM(dv.costo_unitario_real * dv.cantidad) AS costo,
                SUM(dv.cantidad) AS qty
            FROM detalles_venta dv
            JOIN ventas v ON v.id = dv.venta_id
            LEFT JOIN productos p ON p.id = dv.producto_id
            WHERE v.estado = 'completada' {bf}
              AND DATE(v.fecha) BETWEEN DATE(?) AND DATE(?)
            GROUP BY dv.producto_id ORDER BY revenue DESC
        """, params)
        result = []
        for r in rows:
            rev = float(r["revenue"] or 0)
            cst = float(r["costo"] or 0)
            result.append({
                "producto_id": r["producto_id"],
                "nombre": r["nombre"],
                "revenue": round(rev, 2),
                "costo": round(cst, 2),
                "margen": round(rev - cst, 2),
                "margen_pct": round((rev - cst) / rev * 100 if rev else 0, 2),
                "qty": round(float(r["qty"] or 0), 3),
            })
        return result

    # ═════════════════════════════════════════════════════════════════════════
    # INVENTARIO
    # ═════════════════════════════════════════════════════════════════════════

    def get_inventory_status(
        self, branch_id: Optional[int] = None,
        categoria_id: Optional[int] = None,
    ) -> List[Dict]:
        """Estado completo de inventario con valor y alertas."""
        cat_f = "AND p.categoria_id = ?" if categoria_id else ""
        params = ([branch_id] if branch_id else []) + ([categoria_id] if categoria_id else [])

        if branch_id:
            rows = self.db.fetchall(f"""
                SELECT p.id, p.nombre, p.unidad, p.codigo,
                       COALESCE(ia.cantidad, p.existencia, 0) AS stock,
                       COALESCE(p.stock_minimo, 0) AS stock_min,
                       COALESCE(p.precio_compra, p.costo, 0) AS costo,
                       COALESCE(p.precio, 0) AS precio,
                       c.nombre AS categoria,
                       ia.ultima_actualizacion AS updated
                FROM productos p
                LEFT JOIN inventario_actual ia
                    ON ia.producto_id = p.id AND ia.sucursal_id = ?
                LEFT JOIN categorias c ON c.id = p.categoria_id
                WHERE p.activo=1 {cat_f}
                ORDER BY p.nombre
            """, params)
        else:
            rows = self.db.fetchall(f"""
        SELECT p.id, p.nombre, p.unidad, p.codigo,
                       COALESCE(p.existencia, 0) AS stock,
                       COALESCE(p.stock_minimo, 0) AS stock_min,
                       COALESCE(p.precio_compra, p.costo, 0) AS costo,
                       COALESCE(p.precio, 0) AS precio,
                       c.nombre AS categoria, NULL AS updated
                FROM productos p
                LEFT JOIN categorias c ON c.id = p.categoria_id
                WHERE p.activo=1 {cat_f}
                ORDER BY p.nombre
            """, params)

        result = []
        for r in rows:
            stock = float(r["stock"] or 0)
            min_s = float(r["stock_min"] or 0)
            costo = float(r["costo"] or 0)
            precio = float(r["precio"] or 0)
            valor = stock * costo
            if stock <= 0:
                alerta = "CRITICO"
            elif stock < min_s:
                alerta = "BAJO"
            else:
                alerta = "OK"
            result.append({
                "producto_id": r["id"],
                "nombre": r["nombre"],
                "codigo": r["codigo"],
                "unidad": r["unidad"],
                "categoria": r["categoria"],
                "stock": round(stock, 3),
                "stock_minimo": round(min_s, 3),
                "costo_unitario": round(costo, 2),
                "precio": round(precio, 2),
                "valor_inventario": round(valor, 2),
                "margen_potencial": round((precio - costo) * stock, 2),
                "alerta": alerta,
                "updated": r["updated"],
            })
        return result

    def get_inventory_rotation(
        self, branch_id: Optional[int], date_from: str, date_to: str
    ) -> List[Dict]:
        return self._forecast.get_rotacion_inventario(branch_id, date_from, date_to)

    # ═════════════════════════════════════════════════════════════════════════
    # CLIENTES
    # ═════════════════════════════════════════════════════════════════════════

    def get_top_clients(
        self, branch_id: Optional[int], date_from: str, date_to: str,
        limit: int = 20
    ) -> List[Dict]:
        """Ranking de clientes por compras acumuladas."""
        bf = "AND v.sucursal_id = ?" if branch_id else ""
        params = ([branch_id] if branch_id else []) + [date_from, date_to, limit]
        rows = self.db.fetchall(f"""
            SELECT
                c.id, c.nombre, c.apellido_paterno,
                c.telefono, c.email,
                COALESCE(c.puntos, 0) AS puntos,
                COUNT(DISTINCT v.id) AS num_compras,
                SUM(v.total) AS total_comprado,
                AVG(v.total) AS ticket_prom,
                MAX(DATE(v.fecha)) AS ultima_compra
            FROM ventas v
            JOIN clientes c ON c.id = v.cliente_id
            WHERE v.estado = 'completada' AND v.cliente_id IS NOT NULL {bf}
              AND DATE(v.fecha) BETWEEN DATE(?) AND DATE(?)
            GROUP BY c.id
            ORDER BY total_comprado DESC LIMIT ?
        """, params)
        result = []
        for r in rows:
            result.append({
                "cliente_id": r["id"],
                "nombre": f"{r['nombre'] or ''} {r['apellido_paterno'] or ''}".strip(),
                "telefono": r["telefono"],
                "email": r["email"],
                "puntos": int(r["puntos"] or 0),
                "num_compras": int(r["num_compras"] or 0),
                "total_comprado": round(float(r["total_comprado"] or 0), 2),
                "ticket_prom": round(float(r["ticket_prom"] or 0), 2),
                "ultima_compra": r["ultima_compra"],
            })
        return result

    def get_loyalty_impact(
        self, branch_id: Optional[int], date_from: str, date_to: str
    ) -> Dict:
        """Impacto del programa de fidelidad en ventas."""
        bf = "AND v.sucursal_id = ?" if branch_id else ""
        params = ([branch_id] if branch_id else []) + [date_from, date_to]
        rows = self.db.fetchall(f"""
            SELECT
                CASE WHEN v.cliente_id IS NOT NULL THEN 'con_fidelidad' ELSE 'sin_fidelidad' END AS seg,
                COUNT(DISTINCT v.id)  AS tickets,
                SUM(v.total)          AS revenue,
                AVG(v.total)          AS avg_ticket
            FROM ventas v
            WHERE v.estado='completada' {bf}
              AND DATE(v.fecha) BETWEEN DATE(?) AND DATE(?)
            GROUP BY seg
        """, params)
        result = {"con_fidelidad": {}, "sin_fidelidad": {}}
        for r in rows:
            result[r["seg"]] = {
                "tickets": int(r["tickets"] or 0),
                "revenue": round(float(r["revenue"] or 0), 2),
                "avg_ticket": round(float(r["avg_ticket"] or 0), 2),
            }
        # Incremento ticket promedio
        t_con = result["con_fidelidad"].get("avg_ticket", 0)
        t_sin = result["sin_fidelidad"].get("avg_ticket", 0)
        incremento = ((t_con - t_sin) / t_sin * 100) if t_sin else 0
        result["incremento_ticket_pct"] = round(incremento, 2)
        return result

    # ═════════════════════════════════════════════════════════════════════════
    # MERMAS
    # ═════════════════════════════════════════════════════════════════════════

    def get_loss_report(
        self, branch_id: Optional[int], date_from: str, date_to: str
    ) -> List[Dict]:
        """Reporte detallado de mermas con valor monetario estimado."""
        bf = "AND m.sucursal_id = ?" if branch_id else ""
        params = ([branch_id] if branch_id else []) + [date_from, date_to]
        rows = self.db.fetchall(f"""
            SELECT
                m.id, m.producto_id, m.cantidad, m.unidad,
                m.motivo, m.usuario, m.created_at,
                p.nombre AS producto, s.nombre AS sucursal,
                COALESCE(p.precio_compra, p.costo, 0) AS costo_unit,
                COALESCE(p.precio, 0) AS precio_unit
            FROM mermas m
            LEFT JOIN productos p ON p.id = m.producto_id
            LEFT JOIN sucursales s ON s.id = m.sucursal_id
            WHERE DATE(m.created_at) BETWEEN DATE(?) AND DATE(?) {bf}
            ORDER BY m.created_at DESC
        """, params)
        result = []
        for r in rows:
            cant = float(r["cantidad"] or 0)
            result.append({
                "id": r["id"],
                "producto": r["producto"],
                "sucursal": r["sucursal"],
                "cantidad": round(cant, 3),
                "unidad": r["unidad"],
                "motivo": r["motivo"],
                "usuario": r["usuario"],
                "fecha": str(r["created_at"] or "")[:16],
                "valor_costo": round(cant * float(r["costo_unit"] or 0), 2),
                "valor_venta": round(cant * float(r["precio_unit"] or 0), 2),
            })
        return result

    def get_loss_summary(
        self, branch_id: Optional[int], date_from: str, date_to: str
    ) -> Dict:
        """Resumen de mermas por producto."""
        bf = "AND m.sucursal_id = ?" if branch_id else ""
        params = ([branch_id] if branch_id else []) + [date_from, date_to]
        rows = self.db.fetchall(f"""
            SELECT m.producto_id, p.nombre,
                   SUM(m.cantidad) AS total_qty,
                   COUNT(m.id) AS num_eventos,
                   SUM(m.cantidad * COALESCE(p.precio_compra, p.costo, 0)) AS valor_perdido
            FROM mermas m
            LEFT JOIN productos p ON p.id = m.producto_id
            WHERE DATE(m.created_at) BETWEEN DATE(?) AND DATE(?) {bf}
            GROUP BY m.producto_id ORDER BY valor_perdido DESC
        """, params)
        items = [dict(r) for r in rows]
        total_valor = sum(float(r.get("valor_perdido") or 0) for r in items)
        return {"items": items, "total_valor": round(total_valor, 2)}

    # ═════════════════════════════════════════════════════════════════════════
    # PRODUCCIÓN
    # ═════════════════════════════════════════════════════════════════════════

    def get_production_report(
        self, branch_id: Optional[int], date_from: str, date_to: str
    ) -> List[Dict]:
        """Reporte de producciones: receta, tipo, entradas, salidas."""
        bf = "AND p.sucursal_id = ?" if branch_id else ""
        params = ([branch_id] if branch_id else []) + [date_from, date_to]
        rows = self.db.fetchall(f"""
            SELECT p.id, p.fecha, r.nombre AS receta, r.tipo_receta,
                   p.cantidad_base, p.unidad_base, p.usuario,
                   COUNT(pd.id) AS num_items,
                   SUM(CASE WHEN pd.tipo='entrada' THEN pd.cantidad_generada ELSE 0 END) AS gen,
                   SUM(CASE WHEN pd.tipo='salida'  THEN pd.cantidad_generada ELSE 0 END) AS cons
            FROM producciones p
            JOIN recetas r ON r.id = p.receta_id
            LEFT JOIN produccion_detalle pd ON pd.produccion_id = p.id
            WHERE DATE(p.fecha) BETWEEN DATE(?) AND DATE(?) {bf}
            GROUP BY p.id ORDER BY p.fecha DESC
        """, params)
        return [dict(r) for r in rows]

    # ═════════════════════════════════════════════════════════════════════════
    # PREDICCIÓN
    # ═════════════════════════════════════════════════════════════════════════

    def get_forecast_demand(
        self, branch_id: Optional[int], top_n: int = 20
    ) -> List[Dict]:
        """Lista simplificada de forecasts para tabla UI."""
        forecasts = self._forecast.forecast_all(branch_id, top_n=top_n)
        return [
            {
                "producto_id": f.producto_id,
                "nombre": f.producto_nombre,
                "unidad": f.unidad,
                "wma_7": f.wma_7,
                "sma_14": f.sma_14,
                "sma_30": f.sma_30,
                "tendencia": f.tendencia,
                "tendencia_pct": f.tendencia_pct,
                "stock_actual": f.stock_actual,
                "dias_cobertura": f.dias_cobertura,
                "compra_sugerida": f.compra_sugerida_7d,
                "alerta": f.alerta,
                "pico_semana": f.pico_semana,
            }
            for f in forecasts
        ]

    def get_alertas_inventario(
        self, branch_id: Optional[int] = None
    ) -> List[Dict]:
        alertas = self._forecast.get_alertas_inventario(branch_id)
        return [vars(a) for a in alertas]

    # ═════════════════════════════════════════════════════════════════════════
    # SNAPSHOT DIARIO
    # ═════════════════════════════════════════════════════════════════════════

    def save_daily_snapshot(
        self,
        branch_id: int,
        snapshot_date: Optional[str] = None,
        conn=None,
    ) -> None:
        """Guarda snapshot de ventas del día en ventas_diarias."""
        d = snapshot_date or date.today().isoformat()
        kpis = self.get_kpi_cards(branch_id, d, d)
        c = conn or self.db.conn
        c.execute("""
            INSERT INTO ventas_diarias (
                fecha, sucursal_id, total_ventas, total_costo,
                num_tickets, num_clientes, ticket_promedio,
                margen_bruto, margen_pct, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,datetime('now'))
            ON CONFLICT(fecha, sucursal_id) DO UPDATE SET
                total_ventas = excluded.total_ventas,
                total_costo  = excluded.total_costo,
                num_tickets  = excluded.num_tickets,
                num_clientes = excluded.num_clientes,
                ticket_promedio = excluded.ticket_promedio,
                margen_bruto = excluded.margen_bruto,
                margen_pct   = excluded.margen_pct,
                updated_at   = datetime('now')
        """, (
            d, branch_id,
            kpis["total_revenue"], kpis["total_cost"],
            kpis["ticket_count"], kpis["active_clients"],
            kpis["avg_ticket"], kpis["gross_margin"], kpis["gross_margin_pct"],
        ))

    def get_daily_sales(
        self, branch_id: Optional[int], date_from: str, date_to: str
    ) -> List[Dict]:
        return self.get_sales_summary(branch_id, date_from, date_to)

    def get_branch_comparison(
        self, date_from: str, date_to: str
    ) -> List[Dict]:
        return self.get_sales_by_branch(date_from, date_to)

    # ═════════════════════════════════════════════════════════════════════════
    # HISTÓRICO COMPARATIVO
    # ═════════════════════════════════════════════════════════════════════════

    def get_historical_comparison(
        self, branch_id: Optional[int], date_from: str, date_to: str
    ) -> Dict:
        """Compara período actual vs período anterior de igual duración."""
        d1 = datetime.strptime(date_from, "%Y-%m-%d").date()
        d2 = datetime.strptime(date_to, "%Y-%m-%d").date()
        delta = d2 - d1
        prev_to   = (d1 - timedelta(days=1)).isoformat()
        prev_from = (d1 - timedelta(days=delta.days + 1)).isoformat()

        current = self.get_kpi_cards(branch_id, date_from, date_to)
        previous = self.get_kpi_cards(branch_id, prev_from, prev_to)

        def pct(a, b): return round((a - b) / b * 100, 2) if b else 0

        return {
            "current":  current,
            "previous": previous,
            "prev_from": prev_from,
            "prev_to":   prev_to,
            "revenue_change_pct":  pct(current["total_revenue"],    previous["total_revenue"]),
            "margin_change_pct":   pct(current["gross_margin"],      previous["gross_margin"]),
            "tickets_change_pct":  pct(current["ticket_count"],      previous["ticket_count"]),
            "clients_change_pct":  pct(current["active_clients"],    previous["active_clients"]),
        }

    # ═════════════════════════════════════════════════════════════════════════
    # HELPERS
    # ═════════════════════════════════════════════════════════════════════════

    def _has_col(self, tabla: str, col: str) -> bool:
        try:
            cols = {r["name"] for r in self.db.fetchall(f"PRAGMA table_info({tabla})")}
            return col in cols
        except Exception:
            return False
