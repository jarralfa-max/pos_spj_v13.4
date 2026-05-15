"""Migration 074 — compras.archivo_adjunto: optional file path for invoice/remision attachment."""


def run(conn):
    try:
        conn.execute("ALTER TABLE compras ADD COLUMN archivo_adjunto TEXT")
    except Exception:
        pass  # column already exists
    conn.commit()
