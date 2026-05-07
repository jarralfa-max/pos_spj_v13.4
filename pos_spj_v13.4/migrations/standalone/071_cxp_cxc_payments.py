"""
Migration 071 — cxp_payments + cxc_payments tables

These payment-log tables track individual abonos against accounts_payable
(CXP) and accounts_receivable (CXC).  treasury_service.abonar_cuenta_por_pagar()
and abonar_cuenta_por_cobrar() insert into these tables but they were never
created by a prior migration.
"""


def run(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cxp_payments (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ap_id       INTEGER NOT NULL REFERENCES accounts_payable(id),
            monto       REAL    NOT NULL,
            metodo_pago TEXT    NOT NULL DEFAULT 'efectivo',
            usuario     TEXT    NOT NULL DEFAULT '',
            fecha       TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_cxp_payments_ap ON cxp_payments(ap_id)"
    )

    conn.execute("""
        CREATE TABLE IF NOT EXISTS cxc_payments (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ar_id       INTEGER NOT NULL REFERENCES accounts_receivable(id),
            monto       REAL    NOT NULL,
            metodo_pago TEXT    NOT NULL DEFAULT 'efectivo',
            usuario     TEXT    NOT NULL DEFAULT '',
            fecha       TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_cxc_payments_ar ON cxc_payments(ar_id)"
    )

    try:
        conn.commit()
    except Exception:
        pass
