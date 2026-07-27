# migrations/standalone/060_depreciacion_acumulada.py
# Fase 3 — Registro acumulado de depreciación por activo y periodo (Plan Maestro SPJ v13.4)
# Vincula cada asiento mensual de depreciación con el activo y el periodo contable.
# Idempotente — usa CREATE TABLE IF NOT EXISTS y UNIQUE(activo_id, periodo).


def run(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS depreciacion_acumulada (
            id          TEXT NOT NULL    PRIMARY KEY,        -- UUIDv7 acuñado por AssetService
            activo_id   TEXT    NOT NULL,           -- FK activos.id (UUIDv7)
            periodo     TEXT    NOT NULL,          -- 'YYYY-MM'
            monto_mes   REAL    NOT NULL DEFAULT 0, -- cargo mensual
            acumulado   REAL    NOT NULL DEFAULT 0, -- suma histórica hasta este periodo
            cuenta_id   TEXT,                       -- FK opcional a plan_cuentas
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            UNIQUE(activo_id, periodo)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_da_activo
            ON depreciacion_acumulada(activo_id, periodo)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_da_periodo
            ON depreciacion_acumulada(periodo)
    """)
