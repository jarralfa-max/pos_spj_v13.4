# migrations/standalone/082_treasury_tables.py — SPJ ERP v13.4
"""
Migración formal de las tablas de Tesorería.

Estas tablas eran creadas en runtime por TreasuryService._ensure_tables().
FASE 5 auditoría finanzas: moverlas a migración garantiza que existan antes
de que cualquier servicio intente usarlas (fail-fast en bootstrap, no en runtime).

Tablas:
  treasury_capital             — inyecciones y retiros de capital
  treasury_ledger              — movimientos de caja (ingresos/egresos)
  treasury_gastos_fijos        — gastos fijos recurrentes configurados
  pagos_cobros                 — documentos de pago/cobro unificados
  pagos_cobros_aplicaciones    — aplicación de pagos_cobros a documentos (CxP/CxC)
"""


def run(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS treasury_capital (
            id          TEXT    PRIMARY KEY,
            fecha       TEXT    DEFAULT (datetime('now')),
            tipo        TEXT    NOT NULL,
            monto       REAL    NOT NULL,
            descripcion TEXT    DEFAULT '',
            usuario     TEXT    DEFAULT '',
            sucursal_id TEXT
        );

        CREATE TABLE IF NOT EXISTS treasury_ledger (
            id          TEXT    PRIMARY KEY,
            fecha       TEXT    DEFAULT (datetime('now')),
            tipo        TEXT    NOT NULL,
            categoria   TEXT    NOT NULL,
            concepto    TEXT    DEFAULT '',
            ingreso     REAL    DEFAULT 0,
            egreso      REAL    DEFAULT 0,
            sucursal_id TEXT,
            referencia  TEXT    DEFAULT '',
            usuario     TEXT    DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_tl_fecha ON treasury_ledger(fecha);
        CREATE INDEX IF NOT EXISTS idx_tl_cat   ON treasury_ledger(categoria);

        CREATE TABLE IF NOT EXISTS treasury_gastos_fijos (
            id             TEXT    PRIMARY KEY,
            categoria      TEXT    NOT NULL,
            nombre         TEXT    NOT NULL,
            monto_mensual  REAL    NOT NULL,
            dia_pago       INTEGER DEFAULT 1,
            sucursal_id    TEXT,
            activo         INTEGER DEFAULT 1
        );

        -- gastos_futuros (tabla + índices) se define en m000_base_schema
        -- con identidad TEXT UUIDv7; ya no se crea aquí.

        CREATE TABLE IF NOT EXISTS pagos_cobros (
            id              TEXT    PRIMARY KEY,
            folio           TEXT    UNIQUE,
            tipo_operacion  TEXT    NOT NULL,
            tercero_id      TEXT,
            tercero_tipo    TEXT    NOT NULL,
            monto_total     REAL    NOT NULL,
            forma_pago      TEXT    DEFAULT 'efectivo',
            cuenta_origen   TEXT    DEFAULT '',
            fecha           TEXT    DEFAULT (datetime('now')),
            usuario_id      TEXT    DEFAULT '',
            estado          TEXT    DEFAULT 'aplicado',
            referencia      TEXT    DEFAULT '',
            created_at      TEXT    DEFAULT (datetime('now')),
            updated_at      TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS pagos_cobros_aplicaciones (
            id                          TEXT    PRIMARY KEY,
            pago_cobro_id               TEXT    NOT NULL,
            documento_id                TEXT    NOT NULL,
            tipo_documento              TEXT    NOT NULL,
            monto_aplicado              REAL    NOT NULL,
            saldo_anterior_documento    REAL    NOT NULL,
            saldo_posterior_documento   REAL    NOT NULL,
            created_at                  TEXT    DEFAULT (datetime('now'))
        );
    """)
