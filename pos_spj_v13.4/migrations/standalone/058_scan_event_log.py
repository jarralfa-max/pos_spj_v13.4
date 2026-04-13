# migrations/standalone/058_scan_event_log.py
# Fase 2 — Auditoría de eventos de escaneo (Plan Maestro SPJ v13.4)
# Log de cada código escaneado: tipo detectado, payload filtrado, acción aplicada.


def run(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scan_event_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            raw_code     TEXT    NOT NULL,
            tipo         TEXT    NOT NULL DEFAULT 'desconocido',
            contexto     TEXT    DEFAULT 'auto',   -- producto/cliente/auto
            accion       TEXT    DEFAULT '',       -- producto_agregado/cliente_cargado/etc.
            payload      TEXT    DEFAULT '',       -- JSON filtrado del resultado
            cliente_id   INTEGER,
            producto_id  INTEGER,
            sucursal_id  INTEGER DEFAULT 1,
            usuario      TEXT    DEFAULT '',
            created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_scan_event_log_fecha
            ON scan_event_log(created_at)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_scan_event_log_cliente
            ON scan_event_log(cliente_id, created_at)
    """)
