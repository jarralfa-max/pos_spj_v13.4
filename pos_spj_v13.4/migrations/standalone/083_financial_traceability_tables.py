# migrations/standalone/083_financial_traceability_tables.py — SPJ ERP v13.4
"""
Trazabilidad financiera end-to-end.

Crea tablas canónicas NUEVAS para trazabilidad, idempotencia y conciliación.
NO renombra ni elimina tablas existentes (accounts_payable, accounts_receivable,
financial_event_log, treasury_ledger, activos, etc. siguen intactas).

Las nuevas tablas actúan como capa unificada encima de las legacy, permitiendo:
  - operation_id UNIQUE: garantiza idempotencia en todas las escrituras financieras
  - source_module + source_id: enlaza cada registro a su evento de origen
  - financial_trace_log: bitácora técnica de cada operación de trazabilidad
  - reconciliation_records: detecta inconsistencias entre módulos

Tablas creadas:
  financial_documents          — documentos (CxC, CxP, nómina, activos)
  treasury_movements           — movimientos reales de dinero
  journal_entries              — asientos contables idempotentes
  fixed_assets                 — activos fijos
  asset_depreciation_entries   — depreciaciones por período
  maintenance_records          — mantenimientos
  operating_supplies           — insumos operativos
  financial_trace_log          — bitácora de trazabilidad
  reconciliation_records       — conciliación
"""


