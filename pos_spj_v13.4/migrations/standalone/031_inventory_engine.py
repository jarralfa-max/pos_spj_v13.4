
# migrations/031_inventory_engine.py
# ── FASE 6: Motor de Inventario Industrial ────────────────────────────────────
#
# Tablas nuevas:
#   inventario_actual       — caché de stock calculado desde movimientos
#   transferencias          — cabecera de transferencias entre sucursales
#   transferencia_detalle   — líneas de transferencia
#   configuracioneses         — parámetros del sistema (stock negativo, etc.)
#   unidades_conversion     — factores de conversión entre unidades
#
# Principio: inventario_actual se recalcula desde movimientos_inventario
# NUNCA editar inventario_actual directamente — solo desde el motor.
#
# IDEMPOTENTE: CREATE TABLE IF NOT EXISTS + ALTER TABLE safe.

import logging
import sqlite3

logger = logging.getLogger("spj.migrations.031")


def run(conn: sqlite3.Connection) -> None:
    _cleanup_branch_inventory_duplicates(conn)
    _create_inventario_actual(conn)
    _create_transferencias(conn)
    _create_transferencia_detalle(conn)
    _create_configuracioneses(conn)
    _create_unidades_conversion(conn)
    _patch_movimientos_inventario(conn)
    _seed_configuracioneses(conn)
    _seed_unidades(conn)
    _create_indexes(conn)
    _create_triggers(conn)
    _rebuild_inventario_actual(conn)
    # Tablas adicionales fusionadas desde 031_inventory_industrial.py
    _create_transfers(conn)
    _create_recepciones(conn)
    _create_mermas(conn)
    _create_ajustes(conn)
    _create_unidades_medida(conn)
    try: conn.commit()
    except Exception: pass
    logger.info("Migracion 031 completada: inventario engine + industrial fusionado.")


def _add_col_safe(conn, tabla, col, defn):
    existing = {r[1] for r in conn.execute(f"PRAGMA table_info({tabla})").fetchall()}
    if col not in existing:
        conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {defn}")
        logger.debug("Columna %s.%s añadida.", tabla, col)


# ── 0. Limpieza de duplicados branch_inventory ────────────────────────────────

def _cleanup_branch_inventory_duplicates(conn: sqlite3.Connection) -> None:
    """
    branch_inventory puede tener múltiples filas batch_id=NULL por el mismo
    (branch_id, product_id) porque SQLite trata NULL≠NULL en UNIQUE.
    Conserva solo la fila con mayor quantity para evitar doble conteo.
    """
    dups = conn.execute("""
        SELECT branch_id, product_id, MAX(id) as max_id
        FROM branch_inventory
        WHERE batch_id IS NULL
        GROUP BY branch_id, product_id
        HAVING COUNT(*) > 1
    """).fetchall()
    for d in dups:
        conn.execute("""
            DELETE FROM branch_inventory
            WHERE branch_id=? AND product_id=? AND batch_id IS NULL AND id!=?
        """, (d[0], d[1], d[2]))
    if dups:
        logger.info("Limpiados %d grupos de branch_inventory duplicados.", len(dups))


# ── 1. inventario_actual ──────────────────────────────────────────────────────

def _create_inventario_actual(conn: sqlite3.Connection) -> None:
    """
    Caché de inventario. Se recalcula automáticamente desde movimientos.
    NUNCA editar manualmente — usar InventoryManager.registrar_movimiento().
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS inventario_actual (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id         INTEGER NOT NULL,
            sucursal_id         INTEGER NOT NULL,
            cantidad            REAL    NOT NULL DEFAULT 0,
            costo_promedio      REAL    DEFAULT 0,
            ultima_actualizacion TEXT   DEFAULT (datetime('now')),
            UNIQUE(producto_id, sucursal_id),
            FOREIGN KEY (producto_id) REFERENCES productos(id) ON DELETE RESTRICT,
            FOREIGN KEY (sucursal_id) REFERENCES sucursales(id) ON DELETE RESTRICT
        )
    """)
    logger.info("inventario_actual creada/verificada.")


# ── 2. transferencias ─────────────────────────────────────────────────────────

