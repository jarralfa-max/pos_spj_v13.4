# migrations/standalone/062_bi_analytics_tables.py — SPJ ERP
"""
FASE 5 — Tablas BI para AnalyticsEngine.
Idempotente: todas usan CREATE TABLE IF NOT EXISTS.
"""


def run(conn):
    conn.execute("""
        -- Identidad natural compuesta (fecha, sucursal_id): la fila agregada del
        -- día/sucursal ES la identidad (sin surrogate; patrón kpi_snapshots).
        CREATE TABLE IF NOT EXISTS bi_sales_daily (
            fecha               TEXT    NOT NULL,
            sucursal_id         TEXT    NOT NULL,
            total_ventas        REAL    NOT NULL DEFAULT 0,
            num_transacciones   INTEGER NOT NULL DEFAULT 0,
            promedio_ticket     REAL    NOT NULL DEFAULT 0,
            created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY(fecha, sucursal_id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS bi_product_profit (
            fecha       TEXT    NOT NULL,
            producto_id TEXT    NOT NULL,
            ingresos    REAL    NOT NULL DEFAULT 0,
            costo       REAL    NOT NULL DEFAULT 0,
            margen      REAL    NOT NULL DEFAULT 0,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY(fecha, producto_id)
        )
    """)

    # bi_transformations es bitácora append (sin clave natural): id TEXT UUIDv7.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bi_transformations (
            id              TEXT NOT NULL    PRIMARY KEY,
            fecha           TEXT    NOT NULL,
            sucursal_id     TEXT    NOT NULL,
            categoria       TEXT    NOT NULL DEFAULT '',
            inputs_json     TEXT    NOT NULL DEFAULT '[]',
            outputs_json    TEXT    NOT NULL DEFAULT '[]',
            rendimiento_pct REAL    NOT NULL DEFAULT 0,
            created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_bi_tr_fecha_suc
            ON bi_transformations(fecha, sucursal_id)
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS bi_branch_ranking (
            fecha       TEXT    NOT NULL,
            sucursal_id TEXT    NOT NULL,
            rank_ventas INTEGER NOT NULL DEFAULT 0,
            rank_margen INTEGER NOT NULL DEFAULT 0,
            score       REAL    NOT NULL DEFAULT 0,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY(fecha, sucursal_id)
        )
    """)

    try:
        conn.commit()
    except Exception:
        pass
