# migrations/standalone/062_bi_analytics_tables.py — SPJ ERP
"""
FASE 5 — Tablas BI para AnalyticsEngine.
Idempotente: todas usan CREATE TABLE IF NOT EXISTS.
"""


def run(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bi_sales_daily (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha               TEXT    NOT NULL,
            sucursal_id         INTEGER NOT NULL DEFAULT 1,
            total_ventas        REAL    NOT NULL DEFAULT 0,
            num_transacciones   INTEGER NOT NULL DEFAULT 0,
            promedio_ticket     REAL    NOT NULL DEFAULT 0,
            created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
            UNIQUE(fecha, sucursal_id)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_bi_sd_fecha_suc
            ON bi_sales_daily(fecha, sucursal_id)
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS bi_product_profit (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha       TEXT    NOT NULL,
            producto_id INTEGER NOT NULL,
            ingresos    REAL    NOT NULL DEFAULT 0,
            costo       REAL    NOT NULL DEFAULT 0,
            margen      REAL    NOT NULL DEFAULT 0,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            UNIQUE(fecha, producto_id)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_bi_pp_fecha
            ON bi_product_profit(fecha, producto_id)
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS bi_transformations (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha           TEXT    NOT NULL,
            sucursal_id     INTEGER NOT NULL DEFAULT 1,
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
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha       TEXT    NOT NULL,
            sucursal_id INTEGER NOT NULL,
            rank_ventas INTEGER NOT NULL DEFAULT 0,
            rank_margen INTEGER NOT NULL DEFAULT 0,
            score       REAL    NOT NULL DEFAULT 0,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            UNIQUE(fecha, sucursal_id)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_bi_br_fecha
            ON bi_branch_ranking(fecha, sucursal_id)
    """)

    try:
        conn.commit()
    except Exception:
        pass
