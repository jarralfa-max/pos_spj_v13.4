# migrations/standalone/057_loyalty_ledger_unificado.py
# Fase 2 — Ledger unificado de fidelización (Plan Maestro SPJ v13.4)
# Consolida acumulación, canje y reversa en una tabla única con saldo_post.


def run(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS loyalty_ledger (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id     INTEGER NOT NULL,
            tipo           TEXT    NOT NULL CHECK(tipo IN
                               ('acumulacion','canje','reversa','ajuste')),
            puntos         INTEGER NOT NULL,          -- + acumulación, - canje/reversa
            monto_equiv    REAL    DEFAULT 0,         -- valor monetario equivalente
            saldo_post     INTEGER DEFAULT 0,         -- saldo después del movimiento
            referencia     TEXT    DEFAULT '',        -- venta_id, folio, etc.
            descripcion    TEXT    DEFAULT '',
            sucursal_id    INTEGER DEFAULT 1,
            usuario        TEXT    DEFAULT '',
            created_at     TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_loyalty_ledger_cliente
            ON loyalty_ledger(cliente_id, created_at)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_loyalty_ledger_tipo
            ON loyalty_ledger(tipo, created_at)
    """)
