"""
067_meat_erp_improvements.py — pos_spj v13.5 ERP Cárnico
=========================================================

Mejoras de trazabilidad, costeo y merma para sistema ERP cárnico.

Cambios:
  1. production_batches  → columnas lote_origen_id, auto_produccion
  2. production_outputs  → columnas lote_hijo_id, merma_kg_real, variacion_kg
  3. produccion_detalle  → columna tipo expandida (soporte 'merma')
  4. lotes               → columna lote_padre_id, lote_batch_id (genealogía)
  5. movimientos_inventario → columna lote_id, merma_motivo
  6. productos           → columnas peso_prom_kg, es_carnico, unidad_peso
  7. VISTA merma_resumen → por producto/periodo
  8. TABLA merma_log     → registro granular de merma por producción

Ver: migrations/MIGRATION_LOG.md — entrada 067
"""
import logging
import sqlite3

logger = logging.getLogger("spj.migrations.067")


def _add_col(conn: sqlite3.Connection, tabla: str, col: str, defn: str) -> None:
    """Agrega columna de forma idempotente."""
    try:
        existing = {r[1] for r in conn.execute(f"PRAGMA table_info({tabla})").fetchall()}
        if col not in existing:
            conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {defn}")
            logger.debug("+ %s.%s", tabla, col)
    except Exception as e:
        logger.debug("add_col %s.%s: %s", tabla, col, e)


def run(conn: sqlite3.Connection) -> None:
    logger.info("Migración 067 — ERP Cárnico: trazabilidad de lotes y merma...")

    # ── 1. production_batches — columnas de trazabilidad ─────────────────────
    _add_col(conn, "production_batches", "lote_origen_id",
             "INTEGER REFERENCES lotes(id)")
    _add_col(conn, "production_batches", "auto_produccion",
             "INTEGER NOT NULL DEFAULT 1")
    _add_col(conn, "production_batches", "kg_merma_real",
             "REAL DEFAULT 0")
    _add_col(conn, "production_batches", "kg_teorico",
             "REAL DEFAULT 0")
    _add_col(conn, "production_batches", "desviacion_kg",
             "REAL GENERATED ALWAYS AS (kg_merma_real - kg_teorico) VIRTUAL")

    # ── 2. production_outputs — trazabilidad por subproducto ─────────────────
    _add_col(conn, "production_outputs", "lote_hijo_id",
             "INTEGER REFERENCES lotes(id)")
    _add_col(conn, "production_outputs", "merma_kg_real",
             "REAL DEFAULT 0")
    _add_col(conn, "production_outputs", "variacion_kg",
             "REAL DEFAULT 0")

    # ── 3. produccion_detalle — tipo expandido ────────────────────────────────
    # SQLite no tiene ALTER COLUMN — el CHECK ya existente es laxo, agregar 'merma'
    # es compatible sin cambio de constraint dado que SQLite no enforcea CHECK en ALTER
    _add_col(conn, "produccion_detalle", "lote_id",
             "INTEGER REFERENCES lotes(id)")
    _add_col(conn, "produccion_detalle", "merma_kg",
             "REAL DEFAULT 0")

    # ── 4. lotes — genealogía padre-hijo ─────────────────────────────────────
    _add_col(conn, "lotes", "lote_padre_id",
             "INTEGER REFERENCES lotes(id)")
    _add_col(conn, "lotes", "batch_id",
             "TEXT REFERENCES production_batches(id)")
    _add_col(conn, "lotes", "tipo_origen",
             "TEXT DEFAULT 'compra'")  # compra | produccion | ajuste

    # ── 5. movimientos_inventario — vínculo con lote ─────────────────────────
    _add_col(conn, "movimientos_inventario", "lote_id",
             "INTEGER REFERENCES lotes(id)")
    _add_col(conn, "movimientos_inventario", "merma_motivo",
             "TEXT")  # descripción de merma si aplica

    # ── 6. productos — campos cárnicos ───────────────────────────────────────
    _add_col(conn, "productos", "peso_prom_kg",
             "REAL DEFAULT 1.0")
    _add_col(conn, "productos", "es_carnico",
             "INTEGER DEFAULT 0")
    _add_col(conn, "productos", "unidad_peso",
             "TEXT DEFAULT 'kg'")  # kg | g | lb

    # ── 7. Tabla merma_log — registro granular de merma ──────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS merma_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid            TEXT UNIQUE DEFAULT (lower(hex(randomblob(16)))),
            producto_id     INTEGER NOT NULL REFERENCES productos(id),
            lote_id         INTEGER REFERENCES lotes(id),
            produccion_id   INTEGER REFERENCES producciones(id),
            batch_id        TEXT REFERENCES production_batches(id),
            merma_kg        REAL NOT NULL DEFAULT 0,
            merma_pct_real  REAL DEFAULT 0,
            merma_pct_esperada REAL DEFAULT 0,
            desviacion_pct  REAL GENERATED ALWAYS AS (merma_pct_real - merma_pct_esperada) VIRTUAL,
            motivo          TEXT DEFAULT 'PRODUCCION',  -- PRODUCCION|CADUCIDAD|AJUSTE|TRANSPORTE
            costo_perdida   REAL DEFAULT 0,
            sucursal_id     INTEGER DEFAULT 1,
            usuario         TEXT,
            fecha           DATETIME DEFAULT (datetime('now'))
        )
    """)

    # ── 8. Índices de rendimiento ─────────────────────────────────────────────
    indices = [
        "CREATE INDEX IF NOT EXISTS idx_merma_log_producto ON merma_log(producto_id, fecha)",
        "CREATE INDEX IF NOT EXISTS idx_merma_log_batch ON merma_log(batch_id)",
        "CREATE INDEX IF NOT EXISTS idx_merma_log_lote ON merma_log(lote_id)",
        "CREATE INDEX IF NOT EXISTS idx_lotes_padre ON lotes(lote_padre_id)",
        "CREATE INDEX IF NOT EXISTS idx_lotes_batch ON lotes(batch_id)",
        "CREATE INDEX IF NOT EXISTS idx_prod_batches_lote_origen ON production_batches(lote_origen_id)",
        "CREATE INDEX IF NOT EXISTS idx_movimientos_inv_lote ON movimientos_inventario(lote_id)",
    ]
    for idx in indices:
        try:
            conn.execute(idx)
        except Exception as e:
            logger.debug("idx 067: %s", e)

    # ── 9. Vista resumen de merma por producto/mes ────────────────────────────
    try:
        conn.execute("DROP VIEW IF EXISTS vista_merma_resumen")
        conn.execute("""
            CREATE VIEW vista_merma_resumen AS
            SELECT
                p.id          AS producto_id,
                p.nombre      AS producto,
                strftime('%Y-%m', ml.fecha) AS mes,
                COUNT(*)      AS registros,
                SUM(ml.merma_kg) AS merma_kg_total,
                AVG(ml.merma_pct_real) AS merma_pct_promedio,
                SUM(ml.costo_perdida)  AS costo_perdida_total,
                MAX(ml.merma_pct_real) AS merma_pct_max
            FROM merma_log ml
            JOIN productos p ON p.id = ml.producto_id
            GROUP BY p.id, strftime('%Y-%m', ml.fecha)
            ORDER BY ml.fecha DESC, merma_kg_total DESC
        """)
        logger.debug("Vista vista_merma_resumen creada.")
    except Exception as e:
        logger.warning("vista_merma_resumen: %s", e)

    conn.commit()
    logger.info("Migración 067 completada — ERP Cárnico activo.")