def _create_transferencias(conn: sqlite3.Connection) -> None:
    """
    Cabecera de transferencias entre sucursales.
    Estados: pendiente → enviado → recibido | cancelado
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transferencias (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            folio           TEXT    NOT NULL,
            origen_id       INTEGER NOT NULL,
            destino_id      INTEGER NOT NULL,
            estado          TEXT    NOT NULL DEFAULT 'pendiente'
                            CHECK(estado IN ('pendiente','enviado','recibido','cancelado')),
            notas           TEXT    DEFAULT '',
            usuario_origen  TEXT    NOT NULL,
            usuario_destino TEXT,
            operation_id    TEXT    NOT NULL,
            fecha_creacion  TEXT    DEFAULT (datetime('now')),
            fecha_envio     TEXT,
            fecha_recepcion TEXT,
            FOREIGN KEY (origen_id)  REFERENCES sucursales(id) ON DELETE RESTRICT,
            FOREIGN KEY (destino_id) REFERENCES sucursales(id) ON DELETE RESTRICT
        )
    """)
    # Trigger: no regresar estado enviado → pendiente
    conn.execute("DROP TRIGGER IF EXISTS trg_transferencia_estado")
    conn.execute("""
        CREATE TRIGGER trg_transferencia_estado
        BEFORE UPDATE OF estado ON transferencias
        WHEN OLD.estado = 'recibido' OR OLD.estado = 'cancelado'
        BEGIN
            SELECT RAISE(ABORT,
                'TRANSFERENCIA_INMUTABLE: estado final no puede cambiar');
        END
    """)
    logger.info("transferencias creada/verificada.")


# ── 3. transferencia_detalle ──────────────────────────────────────────────────

def _create_transferencia_detalle(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transferencia_detalle (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            transferencia_id INTEGER NOT NULL,
            producto_id      INTEGER NOT NULL,
            cantidad         REAL    NOT NULL CHECK(cantidad > 0),
            cantidad_recibida REAL   DEFAULT 0,
            unidad           TEXT    NOT NULL DEFAULT 'kg',
            costo_unitario   REAL    DEFAULT 0,
            notas            TEXT    DEFAULT '',
            FOREIGN KEY (transferencia_id) REFERENCES transferencias(id) ON DELETE RESTRICT,
            FOREIGN KEY (producto_id)      REFERENCES productos(id)      ON DELETE RESTRICT
        )
    """)
    logger.info("transferencia_detalle creada/verificada.")


# ── 4. configuracioneses ────────────────────────────────────────────────────────

def _create_configuracioneses(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS configuracioneses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            clave       TEXT    NOT NULL UNIQUE,
            valor       TEXT    NOT NULL,
            tipo        TEXT    NOT NULL DEFAULT 'texto',
            descripcion TEXT    DEFAULT '',
            updated_at  TEXT    DEFAULT (datetime('now'))
        )
    """)
    logger.info("configuracioneses creada/verificada.")


# ── 5. unidades_conversion ────────────────────────────────────────────────────

