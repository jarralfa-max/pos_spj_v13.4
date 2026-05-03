
# migrations/standalone/038_transfer_suggestions.py
# ── Sugerencias de Transferencia ──────────────────────────────────────────────
# Tabla para persistir y auditar el historial de sugerencias generadas
# por TransferSuggestionEngine (DOS + CV + Exponential Smoothing).
import logging, sqlite3
logger = logging.getLogger("spj.migrations.038")

def run(conn: sqlite3.Connection) -> None:
    _create_transfer_suggestions(conn)
    _create_indexes(conn)
    try: conn.commit()
    except Exception: pass
    logger.info("Migración 038: transfer_suggestions completada.")

def run(conn: sqlite3.Connection) -> None:
    _create_transfer_suggestions(conn)
    _create_indexes(conn)
    try: conn.commit()
    except Exception: pass
    logger.info("Migración 038: transfer_suggestions completada.")

def _create_transfer_suggestions(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transfer_suggestions (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id       INTEGER NOT NULL,
            origin_branch_id INTEGER NOT NULL,
            dest_branch_id   INTEGER NOT NULL,
            qty_suggested    REAL    NOT NULL,
            origin_dos       REAL    DEFAULT 0,
            dest_dos         REAL    DEFAULT 0,
            cv               REAL    DEFAULT 0,
            urgency_score    REAL    DEFAULT 0,
            reason           TEXT,
            status           TEXT    DEFAULT 'pending'
                             CHECK(status IN ('pending','applied','dismissed')),
            transfer_id      TEXT,   -- UUID del transfer creado si se aplicó
            generated_at     TEXT    DEFAULT (datetime('now')),
            applied_at       TEXT,
            applied_by       TEXT,
            FOREIGN KEY (product_id)       REFERENCES productos(id),
            FOREIGN KEY (origin_branch_id) REFERENCES sucursales(id),
            FOREIGN KEY (dest_branch_id)   REFERENCES sucursales(id)
        )""")
    logger.info("transfer_suggestions creada/verificada.")

def _create_indexes(conn):
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tsug_score   "
        "ON transfer_suggestions(urgency_score DESC)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tsug_status  "
        "ON transfer_suggestions(status)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tsug_prod    "
        "ON transfer_suggestions(product_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tsug_gen     "
        "ON transfer_suggestions(generated_at)")
    logger.info("Índices transfer_suggestions creados.")
