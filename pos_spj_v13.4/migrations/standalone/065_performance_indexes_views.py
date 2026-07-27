# migrations/standalone/065_performance_indexes_views.py — SPJ ERP
"""
Migration 065 — Performance indexes + SQL views for BI.

Adds covering indexes on hot tables (ventas, detalles_venta,
movimientos_inventario, asientos_contables) and creates non-materialized
SQL views used by AnalyticsEngine, BIService, and dashboard queries.

All operations are idempotent:
  - Indexes: CREATE INDEX IF NOT EXISTS
  - Views:   CREATE VIEW IF NOT EXISTS
"""
import logging

logger = logging.getLogger("spj.migrations.065")


def run(conn):
    stmts = [
        # ── ventas ──────────────────────────────────────────────────────
        "CREATE INDEX IF NOT EXISTS idx_ventas_fecha_suc "
        "ON ventas (DATE(fecha), sucursal_id)",

        "CREATE INDEX IF NOT EXISTS idx_ventas_cliente "
        "ON ventas (cliente_id)",

        "CREATE INDEX IF NOT EXISTS idx_ventas_estado "
        "ON ventas (estado)",

        # ── detalles_venta ───────────────────────────────────────────────
        "CREATE INDEX IF NOT EXISTS idx_dv_venta "
        "ON detalles_venta (venta_id)",

        "CREATE INDEX IF NOT EXISTS idx_dv_producto "
        "ON detalles_venta (producto_id)",

        # ── movimientos_inventario ────────────────────────────────────────
        "CREATE INDEX IF NOT EXISTS idx_mov_producto_fecha "
        "ON movimientos_inventario (producto_id, DATE(fecha))",

        "CREATE INDEX IF NOT EXISTS idx_mov_sucursal "
        "ON movimientos_inventario (sucursal_id)",

        "CREATE INDEX IF NOT EXISTS idx_mov_tipo "
        "ON movimientos_inventario (tipo)",

        # ── financial_event_log ───────────────────────────────────────────
        "CREATE INDEX IF NOT EXISTS idx_fel_fecha "
        "ON financial_event_log (DATE(timestamp))",

        "CREATE INDEX IF NOT EXISTS idx_fel_cuenta_debe "
        "ON financial_event_log (cuenta_debe)",

        "CREATE INDEX IF NOT EXISTS idx_fel_cuenta_haber "
        "ON financial_event_log (cuenta_haber)",

        "CREATE INDEX IF NOT EXISTS idx_fel_evento "
        "ON financial_event_log (evento)",

        # ── bi tables ─────────────────────────────────────────────────────
        "CREATE INDEX IF NOT EXISTS idx_bi_sales_fecha "
        "ON bi_sales_daily (fecha)",

        "CREATE INDEX IF NOT EXISTS idx_bi_prod_profit_fecha "
        "ON bi_product_profit (fecha)",
    ]

    for stmt in stmts:
        try:
            conn.execute(stmt)
            logger.info("065: %s", stmt[:60])
        except Exception as e:
            # Index may fail if table doesn't exist — skip gracefully
            logger.warning("065 index skip: %s | %s", stmt[:60], e)

    # ── SQL Views ────────────────────────────────────────────────────────────
    views = {
        "v_ventas_diarias": """
            CREATE VIEW IF NOT EXISTS v_ventas_diarias AS
            SELECT
                DATE(fecha)                  AS fecha,
                sucursal_id,
                COUNT(*)                     AS num_ventas,
                COALESCE(SUM(total), 0)      AS total_dia,
                COALESCE(AVG(total), 0)      AS ticket_promedio,
                COUNT(DISTINCT cliente_id)   AS clientes_unicos
            FROM ventas
            WHERE estado = 'completada'
            GROUP BY DATE(fecha), sucursal_id
        """,

        "v_rentabilidad_productos": """
            CREATE VIEW IF NOT EXISTS v_rentabilidad_productos AS
            SELECT
                dv.producto_id,
                p.nombre                                          AS producto_nombre,
                COALESCE(SUM(dv.subtotal), 0)                    AS ingresos_totales,
                COALESCE(SUM(dv.cantidad * COALESCE(p.costo, 0)), 0) AS costo_total,
                COALESCE(SUM(dv.subtotal
                    - dv.cantidad * COALESCE(p.costo, 0)), 0)    AS margen_total,
                CASE
                    WHEN SUM(dv.subtotal) > 0
                    THEN ROUND(
                        SUM(dv.subtotal - dv.cantidad * COALESCE(p.costo, 0))
                        / SUM(dv.subtotal) * 100, 2)
                    ELSE 0
                END                                               AS margen_pct
            FROM detalles_venta dv
            JOIN ventas v ON v.id = dv.venta_id
            LEFT JOIN productos p ON p.id = dv.producto_id
            WHERE v.estado = 'completada'
            GROUP BY dv.producto_id
        """,

        "v_stock_critico": """
            CREATE VIEW IF NOT EXISTS v_stock_critico AS
            SELECT
                id,
                nombre,
                existencia,
                stock_minimo,
                CASE
                    WHEN existencia <= 0          THEN 'AGOTADO'
                    WHEN existencia <= stock_minimo THEN 'CRITICO'
                    WHEN existencia <= stock_minimo * 2 THEN 'BAJO'
                    ELSE 'OK'
                END AS estado_stock
            FROM productos
            WHERE activo = 1 AND stock_minimo > 0
            ORDER BY existencia ASC
        """,

        "v_flujo_caja_diario": """
            CREATE VIEW IF NOT EXISTS v_flujo_caja_diario AS
            SELECT
                DATE(fecha) AS fecha,
                sucursal_id,
                SUM(CASE WHEN tipo_movimiento = 'ingreso' THEN monto ELSE 0 END)
                    AS ingresos,
                SUM(CASE WHEN tipo_movimiento = 'egreso' THEN monto ELSE 0 END)
                    AS egresos,
                SUM(CASE WHEN tipo_movimiento = 'ingreso' THEN monto ELSE -monto END)
                    AS flujo_neto
            FROM treasury_ledger
            GROUP BY DATE(fecha), sucursal_id
        """,
    }

    for view_name, ddl in views.items():
        try:
            conn.execute(ddl)
            logger.info("065: view %s creada/confirmada", view_name)
        except Exception as e:
            logger.warning("065 view %s skip: %s", view_name, e)

    try:
        conn.commit()
    except Exception:
        pass