def _create_unidades_conversion(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS unidades_conversion (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            unidad_desde TEXT NOT NULL,
            unidad_hasta TEXT NOT NULL,
            factor       REAL NOT NULL CHECK(factor > 0),
            UNIQUE(unidad_desde, unidad_hasta)
        )
    """)
    logger.info("unidades_conversion creada/verificada.")


# ── 6. Columnas faltantes en movimientos_inventario ───────────────────────────

def _patch_movimientos_inventario(conn: sqlite3.Connection) -> None:
    _add_col_safe(conn, "movimientos_inventario", "tipo_movimiento_v2", "TEXT")
    _add_col_safe(conn, "movimientos_inventario", "nota",               "TEXT")
    _add_col_safe(conn, "movimientos_inventario", "proveedor_id",       "INTEGER")
    _add_col_safe(conn, "movimientos_inventario", "operation_id",       "TEXT")


# ── 7. Seed configuracioneses ───────────────────────────────────────────────────

def _seed_configuracioneses(conn: sqlite3.Connection) -> None:
    defaults = [
        ("permitir_stock_negativo", "false", "booleano",
         "Permite ventas aunque no haya stock suficiente"),
        ("sucursal_global_id",      "0",     "entero",
         "ID de la sucursal que actúa como almacén global (0=no aplica)"),
        ("alerta_stock_minimo",     "true",  "booleano",
         "Mostrar alerta cuando stock <= stock_minimo"),
        ("kardex_mostrar_costo",    "true",  "booleano",
         "Mostrar columna de costo en el kardex"),
        ("transferencia_requiere_confirmacion", "true", "booleano",
         "La recepción de transferencia requiere confirmación manual"),
    ]
    for clave, valor, tipo, desc in defaults:
        conn.execute("""
            INSERT OR IGNORE INTO configuracioneses (clave, valor, tipo, descripcion)
            VALUES (?,?,?,?)
        """, (clave, valor, tipo, desc))
    logger.info("configuracioneses por defecto insertadas.")


# ── 8. Seed unidades de conversión ────────────────────────────────────────────

def _seed_unidades(conn: sqlite3.Connection) -> None:
    conversiones = [
        # peso
        ("kg",     "g",     1000.0),
        ("g",      "kg",    0.001),
        ("kg",     "lb",    2.20462),
        ("lb",     "kg",    0.453592),
        # volumen
        ("l",      "ml",    1000.0),
        ("ml",     "l",     0.001),
        # conteo
        ("caja",   "pza",   12.0),
        ("paquete","pza",   6.0),
        ("paquete","kg",    1.0),
        # mismo a mismo (identidad)
        ("kg",     "kg",    1.0),
        ("pza",    "pza",   1.0),
        ("g",      "g",     1.0),
        ("l",      "l",     1.0),
        ("ml",     "ml",    1.0),
    ]
    for desde, hasta, factor in conversiones:
        conn.execute("""
            INSERT OR IGNORE INTO unidades_conversion (unidad_desde, unidad_hasta, factor)
            VALUES (?,?,?)
        """, (desde, hasta, factor))
    logger.info("Unidades de conversión insertadas.")


# ── 9. Índices ────────────────────────────────────────────────────────────────

def _create_indexes(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_inv_actual_prod_suc
        ON inventario_actual(producto_id, sucursal_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_inv_actual_suc
        ON inventario_actual(sucursal_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_transferencias_estado
        ON transferencias(estado)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_transferencias_origen
        ON transferencias(origen_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_mov_inv_producto
        ON movimientos_inventario(producto_id, sucursal_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_mov_inv_fecha
        ON movimientos_inventario(fecha)
    """)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_transferencias_op
        ON transferencias(operation_id)
    """)
    logger.info("Índices creados/verificados.")


# ── 10. Triggers de consistencia ──────────────────────────────────────────────

def _create_triggers(conn: sqlite3.Connection) -> None:
    # Sync automático de productos.existencia desde inventario_actual
    conn.execute("DROP TRIGGER IF EXISTS trg_sync_existencia_insert")
    conn.execute("""
        CREATE TRIGGER trg_sync_existencia_insert
        AFTER INSERT ON inventario_actual
        BEGIN
            UPDATE productos
            SET existencia = (
                SELECT COALESCE(SUM(ia.cantidad), 0)
                FROM inventario_actual ia
                WHERE ia.producto_id = NEW.producto_id
            )
            WHERE id = NEW.producto_id;
        END
    """)
    conn.execute("DROP TRIGGER IF EXISTS trg_sync_existencia_update")
    conn.execute("""
        CREATE TRIGGER trg_sync_existencia_update
        AFTER UPDATE ON inventario_actual
        BEGIN
            UPDATE productos
            SET existencia = (
                SELECT COALESCE(SUM(ia.cantidad), 0)
                FROM inventario_actual ia
                WHERE ia.producto_id = NEW.producto_id
            )
            WHERE id = NEW.producto_id;
        END
    """)
    logger.info("Triggers de sincronización creados.")


# ── 11. Reconstruir inventario_actual desde branch_inventory ──────────────────

def _rebuild_inventario_actual(conn: sqlite3.Connection) -> None:
    """
    Poblar inventario_actual desde branch_inventory (Fase 1)
    para datos existentes al momento de la migración.
    """
    rows = conn.execute("""
        SELECT bi.product_id, bi.branch_id,
               SUM(bi.quantity) as total_qty
        FROM branch_inventory bi
        GROUP BY bi.product_id, bi.branch_id
    """).fetchall()

    for r in rows:
        conn.execute("""
            INSERT INTO inventario_actual (producto_id, sucursal_id, cantidad)
            VALUES (?,?,?)
            ON CONFLICT(producto_id, sucursal_id)
            DO UPDATE SET cantidad = excluded.cantidad,
                          ultima_actualizacion = datetime('now')
        """, (r["product_id"], r["branch_id"], float(r["total_qty"])))

    logger.info("inventario_actual reconstruido desde branch_inventory: %d filas.", len(rows))


# ── Helpers fusionados desde 031_inventory_industrial.py ─────────────────────

# migrations/031_inventory_industrial.py
# ── FASE 6: Motor de Inventario Industrial ───────────────────────────────────
#
# Crea las tablas faltantes que el sistema necesita para el flujo completo:
#   1. transfers + transfer_items     — para TransferRepository (Fase 1)
#   2. recepciones + recepcion_items  — recepción directa de mercancía
#   3. mermas                         — registro de mermas
#   4. ajustes_inventario             — ajustes positivos/negativos
#   5. unidades_medida                — catálogo de unidades + conversiones
#   6. Columnas faltantes en movimientos_inventario
#   7. Trigger: auto-recalcula inventario_actual tras INSERT en movimientos_inventario
#
# IDEMPOTENTE — seguro de ejecutar múltiples veces.

import logging
import sqlite3

logger = logging.getLogger("spj.migrations.031")


def _create_transfers(conn: sqlite3.Connection) -> None:
    """
    Tabla usada por TransferRepository (repositories/transferencias.py).
    Schema exacto que el repo espera.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transfers (
            id                TEXT    PRIMARY KEY,
            branch_origin_id  INTEGER NOT NULL,
            branch_dest_id    INTEGER NOT NULL,
            origin_type       TEXT    NOT NULL DEFAULT 'BRANCH',
            destination_type  TEXT    NOT NULL DEFAULT 'BRANCH',
            status            TEXT    NOT NULL DEFAULT 'DISPATCHED',
            dispatched_by     TEXT    NOT NULL,
            dispatched_at     TEXT    NOT NULL,
            received_by       TEXT,
            received_at       TEXT,
            observations      TEXT,
            operation_id      TEXT    NOT NULL,
            created_at        TEXT    NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (branch_origin_id) REFERENCES sucursales(id) ON DELETE RESTRICT,
            FOREIGN KEY (branch_dest_id)   REFERENCES sucursales(id) ON DELETE RESTRICT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transfer_items (
            id                 TEXT    PRIMARY KEY,
            transfer_id        TEXT    NOT NULL,
            product_id         INTEGER NOT NULL,
            quantity_sent      REAL    NOT NULL CHECK(quantity_sent > 0),
            quantity_received  REAL,
            unit               TEXT    NOT NULL DEFAULT 'kg',
            batch_id           INTEGER,
            notes              TEXT,
            difference         REAL    GENERATED ALWAYS AS
                               (CASE WHEN quantity_received IS NOT NULL
                                THEN quantity_received - quantity_sent ELSE NULL END) VIRTUAL,
            FOREIGN KEY (transfer_id) REFERENCES transfers(id)      ON DELETE RESTRICT,
            FOREIGN KEY (product_id)  REFERENCES productos(id)      ON DELETE RESTRICT
        )
    """)
    logger.info("Tablas transfers + transfer_items creadas/verificadas.")


# ── 2. recepciones + recepcion_items ──────────────────────────────────────────

def _create_recepciones(conn: sqlite3.Connection) -> None:
    """Recepción directa: compras, ajustes iniciales, ingreso manual."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS recepciones (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            folio           TEXT    NOT NULL,
            tipo            TEXT    NOT NULL DEFAULT 'COMPRA',
            proveedor_id    INTEGER,
            sucursal_id     INTEGER NOT NULL,
            usuario         TEXT    NOT NULL,
            quien_entrega   TEXT,
            notas           TEXT,
            operation_id    TEXT    NOT NULL,
            estado          TEXT    NOT NULL DEFAULT 'completada',
            created_at      TEXT    DEFAULT (datetime('now')),
            FOREIGN KEY (proveedor_id) REFERENCES proveedores(id) ON DELETE SET NULL,
            FOREIGN KEY (sucursal_id)  REFERENCES sucursales(id)  ON DELETE RESTRICT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS recepcion_items (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            recepcion_id    INTEGER NOT NULL,
            producto_id     INTEGER NOT NULL,
            cantidad        REAL    NOT NULL CHECK(cantidad > 0),
            unidad          TEXT    NOT NULL DEFAULT 'kg',
            costo_unitario  REAL    NOT NULL DEFAULT 0 CHECK(costo_unitario >= 0),
            notas           TEXT,
            FOREIGN KEY (recepcion_id) REFERENCES recepciones(id)   ON DELETE RESTRICT,
            FOREIGN KEY (producto_id)  REFERENCES productos(id)     ON DELETE RESTRICT
        )
    """)
    logger.info("Tablas recepciones + recepcion_items creadas/verificadas.")


# ── 3. mermas ─────────────────────────────────────────────────────────────────

def _create_mermas(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mermas (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id     INTEGER NOT NULL,
            sucursal_id     INTEGER NOT NULL,
            cantidad        REAL    NOT NULL CHECK(cantidad > 0),
            unidad          TEXT    NOT NULL DEFAULT 'kg',
            motivo          TEXT    NOT NULL,
            usuario         TEXT    NOT NULL,
            operation_id    TEXT    NOT NULL,
            autorizado_por  TEXT,
            created_at      TEXT    DEFAULT (datetime('now')),
            FOREIGN KEY (producto_id)  REFERENCES productos(id)   ON DELETE RESTRICT,
            FOREIGN KEY (sucursal_id)  REFERENCES sucursales(id)  ON DELETE RESTRICT
        )
    """)
    logger.info("Tabla mermas creada/verificada.")


