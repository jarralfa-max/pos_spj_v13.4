# core/services/analytics/analytics_engine.py — SPJ ERP
"""
AnalyticsEngine — Motor de Inteligencia de Negocios Reactivo.

Prioridad 5 = BI/analytics (la más baja per convenio).
Reacciona a eventos y agrega datos en tablas bi_*.
Non-fatal: nunca cancela la operación que originó el evento.
"""
from __future__ import annotations
import json
import logging
from datetime import datetime

logger = logging.getLogger("spj.analytics_engine")

_PRIORITY = 5


class AnalyticsEngine:
    """Suscriptor de eventos que alimenta las tablas BI de agregación."""

    def __init__(self, db_conn):
        self._db = db_conn
        self._subscribed = False

    def wire(self) -> None:
        """Registra handlers en el EventBus. Idempotente."""
        if self._subscribed:
            return
        from core.events.event_bus import get_bus
        from core.events.domain_events import SALE_CREATED, PRODUCTION_EXECUTED

        bus = get_bus()
        bus.subscribe(SALE_CREATED, self.update_sales,
                      priority=_PRIORITY, label="analytics.sales")
        bus.subscribe(PRODUCTION_EXECUTED, self.update_yield,
                      priority=_PRIORITY, label="analytics.yield")
        self._subscribed = True
        logger.info("AnalyticsEngine wired (prio=%d)", _PRIORITY)

    def update_sales(self, data: dict) -> None:
        """SALE_CREATED → UPSERT en bi_sales_daily."""
        try:
            fecha = (data.get("fecha") or datetime.now().strftime("%Y-%m-%d"))[:10]
            sucursal_id = int(data.get("sucursal_id", 1))
            total = float(data.get("total", 0))
            if total <= 0:
                return

            self._db.execute("""
                INSERT INTO bi_sales_daily
                    (fecha, sucursal_id, total_ventas, num_transacciones, promedio_ticket)
                VALUES (?, ?, ?, 1, ?)
                ON CONFLICT(fecha, sucursal_id) DO UPDATE SET
                    total_ventas      = total_ventas + excluded.total_ventas,
                    num_transacciones = num_transacciones + 1,
                    promedio_ticket   = (total_ventas + excluded.total_ventas)
                                        / (num_transacciones + 1)
            """, (fecha, sucursal_id, total, total))
            try:
                self._db.commit()
            except Exception:
                pass
        except Exception as e:
            logger.warning("update_sales non-fatal: %s", e)

    def update_yield(self, data: dict) -> None:
        """PRODUCTION_EXECUTED → INSERT en bi_transformations."""
        try:
            fecha = (data.get("fecha") or datetime.now().strftime("%Y-%m-%d"))[:10]
            sucursal_id = int(data.get("sucursal_id", 1))
            # Soporta payload plano y anidado via DomainEvent.to_dict()
            nested = (data.get("data") or {})
            rendimiento = float(
                data.get("rendimiento_pct")
                or nested.get("rendimiento_pct")
                or data.get("yield_pct")
                or 0
            )
            categoria = (
                data.get("categoria")
                or nested.get("categoria")
                or data.get("tipo", "")
            )
            inputs_json  = json.dumps(
                data.get("inputs") or nested.get("inputs") or data.get("insumos", []),
                ensure_ascii=False,
            )
            outputs_json = json.dumps(
                data.get("outputs") or nested.get("outputs") or data.get("productos", []),
                ensure_ascii=False,
            )

            self._db.execute("""
                INSERT INTO bi_transformations
                    (fecha, sucursal_id, categoria, inputs_json,
                     outputs_json, rendimiento_pct)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (fecha, sucursal_id, categoria, inputs_json,
                  outputs_json, rendimiento))
            try:
                self._db.commit()
            except Exception:
                pass
        except Exception as e:
            logger.warning("update_yield non-fatal: %s", e)

    # ── BI Query API ─────────────────────────────────────────────────────────

    def sales_metrics(self, fecha: str, sucursal_id: int = 1) -> dict:
        """
        Returns aggregated sales metrics for a given date from bi_sales_daily.
        Falls back to computing from ventas table if bi table has no data yet.
        """
        try:
            row = self._db.execute(
                "SELECT total_ventas, num_transacciones, promedio_ticket "
                "FROM bi_sales_daily WHERE fecha=? AND sucursal_id=?",
                (fecha[:10], sucursal_id),
            ).fetchone()
            if row:
                return {
                    "fecha": fecha[:10],
                    "sucursal_id": sucursal_id,
                    "total_ventas": float(row[0] or 0),
                    "num_transacciones": int(row[1] or 0),
                    "promedio_ticket": float(row[2] or 0),
                    "fuente": "bi_sales_daily",
                }
        except Exception:
            pass
        # Fallback: aggregate from ventas table directly
        try:
            row2 = self._db.execute(
                "SELECT COALESCE(SUM(total),0), COUNT(*), "
                "COALESCE(AVG(total),0) FROM ventas "
                "WHERE DATE(fecha)=? AND sucursal_id=? AND estado='completada'",
                (fecha[:10], sucursal_id),
            ).fetchone()
            if row2:
                return {
                    "fecha": fecha[:10],
                    "sucursal_id": sucursal_id,
                    "total_ventas": float(row2[0]),
                    "num_transacciones": int(row2[1]),
                    "promedio_ticket": float(row2[2]),
                    "fuente": "ventas",
                }
        except Exception as e:
            logger.warning("sales_metrics fallback failed: %s", e)
        return {"fecha": fecha[:10], "sucursal_id": sucursal_id,
                "total_ventas": 0.0, "num_transacciones": 0, "promedio_ticket": 0.0,
                "fuente": "empty"}

    def product_profitability(
        self, fecha_ini: str, fecha_fin: str, sucursal_id: int = 1, limit: int = 20
    ) -> list:
        """
        Returns top products by margin for a date range.
        Reads from bi_product_profit if populated; falls back to detalles_venta.
        """
        try:
            rows = self._db.execute(
                "SELECT producto_id, SUM(ingresos) AS ing, SUM(costo) AS cos, "
                "SUM(margen) AS mar FROM bi_product_profit "
                "WHERE fecha BETWEEN ? AND ? "
                "GROUP BY producto_id ORDER BY mar DESC LIMIT ?",
                (fecha_ini[:10], fecha_fin[:10], limit),
            ).fetchall()
            if rows:
                return [
                    {"producto_id": r[0], "ingresos": float(r[1] or 0),
                     "costo": float(r[2] or 0), "margen": float(r[3] or 0),
                     "fuente": "bi_product_profit"}
                    for r in rows
                ]
        except Exception:
            pass
        # Fallback: compute from detalles_venta + productos
        try:
            rows2 = self._db.execute("""
                SELECT dv.producto_id,
                       SUM(dv.subtotal) AS ingresos,
                       SUM(dv.cantidad * COALESCE(p.costo,0)) AS costo,
                       SUM(dv.subtotal - dv.cantidad * COALESCE(p.costo,0)) AS margen
                FROM detalles_venta dv
                JOIN ventas v ON v.id = dv.venta_id
                LEFT JOIN productos p ON p.id = dv.producto_id
                WHERE DATE(v.fecha) BETWEEN ? AND ?
                  AND v.sucursal_id = ?
                  AND v.estado = 'completada'
                GROUP BY dv.producto_id
                ORDER BY margen DESC
                LIMIT ?
            """, (fecha_ini[:10], fecha_fin[:10], sucursal_id, limit)).fetchall()
            return [
                {"producto_id": r[0], "ingresos": float(r[1] or 0),
                 "costo": float(r[2] or 0), "margen": float(r[3] or 0),
                 "fuente": "detalles_venta"}
                for r in (rows2 or [])
            ]
        except Exception as e:
            logger.warning("product_profitability fallback failed: %s", e)
            return []

    def branch_ranking(self, fecha: str) -> list:
        """
        Returns branch ranking for a given date from bi_branch_ranking,
        or computes it from ventas if not yet populated.
        """
        try:
            rows = self._db.execute(
                "SELECT sucursal_id, rank_ventas, rank_margen, score "
                "FROM bi_branch_ranking WHERE fecha=? ORDER BY score DESC",
                (fecha[:10],),
            ).fetchall()
            if rows:
                return [
                    {"sucursal_id": r[0], "rank_ventas": r[1],
                     "rank_margen": r[2], "score": float(r[3] or 0)}
                    for r in rows
                ]
        except Exception:
            pass
        try:
            rows2 = self._db.execute(
                "SELECT sucursal_id, COALESCE(SUM(total),0) AS total_dia "
                "FROM ventas WHERE DATE(fecha)=? AND estado='completada' "
                "GROUP BY sucursal_id ORDER BY total_dia DESC",
                (fecha[:10],),
            ).fetchall()
            return [
                {"sucursal_id": r[0], "rank_ventas": i + 1,
                 "rank_margen": i + 1, "score": float(r[1] or 0)}
                for i, r in enumerate(rows2 or [])
            ]
        except Exception as e:
            logger.warning("branch_ranking fallback failed: %s", e)
            return []

    def inventory_intelligence(self, sucursal_id: int = 1, top: int = 10) -> dict:
        """
        Returns inventory health: low stock items + slow movers + top consumed.
        """
        result: dict = {"low_stock": [], "slow_movers": [], "top_consumed": []}
        try:
            result["low_stock"] = [
                dict(r) for r in self._db.execute(
                    "SELECT id, nombre, existencia, stock_minimo "
                    "FROM productos WHERE activo=1 AND stock_minimo > 0 "
                    "AND existencia <= stock_minimo ORDER BY existencia ASC LIMIT ?",
                    (top,)
                ).fetchall()
            ]
        except Exception as e:
            logger.warning("inventory_intelligence low_stock: %s", e)
        try:
            result["top_consumed"] = [
                {"producto_id": r[0], "total_consumido": float(r[1] or 0)}
                for r in self._db.execute(
                    "SELECT producto_id, SUM(cantidad) AS total "
                    "FROM movimientos_inventario "
                    "WHERE tipo='SALIDA' AND DATE(fecha) >= DATE('now','-30 days') "
                    "AND sucursal_id=? "
                    "GROUP BY producto_id ORDER BY total DESC LIMIT ?",
                    (sucursal_id, top)
                ).fetchall()
            ]
        except Exception as e:
            logger.warning("inventory_intelligence top_consumed: %s", e)
        return result

    def forecast(self, sucursal_id: int = 1, dias_proyeccion: int = 7) -> list:
        """
        Simple moving-average sales forecast for the next N days.
        Uses last 30 days of bi_sales_daily as training window.
        Returns a list of {fecha, proyeccion} dicts.
        """
        from datetime import date, timedelta
        try:
            rows = self._db.execute(
                "SELECT total_ventas FROM bi_sales_daily "
                "WHERE sucursal_id=? AND fecha >= DATE('now','-30 days') "
                "ORDER BY fecha DESC",
                (sucursal_id,),
            ).fetchall()
            if not rows:
                return []
            valores = [float(r[0] or 0) for r in rows]
            promedio = sum(valores) / len(valores) if valores else 0.0
            hoy = date.today()
            return [
                {"fecha": (hoy + timedelta(days=i + 1)).isoformat(),
                 "proyeccion": round(promedio, 2)}
                for i in range(dias_proyeccion)
            ]
        except Exception as e:
            logger.warning("forecast non-fatal: %s", e)
            return []
