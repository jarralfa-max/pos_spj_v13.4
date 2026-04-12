# migrations/standalone/056_print_job_log.py
# Fase 1 — Bitácora de impresión (Plan Maestro SPJ v13.4)
# Registra cada trabajo de impresión: ticket_id, plantilla, impresora,
# estado de cola, reintentos y monto (para auditoría financiera).


def run(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS print_job_log (
            id          INTEGER  PRIMARY KEY AUTOINCREMENT,
            job_id      TEXT     NOT NULL,
            job_type    TEXT     NOT NULL DEFAULT 'ticket',
            plantilla   TEXT     DEFAULT '',
            impresora   TEXT     DEFAULT '',
            folio       TEXT     DEFAULT '',
            estado      TEXT     NOT NULL DEFAULT 'queued',
            reintentos  INTEGER  DEFAULT 0,
            total       REAL     DEFAULT 0,
            sucursal_id INTEGER  DEFAULT 1,
            usuario     TEXT     DEFAULT '',
            error_msg   TEXT     DEFAULT '',
            created_at  TEXT     NOT NULL DEFAULT (datetime('now')),
            finished_at TEXT
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_print_job_log_job_id
            ON print_job_log(job_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_print_job_log_estado
            ON print_job_log(estado, created_at)
    """)
