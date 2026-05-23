import logging
import sqlite3

logger = logging.getLogger("spj.migrations.090")


def _safe_add(conn: sqlite3.Connection, table: str, coldef: str) -> None:
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {coldef}")
    except Exception:
        pass


def run(conn: sqlite3.Connection) -> None:
    # ventas legacy: add canonical workflow metadata without renaming existing columns
    _safe_add(conn, "ventas", "workflow_type TEXT")
    _safe_add(conn, "ventas", "scheduled_at DATETIME")
    _safe_add(conn, "ventas", "source_channel TEXT DEFAULT 'whatsapp'")

    # delivery_orders
    _safe_add(conn, "delivery_orders", "workflow_type TEXT")
    _safe_add(conn, "delivery_orders", "delivery_type TEXT")
    _safe_add(conn, "delivery_orders", "scheduled_at DATETIME")
    _safe_add(conn, "delivery_orders", "source_channel TEXT DEFAULT 'whatsapp'")

    conn.execute("CREATE INDEX IF NOT EXISTS idx_ventas_workflow_status ON ventas(workflow_type, estado)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_delivery_workflow_status ON delivery_orders(workflow_type, estado)")

    try:
        conn.commit()
    except Exception:
        pass
    logger.info("Migración 090: workflow_type/scheduled_at/source_channel en ventas y delivery_orders completada.")
