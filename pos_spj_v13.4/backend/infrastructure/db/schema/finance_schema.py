"""Finance bounded context — born-clean UUIDv7 schema (single source of truth).

Rules:
- Every id is ``TEXT PRIMARY KEY`` holding a lowercase UUIDv7 (PostgreSQL: UUID).
- Every monetary column is ``TEXT`` holding a canonical decimal string
  (PostgreSQL: NUMERIC); floats/REAL are forbidden for money.
- Idempotency is structural: UNIQUE(operation_id) and
  UNIQUE(source_module, source_document_id, posting_purpose).
- No AUTOINCREMENT, no lastrowid, no legacy compatibility, no data rescue.

The only entry point that may execute this DDL is a migration in ``migrations/``.
"""

from __future__ import annotations

FINANCE_TABLES: tuple[str, ...] = (
    "finance_outbox",
    "finance_processed_events",
    "commercial_obligations",
    "posting_profiles",
    "fixed_assets",
    "budget_lines",
    "budgets",
    "profit_centers",
    "cost_centers",
    "reconciliation_matches",
    "reconciliations",
    "bank_statement_lines",
    "bank_statements",
    "treasury_accounts",
    "supplier_payments",
    "payables",
    "collections",
    "receivables",
    "financial_documents",
    "journal_lines",
    "journal_entries",
    "journals",
    "fiscal_periods",
    "accounts",
)

#: Legacy finance tables from all previous generations (m000/035/052/059/061/066/082/083/084).
#: Names colliding with the new schema (journal_entries, financial_documents,
#: fixed_assets) are dropped BEFORE ``create_finance_schema`` recreates them clean.
LEGACY_FINANCE_TABLES: tuple[str, ...] = (
    "journal_entries",
    "journal_lines",
    "financial_documents",
    "fixed_assets",
    "maintenance_records",
    "operating_supplies",
    "accounts_payable",
    "accounts_receivable",
    "cuentas_por_cobrar",
    "cuentas_por_pagar",
    "plan_cuentas",
    "financial_event_log",
    "terceros",
    "cuentas_financieras",
    "catalogo_cuentas_contables",
    "documentos_financieros",
    "pagos_cobros",
    "pagos_cobros_aplicaciones",
    "movimientos_financieros",
    "ledger_financiero",
    "conciliaciones_financieras",
    "cortes_caja_erp",
    "treasury_capital",
    "treasury_ledger",
    "treasury_gastos_fijos",
    "financial_documents_legacy",
    "treasury_movements",
    "asset_depreciation_entries",
    "financial_trace_log",
    "reconciliation_records",
    "capital_movements",
    "activos_depreciacion",
    "growth_ledger",
    "production_cost_ledger",
    "loyalty_budget_caps",
)

