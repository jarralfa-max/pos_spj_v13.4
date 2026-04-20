# migrations/standalone/064_fix_missing_columns.py — SPJ ERP
"""
Hotfix — columnas faltantes detectadas en producción.
Defensivo: _add_col() no falla si la columna ya existe (PRAGMA table_info).
"""
import logging

logger = logging.getLogger("spj.migrations.064")


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
                logger.info("064: added %s.%s", table, col)
            except Exception as e:
                logger.warning("064: could not add %s.%s: %s", table, col, e)

    # gastos_mes() selects g.recurrente
    _add_col("gastos", "recurrente", "INTEGER DEFAULT 0")

    # cuentas_por_cobrar() + sync_cxc_from_ventas() join clientes on apellido_paterno
    _add_col("clientes", "apellido_paterno", "TEXT DEFAULT ''")

    # sync_cxp_from_compras() filters ci.saldo_pendiente > 0
    _add_col("compras_inventariables", "saldo_pendiente", "REAL DEFAULT 0")

    # Also ensure accounts_receivable.venta_id exists (used by sync_cxc_from_ventas)
    _add_col("accounts_receivable", "venta_id", "INTEGER")

    try:
        conn.commit()
    except Exception:
        pass