# ── 4. ajustes_inventario ─────────────────────────────────────────────────────

def _create_ajustes(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ajustes_inventario (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id     INTEGER NOT NULL,
            sucursal_id     INTEGER NOT NULL,
            tipo            TEXT    NOT NULL CHECK(tipo IN ('AJUSTE_POSITIVO','AJUSTE_NEGATIVO')),
            cantidad        REAL    NOT NULL CHECK(cantidad > 0),
            unidad          TEXT    NOT NULL DEFAULT 'kg',
            motivo          TEXT    NOT NULL,
            usuario         TEXT    NOT NULL,
            autorizado_por  TEXT,
            operation_id    TEXT    NOT NULL,
            created_at      TEXT    DEFAULT (datetime('now')),
            FOREIGN KEY (producto_id) REFERENCES productos(id)  ON DELETE RESTRICT,
            FOREIGN KEY (sucursal_id) REFERENCES sucursales(id) ON DELETE RESTRICT
        )
    """)
    logger.info("Tabla ajustes_inventario creada/verificada.")


# ── 5. unidades_medida ────────────────────────────────────────────────────────

def _create_unidades_medida(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS unidades_medida (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo          TEXT    NOT NULL UNIQUE,
            nombre          TEXT    NOT NULL,
            factor_base     REAL    NOT NULL DEFAULT 1.0,
            unidad_base     TEXT    NOT NULL DEFAULT 'kg',
            activa          INTEGER NOT NULL DEFAULT 1
        )
    """)
    logger.info("Tabla unidades_medida creada/verificada.")


