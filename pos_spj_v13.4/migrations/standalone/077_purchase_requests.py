"""
Migration 077 — purchase_requests + purchase_request_items + purchase_request_events

Solicitudes de Compra (Purchase Requests / PR).
Tables referenced by application/purchases/purchase_request_uc.py.
Absence of these tables produced:
    ERROR spj.purchases.pr_uc crear_pr: no such table: purchase_requests
"""


def run(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS purchase_requests (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            folio        TEXT,
            estado       TEXT    NOT NULL DEFAULT 'borrador',
            solicitante  TEXT,
            sucursal_id  INTEGER DEFAULT 1,
            proveedor_id INTEGER,
            notas        TEXT,
            total_est    REAL    DEFAULT 0,
            creado_en    TEXT    DEFAULT (datetime('now')),
            actualizado  TEXT    DEFAULT (datetime('now'))
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS purchase_request_items (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            pr_id              INTEGER NOT NULL
                                   REFERENCES purchase_requests(id) ON DELETE CASCADE,
            producto_id        INTEGER NOT NULL,
            cantidad_solicitada REAL   NOT NULL DEFAULT 1,
            costo_estimado     REAL    DEFAULT 0,
            unidad             TEXT    DEFAULT 'pz',
            notas              TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS purchase_request_events (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            pr_id      INTEGER NOT NULL
                           REFERENCES purchase_requests(id) ON DELETE CASCADE,
            evento     TEXT    NOT NULL,
            usuario    TEXT,
            detalle    TEXT,
            ts         TEXT    DEFAULT (datetime('now'))
        )
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS ix_pr_sucursal_estado
            ON purchase_requests(sucursal_id, estado)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS ix_pr_items_pr_id
            ON purchase_request_items(pr_id)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS ix_pr_events_pr_id
            ON purchase_request_events(pr_id)
    """)

    conn.commit()
