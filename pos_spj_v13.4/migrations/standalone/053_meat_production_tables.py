"""
053_meat_production_tables.py — pos_spj v13.4
Resolución del conflicto de migración 032.

El archivo 032_meat_production.py contenía tablas de producción cárnica
(meat_production_runs, meat_production_yields) que nunca se ejecutaron vía
engine.py porque el canónico 032_bi_tables.py fue el elegido.

Esta migración aplica esas tablas de forma idempotente (CREATE TABLE IF NOT EXISTS).
Incluye también el patch de schema_drift que el huérfano aplicaba.

Ver: migrations/MIGRATION_LOG.md — entrada 053, conflicto 032
"""
import logging
import sqlite3

logger = logging.getLogger("spj.migrations.053")


def _add_col_safe(conn: sqlite3.Connection, tabla: str, col: str, defn: str) -> None:
    try:
        existing = {r[1] for r in conn.execute(f"PRAGMA table_info({tabla})").fetchall()}
        if col not in existing:
            conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {defn}")
            logger.debug("Columna %s.%s añadida.", tabla, col)
    except Exception as e:
        logger.debug("add_col %s.%s: %s", tabla, col, e)


def run(conn: sqlite3.Connection) -> None:
    logger.info("Migración 053 — tablas cárnicas huérfanas de 032...")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS meat_production_runs (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_id        INTEGER NOT NULL,
            source_product_id INTEGER NOT NULL,
            source_weight    REAL NOT NULL,
            source_cost      REAL NOT NULL,
            status           TEXT NOT NULL DEFAULT 'DRAFT',
            created_at       DATETIME DEFAULT (datetime('now')),
            fecha            DATETIME DEFAULT (datetime('now')),
            completed_at     DATETIME,
            user_id          INTEGER
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS meat_production_yields (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id          INTEGER NOT NULL,
            yield_product_id INTEGER NOT NULL,
            weight          REAL NOT NULL,
            allocated_cost  REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (run_id) REFERENCES meat_production_runs(id) ON DELETE CASCADE
        )
    """)

    # Patch schema drift: columnas fecha/created_at en tablas relacionadas
    for tabla in ["meat_production_runs", "producciones", "kpi_snapshots"]:
        _add_col_safe(conn, tabla, "fecha", "DATETIME DEFAULT (datetime('now'))")
        _add_col_safe(conn, tabla, "created_at", "DATETIME DEFAULT (datetime('now'))")

    # Índices
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_meat_runs_branch_fecha ON meat_production_runs(branch_id, fecha)",
        "CREATE INDEX IF NOT EXISTS idx_meat_runs_branch_created ON meat_production_runs(branch_id, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_meat_yields_run ON meat_production_yields(run_id)",
    ]:
        try:
            conn.execute(idx)
        except Exception as e:
            logger.debug("idx 053: %s", e)

    conn.commit()
    logger.info("Migración 053 completada.")
