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
        # Este motor sirve la pantalla VIVA de Inteligencia de Negocios
        # (`modulos/reportes_bi_v2.py`, slot INTELIGENCIA_BI). Sus consultas
        # leían `ventas`/`detalles_venta`, así que el BI que el usuario abre
        # no veía NINGUNA venta del POS: desde SALES-19..22 nacen en el
        # agregado canónico `sales` y no pasan por la tabla legacy.
        #
        # Las 21 consultas llevan los marcadores `__SRC_H__`/`__SRC_L__` y esta
        # envoltura los resuelve a las vistas unificadas (256/257), o a la
        # tabla legacy si la base aún no las tiene. Se hace en un único punto
        # y no convirtiendo 21 literales a f-string: varios ya interpolan
        # otras piezas con f-string o `.format()`, y un marcador con LLAVES
        # colisionaba con ambos (se comprobó: KeyError '_SRC_L' en
        # `product_profitability`). Por eso el marcador no lleva llaves.
        from backend.infrastructure.db.sales_read_source import (
            SalesSourceRewritingConnection,
        )

        self._db = SalesSourceRewritingConnection(db_conn)
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
            sucursal_id = str(data.get("sucursal_id") or "")  # branch UUIDv7 (sin int cast)
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
            sucursal_id = str(data.get("sucursal_id") or "")  # branch UUIDv7 (sin int cast)
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

            from backend.shared.ids import new_uuid
            self._db.execute("""
                INSERT INTO bi_transformations
                    (id, fecha, sucursal_id, categoria, inputs_json,
                     outputs_json, rendimiento_pct)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (new_uuid(), fecha, sucursal_id, categoria, inputs_json,
                  outputs_json, rendimiento))
            try:
                self._db.commit()
            except Exception:
                pass
        except Exception as e:
            logger.warning("update_yield non-fatal: %s", e)

    # ── BI Query API ─────────────────────────────────────────────────────────


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
            prod_cols = set()
            try:
                prod_cols = {r[1] for r in self._db.execute("PRAGMA table_info(productos)").fetchall()}
            except Exception:
                prod_cols = set()
            if "costo" in prod_cols:
                costo_expr = "COALESCE(p.costo, 0)"
            elif "precio_compra" in prod_cols:
                costo_expr = "COALESCE(p.precio_compra, 0)"
            elif "costo_promedio" in prod_cols:
                costo_expr = "COALESCE(p.costo_promedio, 0)"
            else:
                costo_expr = "0"
            rows2 = self._db.execute("""
                SELECT dv.producto_id,
                       SUM(dv.subtotal) AS ingresos,
                       SUM(dv.cantidad * {costo_expr}) AS costo,
                       SUM(dv.subtotal - dv.cantidad * {costo_expr}) AS margen
                FROM __SRC_L__ dv
                JOIN __SRC_H__ v ON v.id = dv.venta_id
                LEFT JOIN productos p ON p.id = dv.producto_id
                WHERE DATE(v.fecha) BETWEEN ? AND ?
                  AND v.sucursal_id = ?
                  AND v.estado = 'completada'
                GROUP BY dv.producto_id
                ORDER BY margen DESC
                LIMIT ?
            """.format(costo_expr=costo_expr), (fecha_ini[:10], fecha_fin[:10], sucursal_id, limit)).fetchall()
            return [
                {"producto_id": r[0], "ingresos": float(r[1] or 0),
                 "costo": float(r[2] or 0), "margen": float(r[3] or 0),
                 "fuente": "detalles_venta"}
                for r in (rows2 or [])
            ]
        except Exception as e:
            logger.warning("product_profitability fallback failed: %s", e)
            return []

    # Expresión de costo robusta reutilizable: prioriza el costo real capturado
    # en la venta y cae a las columnas de costo del producto (born-clean).
    _COSTO_LINE = ("COALESCE(NULLIF(dv.costo_unitario_real,0), "
                   "NULLIF(p.costo,0), NULLIF(p.precio_compra,0), "
                   "NULLIF(p.costo_promedio,0), 0)")




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
            # P2 repoint: lee el ledger canónico (inventory_ledger/_lines) en vez
            # de la tabla legacy movimientos_inventario. "SALIDA" = los tipos de
            # movimiento canónicos con dirección DECREASE (§ MOVEMENT_DIRECTION).
            result["top_consumed"] = [
                {"producto_id": r[0], "total_consumido": float(r[1] or 0)}
                for r in self._db.execute(
                    "SELECT l.product_id, SUM(CAST(l.quantity AS REAL)) AS total "
                    "FROM inventory_ledger_lines l "
                    "JOIN inventory_ledger m ON m.id = l.movement_id "
                    "WHERE m.movement_type IN ('SALE_ISSUE','TRANSFER_DISPATCH',"
                    "'PRODUCTION_CONSUMPTION','SLAUGHTER_INPUT_FUTURE',"
                    "'ADJUSTMENT_OUT','WASTE','SHRINKAGE','EXPIRY_DISPOSAL',"
                    "'SUPPLIER_RETURN') "
                    "AND DATE(m.occurred_at) >= DATE('now','-30 days') "
                    "AND m.branch_id=? "
                    "GROUP BY l.product_id ORDER BY total DESC LIMIT ?",
                    (str(sucursal_id), top)
                ).fetchall()
            ]
        except Exception as e:
            logger.warning("inventory_intelligence top_consumed: %s", e)
        return result


    # ── Unified BI Dashboard API (consolida BIService + BIRepository) ────────


    _cache: dict = {}
    _cache_ts: dict = {}








    def invalidar_cache(self, branch_id: int = None) -> None:
        """Invalida el caché tras una venta (llamado desde EventBus)."""
        if branch_id:
            key = f"{branch_id}:hoy"
            self._cache.pop(key, None)
            self._cache_ts.pop(key, None)
        else:
            self._cache.clear()
            self._cache_ts.clear()
