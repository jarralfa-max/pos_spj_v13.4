# migrations/standalone/061_fix_finanzas_schema.py — SPJ ERP
"""
FASE 1 Hotfix — columnas faltantes en tablas de finanzas.
Usa PRAGMA table_info() para compatibilidad con SQLite < 3.35.
Non-fatal: errores individuales se loguean sin abortar la migración.
"""
import logging

logger = logging.getLogger("spj.migrations.061")


def run(conn):
    def _col_exists(table, col):
        try:
            rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
            return any(r[1] == col for r in rows)
        except Exception:
            return False

    def _add_col(table, col, defn):
        if not _col_exists(table, col):
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {defn}")
                logger.info("061: added %s.%s", table, col)
            except Exception as e:
                logger.warning("061: could not add %s.%s: %s", table, col, e)

    _add_col("financial_event_log", "concepto", "TEXT")

    _add_col("accounts_payable", "folio",    "TEXT")
    _add_col("accounts_payable", "concepto", "TEXT")
    _add_col("accounts_payable", "ref_type", "TEXT DEFAULT 'manual'")

    _add_col("accounts_receivable", "folio",    "TEXT")
    _add_col("accounts_receivable", "venta_id", "INTEGER")

    try:
        conn.commit()
    except Exception:
        pass
