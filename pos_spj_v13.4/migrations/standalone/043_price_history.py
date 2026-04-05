
# migrations/standalone/043_price_history.py
# ── Historial de Cambios de Precio ───────────────────────────────────────────
# Registra quién cambió el precio, cuándo y desde/hasta cuánto.
# Un trigger lo captura automáticamente — sin cambiar el código de la UI.
import logging, sqlite3
logger = logging.getLogger("spj.migrations.043")

def run(conn: sqlite3.Connection) -> None:
    _create_price_history(conn)
    _create_trigger(conn)
    try: conn.commit()
    except Exception: pass
    logger.info("Migración 043: historial de precios completada.")

def _create_price_history(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS historial_precios (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id     INTEGER NOT NULL,
            campo           TEXT    NOT NULL DEFAULT 'precio'
                            CHECK(campo IN ('precio','precio_compra','precio_venta',
                                            'precio_kilo','precio_mayoreo')),
            precio_anterior REAL    NOT NULL,
            precio_nuevo    REAL    NOT NULL,
            diferencia_pct  REAL    GENERATED ALWAYS AS (
                CASE WHEN precio_anterior > 0
                     THEN ROUND((precio_nuevo - precio_anterior) * 100.0 / precio_anterior, 2)
                     ELSE 0 END
            ) STORED,
            usuario         TEXT    DEFAULT 'Sistema',
            sucursal_id     INTEGER DEFAULT 1,
            motivo          TEXT,
            changed_at      TEXT    DEFAULT (datetime('now')),
            FOREIGN KEY (producto_id) REFERENCES productos(id)
        )""")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_hp_producto "
        "ON historial_precios(producto_id, changed_at DESC)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_hp_fecha "
        "ON historial_precios(changed_at DESC)")
    logger.info("historial_precios creada.")

def _create_trigger(conn):
    """
    Trigger que captura automáticamente cambios de precio en la tabla productos.
    No requiere cambios en el código de la UI — el trigger lo hace solo.
    """
        # Precio de venta
    conn.execute("DROP TRIGGER IF EXISTS trg_historial_precio_venta")
    conn.execute("""
        CREATE TRIGGER trg_historial_precio_venta
        AFTER UPDATE OF precio ON productos
        WHEN OLD.precio <> NEW.precio
        BEGIN
            INSERT INTO historial_precios(producto_id, campo, precio_anterior, precio_nuevo)
            VALUES(NEW.id, 'precio', OLD.precio, NEW.precio);
        END
    """)
    # Precio de compra
    conn.execute("DROP TRIGGER IF EXISTS trg_historial_precio_compra")
    conn.execute("""
        CREATE TRIGGER trg_historial_precio_compra
        AFTER UPDATE OF precio_compra ON productos
        WHEN OLD.precio_compra <> NEW.precio_compra
        BEGIN
            INSERT INTO historial_precios(producto_id, campo, precio_anterior, precio_nuevo)
            VALUES(NEW.id, 'precio_compra', OLD.precio_compra, NEW.precio_compra);
        END
    """)
    logger.info("Triggers historial_precios creados.")
