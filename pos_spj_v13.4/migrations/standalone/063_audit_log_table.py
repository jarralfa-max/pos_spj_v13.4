# migrations/standalone/063_audit_log_table.py — SPJ ERP
"""
FASE 7 — Tabla audit_log (columnas en inglés, spec ERP).
Coexiste con audit_logs (columnas en español, legacy POS) — no se toca ni elimina.
"""


def run(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER,
            action        TEXT    NOT NULL,
            entity        TEXT    NOT NULL,
            entity_id     INTEGER,
            timestamp     TEXT    NOT NULL DEFAULT (datetime('now')),
            sucursal_id   INTEGER NOT NULL DEFAULT 1,
            metadata_json TEXT    DEFAULT '{}'
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_log_user
            ON audit_log(user_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_log_entity
            ON audit_log(entity, entity_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp
            ON audit_log(timestamp)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_log_sucursal
            ON audit_log(sucursal_id)
    """)
    try:
        conn.commit()
    except Exception:
        pass
