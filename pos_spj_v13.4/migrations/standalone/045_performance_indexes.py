# migrations/standalone/045_performance_indexes.py — SPJ POS v13
"""
Migración 045 — Índices de rendimiento para tablas calientes.
"""
import logging
logger = logging.getLogger(__name__)

VERSION     = "045"
DESCRIPTION = "Índices de rendimiento: detalles_venta, productos, ventas, movimientos_inventario"

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_dv_venta_id ON detalles_venta(venta_id)",
    "CREATE INDEX IF NOT EXISTS idx_dv_producto_id ON detalles_venta(producto_id)",
    "CREATE INDEX IF NOT EXISTS idx_dv_producto_fecha ON detalles_venta(producto_id, venta_id)",
    "CREATE INDEX IF NOT EXISTS idx_prod_activo_nombre ON productos(activo, nombre) WHERE activo = 1",
    "CREATE INDEX IF NOT EXISTS idx_prod_categoria ON productos(categoria) WHERE activo = 1",
    "CREATE INDEX IF NOT EXISTS idx_ventas_fecha_suc ON ventas(DATE(fecha), sucursal_id)",
    "CREATE INDEX IF NOT EXISTS idx_ventas_cliente_fecha ON ventas(cliente_id, fecha) WHERE cliente_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_ventas_estado_fecha ON ventas(estado, fecha)",
    "CREATE INDEX IF NOT EXISTS idx_mov_prod_suc ON movimientos_inventario(producto_id, sucursal_id)",
    "CREATE INDEX IF NOT EXISTS idx_mov_fecha ON movimientos_inventario(fecha)",
    "CREATE INDEX IF NOT EXISTS idx_wa_queue_estado ON whatsapp_queue(estado, intentos) WHERE estado = 'pendiente'",
    # Conditional indexes — only if column exists
    ("idx_prod_codigo_barras", "productos", "codigo_barras",
     "CREATE INDEX IF NOT EXISTS idx_prod_codigo_barras ON productos(codigo_barras) WHERE codigo_barras IS NOT NULL"),
    ("idx_notif_usuario_leido", "notification_inbox", "usuario",
     "CREATE INDEX IF NOT EXISTS idx_notif_usuario_leido ON notification_inbox(usuario, leido) WHERE leido = 0"),
    ("idx_puntos_cliente", "puntos_fidelidad", "cliente_id",
     "CREATE INDEX IF NOT EXISTS idx_puntos_cliente ON puntos_fidelidad(cliente_id, fecha)"),
]


def _col_exists(conn, table, col):
    try:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        return col in cols
    except Exception:
        return False


def up(conn):
    created = 0
    for idx in INDEXES:
        try:
            if isinstance(idx, tuple):
                # Conditional: check column exists first
                _, table, col, sql = idx
                if not _col_exists(conn, table, col):
                    continue
            else:
                sql = idx
            conn.execute(sql)
            created += 1
        except Exception as e:
            logger.debug("045 idx skip: %s — %s", sql[:40] if isinstance(sql, str) else idx[0], e)
    logger.info("045 — %d índices de rendimiento creados", created)
