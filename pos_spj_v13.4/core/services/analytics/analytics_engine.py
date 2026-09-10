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

    def get_dashboard_data(self, branch_id: int, rango: str = 'hoy') -> dict:
        """
        Construye el paquete completo de datos para el Dashboard.
        Unifica: BIService.get_dashboard_data() + BIRepository queries.
        Cache strategy:
          - 'hoy'   → usa ventas_diarias (agregados) + caché 60s en memoria
          - 'semana'/'mes' → caché 5 min (datos históricos no cambian frecuente)
        """
        import time
        from datetime import datetime, timedelta

        # ── Caché en memoria ──────────────────────────────────────────────
        cache_key = f"{branch_id}:{rango}"
        ttl = 60 if rango == 'hoy' else 300
        now = time.monotonic()
        if cache_key in self._cache:
            if now - self._cache_ts.get(cache_key, 0) < ttl:
                logger.debug("BI cache HIT: %s", cache_key)
                return self._cache[cache_key]

        # ── Calcular fechas ───────────────────────────────────────────────
        hoy = datetime.now()
        if rango == 'hoy':
            fecha_inicio = fecha_fin = hoy.strftime('%Y-%m-%d')
        elif rango == 'semana':
            fecha_inicio = (hoy - timedelta(days=hoy.weekday())).strftime('%Y-%m-%d')
            fecha_fin = hoy.strftime('%Y-%m-%d')
        elif rango == 'mes':
            fecha_inicio = hoy.replace(day=1).strftime('%Y-%m-%d')
            fecha_fin = hoy.strftime('%Y-%m-%d')
        else:
            fecha_inicio = fecha_fin = hoy.strftime('%Y-%m-%d')

        # ── Intentar leer desde ventas_diarias (tabla de agregados) ──────
        try:
            if rango == 'hoy':
                row = self._db.execute("""
                    SELECT COALESCE(SUM(total_ventas),0),
                           COALESCE(SUM(num_transacciones),0),
                           COALESCE(AVG(promedio_ticket),0),
                           COALESCE(SUM(clientes_nuevos),0)
                    FROM bi_sales_daily
                    WHERE fecha=? AND sucursal_id=?
                """, (fecha_inicio, branch_id)).fetchone()
                if row and float(row[0]) > 0:
                    kpis_fast = {
                        'ingresos_totales': float(row[0]),
                        'total_tickets':    int(row[1]),
                        'ticket_promedio':  float(row[2]),
                        'clientes_unicos':  int(row[3]) if row[3] else 0,
                    }
                    dashboard = {
                        'periodo':            f"{fecha_inicio} al {fecha_fin}",
                        'fuente':             'bi_sales_daily',
                        'kpis': {
                            'ingresos':         kpis_fast['ingresos_totales'],
                            'tickets':          kpis_fast['total_tickets'],
                            'ticket_promedio':  kpis_fast['ticket_promedio'],
                            'clientes_unicos':  kpis_fast['clientes_unicos'],
                        },
                        'ventas_por_hora':      self.get_ventas_por_hora(
                            branch_id, fecha_inicio, fecha_fin),
                        'top_productos':        self.get_ranking_productos(
                            branch_id, fecha_inicio, fecha_fin, limite=5, orden='DESC'),
                        'productos_lentos':     self.get_ranking_productos(
                            branch_id, fecha_inicio, fecha_fin, limite=5, orden='ASC'),
                        'clientes_recurrentes': self.get_clientes_recurrentes(
                            branch_id, fecha_inicio, fecha_fin),
                    }
                    self._cache[cache_key] = dashboard
                    self._cache_ts[cache_key] = now
                    logger.debug("BI desde bi_sales_daily: %s", cache_key)
                    return dashboard
        except Exception as e:
            logger.debug("bi_sales_daily no disponible, calculando en tiempo real: %s", e)

        # ── Fallback: calcular desde ventas (tiempo real) ─────────────────
        try:
            kpis = self._get_kpis_generales(branch_id, fecha_inicio, fecha_fin)
            dashboard = {
                'periodo': f"{fecha_inicio} al {fecha_fin}",
                'fuente':  'tiempo_real',
                'kpis': {
                    'ingresos':         kpis.get('ingresos_totales') or 0.0,
                    'tickets':          kpis.get('total_tickets') or 0,
                    'ticket_promedio':  kpis.get('ticket_promedio') or 0.0,
                    'clientes_unicos':  kpis.get('clientes_unicos') or 0,
                },
                'ventas_por_hora':      self.get_ventas_por_hora(
                    branch_id, fecha_inicio, fecha_fin),
                'top_productos':        self.get_ranking_productos(
                    branch_id, fecha_inicio, fecha_fin, limite=5, orden='DESC'),
                'productos_lentos':     self.get_ranking_productos(
                    branch_id, fecha_inicio, fecha_fin, limite=5, orden='ASC'),
                'clientes_recurrentes': self.get_clientes_recurrentes(
                    branch_id, fecha_inicio, fecha_fin),
            }
            # Comparativa vs período anterior
            try:
                dashboard['comparativa'] = self._get_comparativa(branch_id, rango)
            except Exception:
                dashboard['comparativa'] = {}

            self._cache[cache_key] = dashboard
            self._cache_ts[cache_key] = now
            return dashboard
        except Exception as e:
            logger.error("Fallo al generar Dashboard BI para sucursal %d: %s", branch_id, e)
            raise RuntimeError("No se pudo generar el reporte analítico.")

    _cache: dict = {}
    _cache_ts: dict = {}

    def _get_kpis_generales(self, sucursal_id: int, fecha_inicio: str, fecha_fin: str) -> dict:
        """Obtiene Total de Ventas, Ticket Promedio y Cantidad de Clientes."""
        query = """
            SELECT 
                COUNT(id) as total_tickets,
                SUM(total) as ingresos_totales,
                AVG(total) as ticket_promedio,
                COUNT(DISTINCT cliente_id) as clientes_unicos
            FROM __SRC_H__ 
            WHERE sucursal_id = ? AND estado = 'completada'
            AND date(fecha) BETWEEN date(?) AND date(?)
        """
        row = self._db.execute(query, (sucursal_id, fecha_inicio, fecha_fin)).fetchone()
        return dict(row) if row else {'total_tickets': 0, 'ingresos_totales': 0, 'ticket_promedio': 0, 'clientes_unicos': 0}

    def get_ventas_por_hora(self, sucursal_id: int, fecha_inicio: str, fecha_fin: str) -> list:
        """Agrupa las ventas según la hora del día para detectar 'Horas Pico'."""
        query = """
            SELECT 
                strftime('%H', fecha) as hora,
                COUNT(id) as cantidad_ventas,
                SUM(total) as ingresos
            FROM __SRC_H__
            WHERE sucursal_id = ? AND estado = 'completada'
            AND date(fecha) BETWEEN date(?) AND date(?)
            GROUP BY hora
            ORDER BY hora ASC
        """
        return [dict(row) for row in self._db.execute(query, (sucursal_id, fecha_inicio, fecha_fin)).fetchall()]

    def get_ranking_productos(self, sucursal_id: int, fecha_inicio: str, fecha_fin: str, limite: int = 10, orden: str = 'DESC') -> list:
        """
        Obtiene los productos Más Vendidos (DESC) o los Lentos/Menos Vendidos (ASC).
        """
        query = f"""
            SELECT 
                p.nombre,
                SUM(d.cantidad) as cantidad_vendida,
                SUM(d.subtotal) as ingresos_generados
            FROM __SRC_L__ d
            JOIN __SRC_H__ v ON d.venta_id = v.id
            JOIN productos p ON d.producto_id = p.id
            WHERE v.sucursal_id = ? AND v.estado = 'completada'
            AND date(v.fecha) BETWEEN date(?) AND date(?)
            GROUP BY p.id, p.nombre
            ORDER BY cantidad_vendida {orden}
            LIMIT ?
        """
        return [dict(row) for row in self._db.execute(query, (sucursal_id, fecha_inicio, fecha_fin, limite)).fetchall()]

    def get_clientes_recurrentes(self, sucursal_id: int, fecha_inicio: str, fecha_fin: str) -> list:
        """Identifica a los VIPs: Clientes que más veces han comprado y más han gastado."""
        query = """
            SELECT 
                c.nombre,
                COUNT(v.id) as visitas,
                SUM(v.total) as valor_vida
            FROM __SRC_H__ v
            JOIN clientes c ON v.cliente_id = c.id
            WHERE v.sucursal_id = ? AND v.estado = 'completada' AND c.nombre != 'Público General'
            AND date(v.fecha) BETWEEN date(?) AND date(?)
            GROUP BY c.id, c.nombre
            ORDER BY valor_vida DESC
            LIMIT 10
        """
        return [dict(row) for row in self._db.execute(query, (sucursal_id, fecha_inicio, fecha_fin)).fetchall()]



    def _get_comparativa(self, sucursal_id: int, rango: str) -> dict:
        """KPIs del período anterior: hoy→ayer, semana→semana pasada, mes→mes pasado."""
        from datetime import date, timedelta
        hoy = date.today()
        if rango == 'hoy':
            fi = ff = (hoy - timedelta(days=1)).isoformat()
        elif rango == 'semana':
            ff = (hoy - timedelta(days=7)).isoformat()
            fi = (hoy - timedelta(days=14)).isoformat()
        else:
            ff = (hoy - timedelta(days=30)).isoformat()
            fi = (hoy - timedelta(days=60)).isoformat()
        kpis = self._get_kpis_generales(sucursal_id, fi, ff)
        return {
            'ingresos':    float(kpis.get('ingresos_totales') or 0),
            'num_ventas':  int(kpis.get('total_tickets') or 0),
            'ticket_prom': float(kpis.get('ticket_promedio') or 0),
            'periodo':     f"{fi} → {ff}",
        }

    def invalidar_cache(self, branch_id: int = None) -> None:
        """Invalida el caché tras una venta (llamado desde EventBus)."""
        if branch_id:
            key = f"{branch_id}:hoy"
            self._cache.pop(key, None)
            self._cache_ts.pop(key, None)
        else:
            self._cache.clear()
            self._cache_ts.clear()
