"""
052_financial_event_log.py — pos_spj v13.4
Crea la tabla financial_event_log para audit trail de operaciones financieras.

Requerimiento: toda operación financiera con impacto contable debe loguear aquí
con cuentas debe/haber para garantizar la regla de doble entrada (debe = haber).

Ver: migrations/MIGRATION_LOG.md — entrada 052
"""


def run(conn):
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS financial_event_log (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp     DATETIME DEFAULT CURRENT_TIMESTAMP,
            evento        TEXT NOT NULL,
            modulo        TEXT NOT NULL,
            referencia_id INTEGER,
            monto         DECIMAL(15,4),
            cuenta_debe   TEXT,
            cuenta_haber  TEXT,
            usuario_id    INTEGER,
            sucursal_id   INTEGER DEFAULT 1,
            metadata      JSON
        );

        CREATE INDEX IF NOT EXISTS idx_fel_timestamp
            ON financial_event_log(timestamp);

        CREATE INDEX IF NOT EXISTS idx_fel_evento
            ON financial_event_log(evento);

        CREATE INDEX IF NOT EXISTS idx_fel_sucursal
            ON financial_event_log(sucursal_id);
    """)

    conn.commit()
