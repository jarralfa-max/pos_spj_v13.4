
# migrations/standalone/039_branch_products.py
# ── Productos por Sucursal (branch_products) ──────────────────────────────────
#
# PROBLEMA RESUELTO: La tabla productos tiene un solo flag activo=0/1 global.
# Si se desactiva un producto, desaparece en TODAS las sucursales.
# Además productos.sucursal_id implica que el producto "pertenece" a una sola
# sucursal, lo que causa inconsistencias en reportes multi-sucursal.
#
# SOLUCIÓN: Tabla pivot branch_products + Vista v_productos_activos.
#   - branch_products(branch_id, product_id) define qué productos existen en cada sucursal
#   - precio_local NULL = usar productos.precio (sin diferenciación)
#   - stock_min_local NULL = usar productos.stock_minimo (sin diferenciación)
#   - La VISTA mantiene compatibilidad: código antiguo sigue funcionando sin cambios.
#
# MIGRACIÓN DE DATOS: Seed automático — todos los productos activos se habilitan
# en todas las sucursales activas (comportamiento actual preservado).
#
# IDEMPOTENTE.
import logging, sqlite3
logger = logging.getLogger("spj.migrations.039")

def run(conn: sqlite3.Connection) -> None:
    _create_branch_products(conn)
    _create_view(conn)
    _seed_existing_products(conn)
    _create_indexes(conn)
    try: conn.commit()
    except Exception: pass
    logger.info("Migración 039: branch_products completada.")

def _create_branch_products(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS branch_products (
            branch_id       INTEGER NOT NULL,
            product_id      INTEGER NOT NULL,
            activo          INTEGER NOT NULL DEFAULT 1
                            CHECK(activo IN (0,1)),
            precio_local    REAL,       -- NULL = usar productos.precio
            stock_min_local REAL,       -- NULL = usar productos.stock_minimo
            notas           TEXT,
            updated_at      TEXT DEFAULT (datetime('now')),
            updated_by      TEXT,
            PRIMARY KEY (branch_id, product_id),
            FOREIGN KEY (branch_id)  REFERENCES sucursales(id) ON DELETE CASCADE,
            FOREIGN KEY (product_id) REFERENCES productos(id)  ON DELETE CASCADE
        )""")
    logger.info("branch_products creada/verificada.")

def _create_view(conn):
    """
    Vista de compatibilidad: los módulos que hacen
    SELECT ... FROM productos WHERE activo=1 AND sucursal_id=?
    ahora pueden usar esta vista si se refactorizan gradualmente.
    La vista NO rompe el código existente porque productos sigue igual.
    """
    conn.execute("DROP VIEW IF EXISTS v_productos_activos")
    conn.execute("""
        CREATE VIEW v_productos_activos AS
        SELECT
            p.*,
            bp.branch_id,
            bp.activo          AS activo_en_sucursal,
            COALESCE(bp.precio_local,    p.precio)        AS precio_efectivo,
            COALESCE(bp.stock_min_local, p.stock_minimo)  AS stock_min_efectivo
        FROM productos p
        JOIN branch_products bp ON bp.product_id = p.id
        WHERE p.activo = 1
          AND bp.activo = 1
    """)
    logger.info("Vista v_productos_activos creada.")

def _seed_existing_products(conn):
    """
    Preserva el comportamiento actual: todos los productos activos
    quedan habilitados en todas las sucursales activas.
    Solo inserta filas faltantes (ON CONFLICT IGNORE).
    """
    try:
        conn.execute("""
            INSERT OR IGNORE INTO branch_products (branch_id, product_id, activo)
            SELECT s.id, p.id, 1
            FROM sucursales s
            CROSS JOIN productos p
            WHERE s.activa = 1
              AND p.activo  = 1
              AND p.deleted_at IS NULL
        """)
        n = conn.execute("SELECT changes()").fetchone()[0]
        logger.info("Seed branch_products: %d filas insertadas.", n)
    except Exception as e:
        logger.warning("_seed_existing_products: %s", e)

def _create_indexes(conn):
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_bp_branch   ON branch_products(branch_id, activo)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_bp_product  ON branch_products(product_id, activo)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_bp_precio   ON branch_products(branch_id) WHERE precio_local IS NOT NULL")
    logger.info("Índices branch_products creados.")