_DDL = """
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    account_type TEXT NOT NULL CHECK (account_type IN (
        'ASSET','LIABILITY','EQUITY','REVENUE','CONTRA_REVENUE',
        'COST_OF_SALES','EXPENSE','OTHER_INCOME','OTHER_EXPENSE')),
    normal_balance TEXT NOT NULL CHECK (normal_balance IN ('DEBIT','CREDIT')),
    parent_account_id TEXT REFERENCES accounts(id),
    posting_allowed INTEGER NOT NULL DEFAULT 1,
    reconciliation_required INTEGER NOT NULL DEFAULT 0,
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    branch_restriction_id TEXT,
    cash_flow_category TEXT NOT NULL DEFAULT 'NONE'
        CHECK (cash_flow_category IN ('OPERATING','INVESTING','FINANCING','NONE')),
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fiscal_periods (
    id TEXT PRIMARY KEY,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','SOFT_CLOSED','CLOSED')),
    opened_at TEXT NOT NULL,
    soft_closed_at TEXT,
    closed_at TEXT,
    reopened_at TEXT,
    closed_by TEXT,
    reopen_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (year, month)
);

CREATE TABLE IF NOT EXISTS journals (
    id TEXT PRIMARY KEY,
    journal_type TEXT NOT NULL UNIQUE CHECK (journal_type IN (
        'SALES','PURCHASES','CASH','BANK','PAYROLL','INVENTORY','LOYALTY',
        'COMMERCIAL_INSTRUMENTS','FIXED_ASSETS','ADJUSTMENTS','GENERAL','OPENING','CLOSING')),
    name TEXT NOT NULL,
    entry_sequence_prefix TEXT NOT NULL,
    next_sequence INTEGER NOT NULL DEFAULT 1,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS journal_entries (
    id TEXT PRIMARY KEY,
    journal_id TEXT NOT NULL REFERENCES journals(id),
    entry_number TEXT NOT NULL UNIQUE,
    entry_date TEXT NOT NULL,
    fiscal_period_id TEXT NOT NULL REFERENCES fiscal_periods(id),
    description TEXT NOT NULL DEFAULT '',
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    status TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN (
        'DRAFT','VALIDATED','POSTED','REVERSED','CANCELLED')),
    source_module TEXT NOT NULL,
    source_document_id TEXT NOT NULL,
    posting_purpose TEXT NOT NULL,
    operation_id TEXT NOT NULL UNIQUE,
    branch_id TEXT,
    reversal_of_entry_id TEXT REFERENCES journal_entries(id),
    reversed_by_entry_id TEXT REFERENCES journal_entries(id),
    posted_at TEXT,
    created_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (source_module, source_document_id, posting_purpose)
);

CREATE TABLE IF NOT EXISTS journal_lines (
    id TEXT PRIMARY KEY,
    journal_entry_id TEXT NOT NULL REFERENCES journal_entries(id) ON DELETE CASCADE,
    account_id TEXT NOT NULL REFERENCES accounts(id),
    description TEXT NOT NULL DEFAULT '',
    debit_amount TEXT NOT NULL DEFAULT '0.00',
    credit_amount TEXT NOT NULL DEFAULT '0.00',
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    cost_center_id TEXT,
    profit_center_id TEXT,
    branch_id TEXT,
    line_index INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS financial_documents (
    id TEXT PRIMARY KEY,
    document_type TEXT NOT NULL,
    document_number TEXT NOT NULL,
    issue_date TEXT NOT NULL,
    due_date TEXT,
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    exchange_rate TEXT NOT NULL DEFAULT '1',
    subtotal TEXT,
    tax_amount TEXT,
    discount_amount TEXT,
    total_amount TEXT NOT NULL,
    outstanding_amount TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN (
        'DRAFT','OPEN','PARTIALLY_SETTLED','SETTLED','CANCELLED')),
    branch_id TEXT,
    customer_id TEXT,
    supplier_id TEXT,
    source_module TEXT NOT NULL,
    source_document_id TEXT NOT NULL,
    operation_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (source_module, source_document_id, document_type)
);

CREATE TABLE IF NOT EXISTS receivables (
    id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    financial_document_id TEXT NOT NULL REFERENCES financial_documents(id),
    original_amount TEXT NOT NULL,
    outstanding_amount TEXT NOT NULL,
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    issue_date TEXT NOT NULL,
    due_date TEXT,
    branch_id TEXT,
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN (
        'OPEN','PARTIALLY_COLLECTED','SETTLED','WRITTEN_OFF','CANCELLED')),
    operation_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (financial_document_id)
);

CREATE TABLE IF NOT EXISTS collections (
    id TEXT PRIMARY KEY,
    receivable_id TEXT NOT NULL REFERENCES receivables(id),
    customer_id TEXT NOT NULL,
    amount TEXT NOT NULL,
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    collection_date TEXT NOT NULL,
    treasury_account_id TEXT NOT NULL,
    journal_entry_id TEXT REFERENCES journal_entries(id),
    reference TEXT NOT NULL DEFAULT '',
    branch_id TEXT,
    operation_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS payables (
    id TEXT PRIMARY KEY,
    supplier_id TEXT NOT NULL,
    financial_document_id TEXT NOT NULL REFERENCES financial_documents(id),
    original_amount TEXT NOT NULL,
    outstanding_amount TEXT NOT NULL,
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    issue_date TEXT NOT NULL,
    due_date TEXT,
    branch_id TEXT,
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN (
        'OPEN','SCHEDULED','PARTIALLY_PAID','SETTLED','CANCELLED')),
    operation_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (financial_document_id)
);

CREATE TABLE IF NOT EXISTS supplier_payments (
    id TEXT PRIMARY KEY,
    payable_id TEXT NOT NULL REFERENCES payables(id),
    supplier_id TEXT NOT NULL,
    amount TEXT NOT NULL,
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    scheduled_date TEXT NOT NULL,
    treasury_account_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'SCHEDULED' CHECK (status IN (
        'SCHEDULED','AUTHORIZED','EXECUTED','RECONCILED','CANCELLED')),
    scheduled_by TEXT,
    authorized_by TEXT,
    authorized_at TEXT,
    executed_at TEXT,
    executed_date TEXT,
    journal_entry_id TEXT REFERENCES journal_entries(id),
    reconciled_at TEXT,
    reference TEXT NOT NULL DEFAULT '',
    branch_id TEXT,
    operation_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS treasury_accounts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    account_type TEXT NOT NULL CHECK (account_type IN (
        'BANK','CASH_REGISTER','PETTY_CASH','GENERAL_CASH',
        'PAYMENT_PROCESSOR','DIGITAL_WALLET','CLEARING_ACCOUNT')),
    ledger_account_id TEXT NOT NULL REFERENCES accounts(id),
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    branch_id TEXT,
    bank_name TEXT,
    bank_account_number TEXT,
    requires_reconciliation INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bank_statements (
    id TEXT PRIMARY KEY,
    treasury_account_id TEXT NOT NULL REFERENCES treasury_accounts(id),
    statement_date TEXT NOT NULL,
    opening_balance TEXT NOT NULL,
    closing_balance TEXT NOT NULL,
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    operation_id TEXT NOT NULL UNIQUE,
    imported_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bank_statement_lines (
    id TEXT PRIMARY KEY,
    bank_statement_id TEXT NOT NULL REFERENCES bank_statements(id) ON DELETE CASCADE,
    transaction_date TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    amount TEXT NOT NULL,
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    external_reference TEXT NOT NULL DEFAULT '',
    matched_journal_line_id TEXT REFERENCES journal_lines(id),
    reconciled INTEGER NOT NULL DEFAULT 0,
    line_index INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS reconciliations (
    id TEXT PRIMARY KEY,
    treasury_account_id TEXT NOT NULL REFERENCES treasury_accounts(id),
    bank_statement_id TEXT NOT NULL REFERENCES bank_statements(id),
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN (
        'OPEN','IN_PROGRESS','COMPLETED','REVERTED')),
    completed_by TEXT,
    completed_at TEXT,
    reverted_by TEXT,
    revert_reason TEXT,
    operation_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reconciliation_matches (
    id TEXT PRIMARY KEY,
    reconciliation_id TEXT NOT NULL REFERENCES reconciliations(id) ON DELETE CASCADE,
    bank_statement_line_id TEXT NOT NULL REFERENCES bank_statement_lines(id),
    journal_line_id TEXT NOT NULL REFERENCES journal_lines(id),
    matched_by TEXT NOT NULL,
    matched_at TEXT NOT NULL,
    UNIQUE (reconciliation_id, bank_statement_line_id),
    UNIQUE (reconciliation_id, journal_line_id)
);

CREATE TABLE IF NOT EXISTS cost_centers (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    parent_id TEXT REFERENCES cost_centers(id),
    branch_id TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS profit_centers (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    branch_id TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS budgets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    fiscal_year INTEGER NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN (
        'DRAFT','SUBMITTED','APPROVED','CLOSED','REJECTED')),
    submitted_by TEXT,
    approved_by TEXT,
    approved_at TEXT,
    branch_id TEXT,
    operation_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (name, fiscal_year, version)
);

CREATE TABLE IF NOT EXISTS budget_lines (
    id TEXT PRIMARY KEY,
    budget_id TEXT NOT NULL REFERENCES budgets(id) ON DELETE CASCADE,
    account_id TEXT NOT NULL REFERENCES accounts(id),
    period_code TEXT NOT NULL,
    planned_amount TEXT NOT NULL,
    committed_amount TEXT NOT NULL DEFAULT '0.00',
    accrued_amount TEXT NOT NULL DEFAULT '0.00',
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    cost_center_id TEXT REFERENCES cost_centers(id),
    branch_id TEXT,
    UNIQUE (budget_id, account_id, period_code, cost_center_id)
);

CREATE TABLE IF NOT EXISTS fixed_assets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    acquisition_cost TEXT NOT NULL,
    residual_value TEXT NOT NULL DEFAULT '0.00',
    accumulated_depreciation TEXT NOT NULL DEFAULT '0.00',
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    useful_life_months INTEGER NOT NULL,
    depreciation_method TEXT NOT NULL DEFAULT 'STRAIGHT_LINE',
    status TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN (
        'DRAFT','CAPITALIZED','FULLY_DEPRECIATED','DISPOSED')),
    capitalization_date TEXT,
    asset_account_id TEXT REFERENCES accounts(id),
    depreciation_expense_account_id TEXT REFERENCES accounts(id),
    accumulated_depreciation_account_id TEXT REFERENCES accounts(id),
    last_depreciated_period TEXT,
    disposal_date TEXT,
    disposal_journal_entry_id TEXT REFERENCES journal_entries(id),
    branch_id TEXT,
    cost_center_id TEXT REFERENCES cost_centers(id),
    operation_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS posting_profiles (
    id TEXT PRIMARY KEY,
    profile_key TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    accounts_json TEXT NOT NULL,
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    instrument_type TEXT,
    program_id TEXT,
    campaign_id TEXT,
    branch_id TEXT,
    customer_type TEXT,
    currency_code TEXT,
    funding_party TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_posting_profiles_key
    ON posting_profiles (profile_key, effective_from);

CREATE TABLE IF NOT EXISTS commercial_obligations (
    id TEXT PRIMARY KEY,
    instrument_type TEXT NOT NULL CHECK (instrument_type IN (
        'LOYALTY_POINTS','PROMOTIONAL_COUPON','DISCOUNT_COUPON','REFUND_VOUCHER',
        'STORE_CREDIT','GIFT_CARD','PREPAID_VOUCHER','PROMOTIONAL_BALANCE',
        'CUSTOMER_WALLET','THIRD_PARTY_VOUCHER')),
    source_module TEXT NOT NULL,
    source_instrument_id TEXT NOT NULL,
    recognition_basis TEXT NOT NULL CHECK (recognition_basis IN (
        'LIABILITY','CONTRA_REVENUE','PROMOTIONAL_EXPENSE',
        'THIRD_PARTY_RECEIVABLE','NO_INITIAL_RECOGNITION')),
    customer_id TEXT,
    branch_id TEXT,
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    original_amount TEXT NOT NULL,
    recognized_amount TEXT NOT NULL,
    redeemed_amount TEXT NOT NULL DEFAULT '0.00',
    released_amount TEXT NOT NULL DEFAULT '0.00',
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN (
        'PENDING_RECOGNITION','OPEN','PARTIALLY_REDEEMED','REDEEMED',
        'EXPIRED','CANCELLED','REVERSED')),
    issued_at TEXT,
    expires_at TEXT,
    operation_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (instrument_type, source_module, source_instrument_id)
);

CREATE TABLE IF NOT EXISTS finance_processed_events (
    event_id TEXT PRIMARY KEY,
    event_name TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    processed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS finance_outbox (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    event_name TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','DISPATCHED')),
    created_at TEXT NOT NULL,
    dispatched_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_journal_entries_period ON journal_entries (fiscal_period_id, status);
CREATE INDEX IF NOT EXISTS idx_journal_entries_date ON journal_entries (entry_date);
CREATE INDEX IF NOT EXISTS idx_journal_lines_entry ON journal_lines (journal_entry_id);
CREATE INDEX IF NOT EXISTS idx_journal_lines_account ON journal_lines (account_id);
CREATE INDEX IF NOT EXISTS idx_receivables_customer ON receivables (customer_id, status);
CREATE INDEX IF NOT EXISTS idx_payables_supplier ON payables (supplier_id, status);
CREATE INDEX IF NOT EXISTS idx_supplier_payments_payable ON supplier_payments (payable_id, status);
CREATE INDEX IF NOT EXISTS idx_obligations_instrument
    ON commercial_obligations (instrument_type, status);
CREATE INDEX IF NOT EXISTS idx_obligations_customer ON commercial_obligations (customer_id);
CREATE INDEX IF NOT EXISTS idx_financial_documents_source
    ON financial_documents (source_module, source_document_id);
CREATE INDEX IF NOT EXISTS idx_finance_outbox_status ON finance_outbox (status);
"""


def create_finance_schema(conn) -> None:
    """Create the complete finance schema. Idempotent (IF NOT EXISTS)."""
    conn.executescript(_DDL)


def drop_legacy_finance_tables(conn) -> list[str]:
    """Drop every legacy finance table. Development-phase rule: no data rescue,
    no dual routes — a clean database is regenerated from the canonical schema."""
    dropped: list[str] = []
    for table in LEGACY_FINANCE_TABLES:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if row is not None:
            conn.execute(f"DROP TABLE IF EXISTS {table}")
            dropped.append(table)
    return dropped