def run(conn):
    conn.executescript("""
        -- ── DOCUMENTOS FINANCIEROS ────────────────────────────────────────────
        -- Capa unificada: CxC, CxP, nómina por pagar, activo pendiente, etc.
        -- Coexiste con accounts_payable / accounts_receivable (legacy).
        CREATE TABLE IF NOT EXISTS financial_documents (
            id                  TEXT    PRIMARY KEY,
            document_type       TEXT    NOT NULL,       -- receivable|payable|payroll|maintenance|asset
            status              TEXT    NOT NULL DEFAULT 'pending',
            source_module       TEXT    NOT NULL,       -- ventas|compras|nomina|mantenimiento|activos
            source_id           TEXT,
            source_folio        TEXT    DEFAULT '',
            party_type          TEXT    DEFAULT '',     -- customer|supplier|employee
            party_id            TEXT,
            original_amount     REAL    NOT NULL,
            balance             REAL    NOT NULL,
            currency            TEXT    DEFAULT 'MXN',
            due_date            TEXT,
            branch_id           TEXT,
            user                TEXT    DEFAULT 'sistema',
            operation_id        TEXT    UNIQUE NOT NULL,
            metadata_json       TEXT    DEFAULT '{}',
            created_at          TEXT    DEFAULT (datetime('now')),
            updated_at          TEXT    DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_fd_source
            ON financial_documents(source_module, source_id);
        CREATE INDEX IF NOT EXISTS idx_fd_party
            ON financial_documents(party_type, party_id);
        CREATE INDEX IF NOT EXISTS idx_fd_status
            ON financial_documents(status);

        -- ── MOVIMIENTOS DE TESORERÍA ──────────────────────────────────────────
        -- Dinero real confirmado. Coexiste con treasury_ledger (legacy).
        CREATE TABLE IF NOT EXISTS treasury_movements (
            id                      TEXT    PRIMARY KEY,
            movement_type           TEXT    NOT NULL,   -- inflow|outflow
            direction               TEXT    NOT NULL,   -- in|out
            amount                  REAL    NOT NULL,
            payment_method          TEXT    DEFAULT 'efectivo',
            account                 TEXT    DEFAULT 'caja',
            status                  TEXT    DEFAULT 'confirmed',
            source_module           TEXT    NOT NULL,
            source_id               TEXT,
            source_folio            TEXT    DEFAULT '',
            financial_document_id   TEXT,
            branch_id               TEXT,
            user                    TEXT    DEFAULT 'sistema',
            operation_id            TEXT    UNIQUE NOT NULL,
            metadata_json           TEXT    DEFAULT '{}',
            created_at              TEXT    DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_tm_source
            ON treasury_movements(source_module, source_id);
        CREATE INDEX IF NOT EXISTS idx_tm_status
            ON treasury_movements(status);
        CREATE INDEX IF NOT EXISTS idx_tm_branch
            ON treasury_movements(branch_id, created_at);

        -- ── ASIENTOS CONTABLES ────────────────────────────────────────────────
        -- Idempotentes por operation_id. Coexiste con financial_event_log (legacy).
        CREATE TABLE IF NOT EXISTS journal_entries (
            id              TEXT    PRIMARY KEY,
            event_type      TEXT    NOT NULL,
            source_module   TEXT    NOT NULL,
            source_id       TEXT,
            source_folio    TEXT    DEFAULT '',
            debit_account   TEXT    NOT NULL,
            credit_account  TEXT    NOT NULL,
            amount          REAL    NOT NULL,
            branch_id       TEXT,
            user            TEXT    DEFAULT 'sistema',
            operation_id    TEXT    UNIQUE NOT NULL,
            metadata_json   TEXT    DEFAULT '{}',
            created_at      TEXT    DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_je_source
            ON journal_entries(source_module, source_id);
        CREATE INDEX IF NOT EXISTS idx_je_debit
            ON journal_entries(debit_account);
        CREATE INDEX IF NOT EXISTS idx_je_credit
            ON journal_entries(credit_account);

        -- ── ACTIVOS FIJOS ─────────────────────────────────────────────────────
        -- Canónico para trazabilidad. Coexiste con tabla 'activos' (legacy).
        CREATE TABLE IF NOT EXISTS fixed_assets (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_name              TEXT    NOT NULL,
            asset_type              TEXT    NOT NULL,   -- equipment|vehicle|furniture|computer|other
            acquisition_date        TEXT    NOT NULL,
            acquisition_cost        REAL    NOT NULL,
            current_value           REAL    NOT NULL,
            accumulated_depreciation REAL   DEFAULT 0.0,
            depreciation_method     TEXT    DEFAULT 'straight_line',
            useful_life_months      INTEGER DEFAULT 60,
            status                  TEXT    DEFAULT 'active',  -- active|disposed|sold
            supplier_id             INTEGER,
            branch_id               INTEGER DEFAULT 1,
            source_module           TEXT    DEFAULT 'activos',
            source_id               INTEGER,
            source_folio            TEXT    DEFAULT '',
            financial_document_id   INTEGER,
            treasury_movement_id    INTEGER,
            journal_entry_id        INTEGER,
            operation_id            TEXT    UNIQUE NOT NULL,
            metadata_json           TEXT    DEFAULT '{}',
            created_at              TEXT    DEFAULT (datetime('now')),
            updated_at              TEXT    DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_fa_status
            ON fixed_assets(status, branch_id);

        -- ── DEPRECIACIONES ────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS asset_depreciation_entries (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id        INTEGER NOT NULL,
            period          TEXT    NOT NULL,   -- 'YYYY-MM'
            amount          REAL    NOT NULL,
            journal_entry_id INTEGER,
            operation_id    TEXT    UNIQUE NOT NULL,  -- asset_id-YYYY-MM
            created_at      TEXT    DEFAULT (datetime('now')),
            FOREIGN KEY (asset_id) REFERENCES fixed_assets(id)
        );
        CREATE INDEX IF NOT EXISTS idx_ade_asset_period
            ON asset_depreciation_entries(asset_id, period);

        -- ── MANTENIMIENTOS ────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS maintenance_records (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id                INTEGER,
            maintenance_type        TEXT    NOT NULL,  -- preventive|corrective|repair|parts|labor
            description             TEXT    DEFAULT '',
            amount                  REAL    NOT NULL,
            status                  TEXT    DEFAULT 'pending',  -- pending|paid|cancelled|capitalized
            supplier_id             INTEGER,
            branch_id               INTEGER DEFAULT 1,
            source_module           TEXT    DEFAULT 'mantenimiento',
            source_id               INTEGER,
            source_folio            TEXT    DEFAULT '',
            financial_document_id   INTEGER,
            treasury_movement_id    INTEGER,
            journal_entry_id        INTEGER,
            capitalizable           INTEGER DEFAULT 0,
            operation_id            TEXT    UNIQUE NOT NULL,
            metadata_json           TEXT    DEFAULT '{}',
            created_at              TEXT    DEFAULT (datetime('now')),
            updated_at              TEXT    DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_mr_status
            ON maintenance_records(status, branch_id);

        -- ── INSUMOS OPERATIVOS ────────────────────────────────────────────────
        -- Rollos térmicos, etiquetas, limpieza, papelería, bolsas, empaques.
        CREATE TABLE IF NOT EXISTS operating_supplies (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            supply_type             TEXT    NOT NULL,  -- thermal_rolls|labels|cleaning|stationery|bags|packaging|other
            description             TEXT    DEFAULT '',
            quantity                REAL    DEFAULT 1,
            unit_cost               REAL    NOT NULL,
            total_amount            REAL    NOT NULL,
            status                  TEXT    DEFAULT 'pending',  -- pending|paid|cancelled
            supplier_id             INTEGER,
            branch_id               INTEGER DEFAULT 1,
            source_module           TEXT    DEFAULT 'compras',
            source_id               INTEGER,
            source_folio            TEXT    DEFAULT '',
            financial_document_id   INTEGER,
            treasury_movement_id    INTEGER,
            journal_entry_id        INTEGER,
            operation_id            TEXT    UNIQUE NOT NULL,
            metadata_json           TEXT    DEFAULT '{}',
            created_at              TEXT    DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_os_type
            ON operating_supplies(supply_type, branch_id);

        -- ── BITÁCORA DE TRAZABILIDAD ──────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS financial_trace_log (
            id              TEXT    PRIMARY KEY,
            event_type      TEXT    NOT NULL,
            source_module   TEXT    NOT NULL,
            source_id       TEXT,
            source_folio    TEXT    DEFAULT '',
            operation_id    TEXT    NOT NULL,
            trace_status    TEXT    NOT NULL DEFAULT 'started',  -- started|completed|failed|skipped
            payload_json    TEXT    DEFAULT '{}',
            error_message   TEXT    DEFAULT '',
            created_at      TEXT    DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_ftl_op
            ON financial_trace_log(operation_id);
        CREATE INDEX IF NOT EXISTS idx_ftl_status
            ON financial_trace_log(trace_status, event_type);

        -- ── REGISTROS DE CONCILIACIÓN ─────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS reconciliation_records (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            check_type      TEXT    NOT NULL,  -- sale_vs_treasury|cxc_journal|cxp_journal|etc.
            source_module   TEXT    NOT NULL,
            source_id       INTEGER,
            expected_amount REAL    DEFAULT 0,
            actual_amount   REAL    DEFAULT 0,
            difference      REAL    DEFAULT 0,
            status          TEXT    DEFAULT 'pending',  -- ok|discrepancy|resolved|ignored
            branch_id       INTEGER DEFAULT 1,
            user            TEXT    DEFAULT 'sistema',
            operation_id    TEXT,
            metadata_json   TEXT    DEFAULT '{}',
            created_at      TEXT    DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_rr_status
            ON reconciliation_records(status, check_type);
        CREATE INDEX IF NOT EXISTS idx_rr_source
            ON reconciliation_records(source_module, source_id);
    """)
