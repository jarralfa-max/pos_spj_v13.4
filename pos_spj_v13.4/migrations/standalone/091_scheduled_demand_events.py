import logging
import sqlite3

logger = logging.getLogger("spj.migrations.091")


def run(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_demand_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id INTEGER NOT NULL,
            branch_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity REAL NOT NULL DEFAULT 0,
            unit TEXT DEFAULT 'kg',
            scheduled_at DATETIME NOT NULL,
            source_channel TEXT DEFAULT 'whatsapp',
            customer_id INTEGER,
            folio TEXT,
            created_at DATETIME DEFAULT (datetime('now')),
            UNIQUE(sale_id, product_id, scheduled_at)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sched_demand_branch_date ON scheduled_demand_events(branch_id, scheduled_at)")
    try:
        conn.commit()
    except Exception:
        pass
    logger.info("Migración 091: scheduled_demand_events completada.")