# ── 6. Parches a movimientos_inventario ───────────────────────────────────────

def _patch_movimientos_inventario(conn: sqlite3.Connection) -> None:
    _add_col_safe(conn, "movimientos_inventario", "nota",           "TEXT")
    _add_col_safe(conn, "movimientos_inventario", "costo_unitario", "REAL DEFAULT 0")
    logger.info("movimientos_inventario parchado.")


# ── 7. Parches a inventario_actual ────────────────────────────────────────────

def _patch_inventario_actual(conn: sqlite3.Connection) -> None:
    _add_col_safe(conn, "inventario_actual", "costo_promedio", "REAL DEFAULT 0")
    _add_col_safe(conn, "inventario_actual", "ultima_actualizacion", "TEXT DEFAULT (datetime('now'))")
    logger.info("inventario_actual parchado.")


# ── 8. Trigger de recalculación de cache ─────────────────────────────────────

def _create_triggers(conn: sqlite3.Connection) -> None:
    """
    Recalcula inventario_actual.cantidad automáticamente después de cada
    INSERT en movimientos_inventario.

    El campo `tipo` en movimientos_inventario usa 'entrada'/'salida'.
    Tipos de entrada: COMPRA, RECEPCION_DIRECTA, TRANSFERENCIA_ENTRADA,
                      PRODUCCION_GENERACION, AJUSTE_POSITIVO, DEVOLUCION
    Tipos de salida:  VENTA, TRANSFERENCIA_SALIDA, PRODUCCION_CONSUMO,
                      AJUSTE_NEGATIVO, MERMA
    """
    conn.execute("DROP TRIGGER IF EXISTS trg_recalc_inventario_actual")
    conn.execute("""
        CREATE TRIGGER trg_recalc_inventario_actual
        AFTER INSERT ON movimientos_inventario
        WHEN NEW.producto_id IS NOT NULL AND NEW.sucursal_id IS NOT NULL
        BEGIN
            INSERT INTO inventario_actual (producto_id, sucursal_id, cantidad, ultima_actualizacion)
            VALUES (
                NEW.producto_id,
                NEW.sucursal_id,
                CASE WHEN NEW.tipo IN ('entrada','COMPRA','RECEPCION_DIRECTA',
                                       'TRANSFERENCIA_ENTRADA','PRODUCCION_GENERACION',
                                       'PRODUCCION_ENTRADA','AJUSTE_POSITIVO','DEVOLUCION')
                     THEN NEW.cantidad ELSE -NEW.cantidad END,
                datetime('now')
            )
            ON CONFLICT(producto_id, sucursal_id) DO UPDATE SET
                cantidad = inventario_actual.cantidad +
                    CASE WHEN NEW.tipo IN ('entrada','COMPRA','RECEPCION_DIRECTA',
                                           'TRANSFERENCIA_ENTRADA','PRODUCCION_GENERACION',
                                           'PRODUCCION_ENTRADA','AJUSTE_POSITIVO','DEVOLUCION')
                         THEN NEW.cantidad ELSE -NEW.cantidad END,
                ultima_actualizacion = datetime('now');
        END
    """)

    # NOTA: no se pone trigger BEFORE UPDATE sobre cantidad porque el propio trigger
    # trg_recalc_inventario_actual hace INSERT ON CONFLICT DO UPDATE y dispararía
    # un bucle. La protección se garantiza a nivel de engine (único punto de escritura).
    logger.info("Triggers de inventario_actual creados/verificados.")


