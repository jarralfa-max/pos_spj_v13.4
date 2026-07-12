# migrations/standalone/084_capital_movements.py — SPJ ERP v13.4
"""
Movimientos de capital / patrimonio del negocio.

Registra inyecciones de capital, retiros y ajustes de patrimonio de los socios.
Coexiste con treasury_ledger (operaciones diarias) — capital es capa de patrimonio,
no tesorería operativa.

Tabla creada:
  capital_movements  — movimientos de capital con trazabilidad completa
"""


def run(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS capital_movements (
            id                  TEXT NOT NULL    PRIMARY KEY,
            movement_type       TEXT    NOT NULL DEFAULT 'injection',
                                        -- injection | withdrawal | adjustment | opening_balance
            amount              REAL    NOT NULL CHECK(amount > 0),
            concept             TEXT    NOT NULL DEFAULT '',
            partner_name        TEXT    DEFAULT '',   -- nombre del socio/origen
            partner_id          TEXT,                 -- FK opcional a socios si existe
            payment_method      TEXT    DEFAULT 'efectivo',
            reference           TEXT    DEFAULT '',   -- número de transferencia, cheque, etc.
            branch_id           TEXT,
            user                TEXT    DEFAULT 'sistema',
            status              TEXT    NOT NULL DEFAULT 'registered',
                                        -- registered | pending | cancelled
            operation_id        TEXT    UNIQUE NOT NULL,
            journal_entry_id    TEXT,                 -- FK a journal_entries si aplica
            treasury_movement_id TEXT,                -- FK a treasury_movements si aplica
            metadata_json       TEXT    DEFAULT '{}',
            created_at          TEXT    DEFAULT (datetime('now')),
            updated_at          TEXT    DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_capital_movements_type
            ON capital_movements(movement_type);

        CREATE INDEX IF NOT EXISTS idx_capital_movements_branch
            ON capital_movements(branch_id, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_capital_movements_status
            ON capital_movements(status);
    """)