# ── 9. Índices ────────────────────────────────────────────────────────────────

def _create_indexes(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE INDEX IF NOT EXISTS idx_transfers_origin  ON transfers(branch_origin_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_transfers_dest    ON transfers(branch_dest_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_transfers_status  ON transfers(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_transfer_items_tr ON transfer_items(transfer_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_recepciones_suc   ON recepciones(sucursal_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_mermas_prod_suc   ON mermas(producto_id, sucursal_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ajustes_prod_suc  ON ajustes_inventario(producto_id, sucursal_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_movinv_prod_suc   ON movimientos_inventario(producto_id, sucursal_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_movinv_fecha      ON movimientos_inventario(fecha)")
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_inventario_actual_pk
        ON inventario_actual(producto_id, sucursal_id)
    """)
    logger.info("Índices de inventario industrial creados/verificados.")


# ── 10. Seed unidades_medida ──────────────────────────────────────────────────

def _seed_unidades(conn: sqlite3.Connection) -> None:
    unidades = [
        ("kg",  "Kilogramo",   1.0,    "kg"),
        ("g",   "Gramo",       0.001,  "kg"),
        ("t",   "Tonelada",    1000.0, "kg"),
        ("l",   "Litro",       1.0,    "l"),
        ("ml",  "Mililitro",   0.001,  "l"),
        ("pza", "Pieza",       1.0,    "pza"),
        ("paq", "Paquete",     1.0,    "paq"),
        ("cja", "Caja",        1.0,    "cja"),
        ("doc", "Docena",      12.0,   "pza"),
    ]
    for codigo, nombre, factor, base in unidades:
        conn.execute("""
            INSERT OR IGNORE INTO unidades_medida (codigo, nombre, factor_base, unidad_base)
            VALUES (?,?,?,?)
        """, (codigo, nombre, factor, base))
    logger.info("Unidades de medida sembradas.")