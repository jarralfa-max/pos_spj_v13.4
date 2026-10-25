"""Finance bounded context — born-clean UUIDv7 schema (single source of truth).

Rules:
- Every id is ``TEXT NOT NULL PRIMARY KEY`` holding a lowercase UUIDv7 (PostgreSQL: UUID).
- Every monetary column is ``TEXT`` holding a canonical decimal string
  (PostgreSQL: NUMERIC); floats/REAL are forbidden for money.
- Idempotency is structural: UNIQUE(operation_id) and
  UNIQUE(source_module, source_document_id, posting_purpose).
- Sin autoincrementos ni identidades de cursor; sin compatibilidad legacy ni rescate de datos.

Ronda 2 FIN-ERP (2026-10-21): ésta es la ÚNICA definición. No hay capa de
"upgrade" que convierta tablas anteriores. La migración 345 aplica el contrato:
crea las tablas ausentes y vuelve a crear las de un contrato anterior que estén
VACÍAS; si alguna tiene datos se detiene sin tocar nada (convertir es una
decisión explícita). Nunca se pide borrar la base (auditoría enterprise N05).

The only entry point that may execute this DDL is a migration in ``migrations/``.
"""

from __future__ import annotations

import sqlite3


_DDL = """
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT NOT NULL PRIMARY KEY,
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

CREATE TABLE IF NOT EXISTS currencies (
    id TEXT NOT NULL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    decimal_places INTEGER NOT NULL DEFAULT 2,
    rounding_mode TEXT NOT NULL DEFAULT 'ROUND_HALF_UP',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS exchange_rates (
    id TEXT NOT NULL PRIMARY KEY,
    from_currency TEXT NOT NULL,
    to_currency TEXT NOT NULL,
    rate TEXT NOT NULL,
    effective_date TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT '',
    created_by TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (from_currency, to_currency, effective_date)
);

CREATE TABLE IF NOT EXISTS fiscal_periods (
    id TEXT NOT NULL PRIMARY KEY,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','SOFT_CLOSED','CLOSED')),
    opened_at TEXT NOT NULL,
    soft_closed_at TEXT,
    soft_closed_by TEXT,
    closed_at TEXT,
    closed_by TEXT,
    reopened_at TEXT,
    reopened_by TEXT,
    reopen_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (year, month)
);

CREATE TABLE IF NOT EXISTS journals (
    id TEXT NOT NULL PRIMARY KEY,
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
    id TEXT NOT NULL PRIMARY KEY,
    journal_id TEXT NOT NULL REFERENCES journals(id),
    entry_number TEXT NOT NULL UNIQUE,
    entry_date TEXT NOT NULL,
    posting_date TEXT NOT NULL,
    fiscal_period_id TEXT NOT NULL REFERENCES fiscal_periods(id),
    description TEXT NOT NULL DEFAULT '',
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    base_currency_code TEXT NOT NULL DEFAULT 'MXN',
    status TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN (
        'DRAFT','VALIDATED','POSTED','REVERSED','CANCELLED')),
    source_module TEXT NOT NULL,
    source_document_type TEXT,
    source_document_id TEXT NOT NULL,
    posting_purpose TEXT NOT NULL,
    operation_id TEXT NOT NULL UNIQUE,
    branch_id TEXT,
    reversal_of_entry_id TEXT REFERENCES journal_entries(id),
    reversed_by_entry_id TEXT REFERENCES journal_entries(id),
    created_by TEXT,
    validated_by TEXT,
    validated_at TEXT,
    posted_by TEXT,
    posted_at TEXT,
    cancelled_by TEXT,
    cancel_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (source_module, source_document_id, posting_purpose)
);

CREATE TABLE IF NOT EXISTS journal_lines (
    id TEXT NOT NULL PRIMARY KEY,
    journal_entry_id TEXT NOT NULL REFERENCES journal_entries(id) ON DELETE CASCADE,
    account_id TEXT NOT NULL REFERENCES accounts(id),
    description TEXT NOT NULL DEFAULT '',
    debit_amount TEXT NOT NULL DEFAULT '0.00',
    credit_amount TEXT NOT NULL DEFAULT '0.00',
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    exchange_rate TEXT NOT NULL DEFAULT '1',
    base_debit_amount TEXT NOT NULL DEFAULT '0.00',
    base_credit_amount TEXT NOT NULL DEFAULT '0.00',
    line_role TEXT NOT NULL DEFAULT 'NORMAL' CHECK (line_role IN ('NORMAL','ROUNDING')),
    branch_id TEXT,
    cost_center_id TEXT,
    profit_center_id TEXT,
    project_id TEXT,
    department_id TEXT,
    customer_id TEXT,
    supplier_id TEXT,
    employee_id TEXT,
    product_id TEXT,
    source_reference TEXT NOT NULL DEFAULT '',
    line_index INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS financial_documents (
    id TEXT NOT NULL PRIMARY KEY,
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
    row_version INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (source_module, source_document_id, document_type)
);

CREATE TABLE IF NOT EXISTS receivables (
    id TEXT NOT NULL PRIMARY KEY,
    customer_id TEXT NOT NULL,
    financial_document_id TEXT NOT NULL REFERENCES financial_documents(id),
    original_amount TEXT NOT NULL,
    outstanding_amount TEXT NOT NULL,
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    issue_date TEXT NOT NULL,
    due_date TEXT,
    credit_term_days INTEGER,
    credit_origin TEXT NOT NULL DEFAULT 'SALE',
    branch_id TEXT,
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN (
        'OPEN','PARTIALLY_COLLECTED','COLLECTED','OVERDUE','DISPUTED','CANCELLED',
        'WRITTEN_OFF')),
    dispute_reason TEXT,
    disputed_at TEXT,
    disputed_by TEXT,
    written_off_at TEXT,
    written_off_by TEXT,
    write_off_reason TEXT,
    operation_id TEXT NOT NULL UNIQUE,
    row_version INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (financial_document_id)
);

CREATE TABLE IF NOT EXISTS receivable_charges (
    id TEXT NOT NULL PRIMARY KEY,
    receivable_id TEXT NOT NULL REFERENCES receivables(id),
    amount TEXT NOT NULL,
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    source_module TEXT NOT NULL,
    source_reference TEXT NOT NULL,
    operation_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS receivable_payment_promises (
    id TEXT NOT NULL PRIMARY KEY,
    receivable_id TEXT NOT NULL REFERENCES receivables(id),
    promised_date TEXT NOT NULL,
    promised_amount TEXT NOT NULL,
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    note TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','KEPT','BROKEN','CANCELLED')),
    created_by TEXT,
    operation_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS collections (
    id TEXT NOT NULL PRIMARY KEY,
    customer_id TEXT NOT NULL,
    branch_id TEXT,
    treasury_account_id TEXT NOT NULL REFERENCES treasury_accounts(id),
    payment_method TEXT NOT NULL DEFAULT 'BANK_TRANSFER',
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    amount TEXT NOT NULL,
    applied_amount TEXT NOT NULL DEFAULT '0.00',
    collection_date TEXT NOT NULL,
    reference TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'UNAPPLIED' CHECK (status IN (
        'UNAPPLIED','PARTIALLY_APPLIED','APPLIED','REVERSED')),
    journal_entry_id TEXT REFERENCES journal_entries(id),
    created_by TEXT,
    operation_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS collection_applications (
    id TEXT NOT NULL PRIMARY KEY,
    collection_id TEXT NOT NULL REFERENCES collections(id),
    receivable_id TEXT NOT NULL REFERENCES receivables(id),
    applied_amount TEXT NOT NULL,
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    journal_entry_id TEXT REFERENCES journal_entries(id),
    created_by TEXT,
    operation_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS payables (
    id TEXT NOT NULL PRIMARY KEY,
    supplier_id TEXT NOT NULL,
    financial_document_id TEXT NOT NULL REFERENCES financial_documents(id),
    original_amount TEXT NOT NULL,
    outstanding_amount TEXT NOT NULL,
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    issue_date TEXT NOT NULL,
    due_date TEXT,
    branch_id TEXT,
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN (
        'OPEN','PARTIALLY_PAID','SCHEDULED','AUTHORIZED','PAID','OVERDUE','DISPUTED',
        'CANCELLED')),
    priority TEXT NOT NULL DEFAULT 'NORMAL' CHECK (priority IN ('LOW','NORMAL','HIGH','CRITICAL')),
    payment_terms TEXT NOT NULL DEFAULT '',
    debit_nature TEXT NOT NULL DEFAULT 'INVENTORY' CHECK (debit_nature IN (
        'INVENTORY','OPERATING_EXPENSE','PREPAID_EXPENSE','FIXED_ASSET','OTHER_ASSET')),
    purchase_order_id TEXT,
    goods_receipt_id TEXT,
    blocked INTEGER NOT NULL DEFAULT 0,
    block_reason TEXT,
    unblocked_by TEXT,
    unblock_reason TEXT,
    dispute_reason TEXT,
    retention_amount TEXT NOT NULL DEFAULT '0.00',
    early_payment_discount_percent TEXT,
    early_payment_discount_until TEXT,
    operation_id TEXT NOT NULL UNIQUE,
    row_version INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (financial_document_id)
);

CREATE TABLE IF NOT EXISTS supplier_payments (
    id TEXT NOT NULL PRIMARY KEY,
    payable_id TEXT NOT NULL REFERENCES payables(id),
    supplier_id TEXT NOT NULL,
    amount TEXT NOT NULL,
    discount_amount TEXT NOT NULL DEFAULT '0.00',
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    scheduled_date TEXT NOT NULL,
    treasury_account_id TEXT NOT NULL REFERENCES treasury_accounts(id),
    status TEXT NOT NULL DEFAULT 'SCHEDULED' CHECK (status IN (
        'SCHEDULED','AUTHORIZED','EXECUTED','RECONCILED','CANCELLED')),
    scheduled_by TEXT,
    authorized_by TEXT,
    authorized_at TEXT,
    second_authorization_required INTEGER NOT NULL DEFAULT 0,
    second_authorized_by TEXT,
    second_authorized_at TEXT,
    executed_by TEXT,
    executed_at TEXT,
    executed_date TEXT,
    execution_reference TEXT,
    journal_entry_id TEXT REFERENCES journal_entries(id),
    reconciled_at TEXT,
    reference TEXT NOT NULL DEFAULT '',
    branch_id TEXT,
    operation_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS supplier_advances (
    id TEXT NOT NULL PRIMARY KEY,
    supplier_id TEXT NOT NULL,
    branch_id TEXT,
    treasury_account_id TEXT NOT NULL REFERENCES treasury_accounts(id),
    amount TEXT NOT NULL,
    applied_amount TEXT NOT NULL DEFAULT '0.00',
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    advance_date TEXT NOT NULL,
    reference TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN (
        'OPEN','PARTIALLY_APPLIED','APPLIED','CANCELLED')),
    journal_entry_id TEXT REFERENCES journal_entries(id),
    created_by TEXT,
    operation_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS supplier_advance_applications (
    id TEXT NOT NULL PRIMARY KEY,
    supplier_advance_id TEXT NOT NULL REFERENCES supplier_advances(id),
    payable_id TEXT NOT NULL REFERENCES payables(id),
    applied_amount TEXT NOT NULL,
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    journal_entry_id TEXT REFERENCES journal_entries(id),
    created_by TEXT,
    operation_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS treasury_accounts (
    id TEXT NOT NULL PRIMARY KEY,
    name TEXT NOT NULL,
    account_type TEXT NOT NULL CHECK (account_type IN (
        'BANK','CASH_REGISTER','PETTY_CASH','GENERAL_CASH',
        'PAYMENT_PROCESSOR','DIGITAL_WALLET','CLEARING_ACCOUNT')),
    ledger_account_id TEXT NOT NULL REFERENCES accounts(id),
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    branch_id TEXT,
    bank_name TEXT,
    masked_account_number TEXT NOT NULL DEFAULT '',
    requires_reconciliation INTEGER NOT NULL DEFAULT 0,
    restricted INTEGER NOT NULL DEFAULT 0,
    allows_overdraft INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS treasury_movements (
    id TEXT NOT NULL PRIMARY KEY,
    treasury_account_id TEXT NOT NULL REFERENCES treasury_accounts(id),
    kind TEXT NOT NULL CHECK (kind IN ('DEPOSIT','WITHDRAWAL','BANK_CHARGE','BANK_INTEREST')),
    amount TEXT NOT NULL,
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    movement_date TEXT NOT NULL,
    counterpart_account_id TEXT NOT NULL REFERENCES accounts(id),
    reference TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    financial_document_id TEXT REFERENCES financial_documents(id),
    journal_entry_id TEXT REFERENCES journal_entries(id),
    bank_statement_line_id TEXT,
    created_by TEXT,
    branch_id TEXT,
    operation_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bank_statements (
    id TEXT NOT NULL PRIMARY KEY,
    treasury_account_id TEXT NOT NULL REFERENCES treasury_accounts(id),
    statement_date TEXT NOT NULL,
    opening_balance TEXT NOT NULL,
    closing_balance TEXT NOT NULL,
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    source_format TEXT NOT NULL DEFAULT 'MANUAL' CHECK (source_format IN (
        'MANUAL','CSV','XLSX','API')),
    file_name TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL,
    imported_by TEXT,
    operation_id TEXT NOT NULL UNIQUE,
    imported_at TEXT NOT NULL,
    UNIQUE (treasury_account_id, content_hash)
);

CREATE TABLE IF NOT EXISTS bank_statement_lines (
    id TEXT NOT NULL PRIMARY KEY,
    bank_statement_id TEXT NOT NULL REFERENCES bank_statements(id) ON DELETE CASCADE,
    transaction_date TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    amount TEXT NOT NULL,
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    external_reference TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'UNMATCHED' CHECK (status IN (
        'UNMATCHED','SUGGESTED','MATCHED','IGNORED','ADJUSTMENT_REQUIRED')),
    matched_journal_line_id TEXT REFERENCES journal_lines(id),
    suggested_journal_line_id TEXT REFERENCES journal_lines(id),
    suggestion_score INTEGER,
    ignored_reason TEXT,
    ignored_by TEXT,
    adjustment_journal_entry_id TEXT REFERENCES journal_entries(id),
    line_index INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS reconciliations (
    id TEXT NOT NULL PRIMARY KEY,
    treasury_account_id TEXT NOT NULL REFERENCES treasury_accounts(id),
    bank_statement_id TEXT NOT NULL REFERENCES bank_statements(id),
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN (
        'OPEN','IN_PROGRESS','COMPLETED','REVERTED')),
    completed_by TEXT,
    completed_at TEXT,
    difference_reason TEXT,
    reverted_by TEXT,
    revert_reason TEXT,
    operation_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reconciliation_matches (
    id TEXT NOT NULL PRIMARY KEY,
    reconciliation_id TEXT NOT NULL REFERENCES reconciliations(id) ON DELETE CASCADE,
    bank_statement_line_id TEXT NOT NULL REFERENCES bank_statement_lines(id),
    journal_line_id TEXT NOT NULL REFERENCES journal_lines(id),
    matched_by TEXT NOT NULL,
    matched_at TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    reverted_at TEXT,
    reverted_by TEXT,
    revert_reason TEXT
);

CREATE TABLE IF NOT EXISTS cost_centers (
    id TEXT NOT NULL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    parent_id TEXT REFERENCES cost_centers(id),
    branch_id TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS profit_centers (
    id TEXT NOT NULL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    branch_id TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT NOT NULL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    branch_id TEXT,
    is_capex INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS departments (
    id TEXT NOT NULL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS budgets (
    id TEXT NOT NULL PRIMARY KEY,
    name TEXT NOT NULL,
    fiscal_year INTEGER NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    previous_version_id TEXT REFERENCES budgets(id),
    status TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN (
        'DRAFT','SUBMITTED','APPROVED','ACTIVE','CLOSED','CANCELLED')),
    blocking INTEGER NOT NULL DEFAULT 1,
    submitted_by TEXT,
    approved_by TEXT,
    approved_at TEXT,
    rejection_reason TEXT,
    cancel_reason TEXT,
    branch_id TEXT,
    operation_id TEXT NOT NULL UNIQUE,
    row_version INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (name, fiscal_year, version)
);

CREATE TABLE IF NOT EXISTS budget_lines (
    id TEXT NOT NULL PRIMARY KEY,
    budget_id TEXT NOT NULL REFERENCES budgets(id) ON DELETE CASCADE,
    account_id TEXT NOT NULL REFERENCES accounts(id),
    period_code TEXT NOT NULL,
    planned_amount TEXT NOT NULL,
    committed_amount TEXT NOT NULL DEFAULT '0.00',
    accrued_amount TEXT NOT NULL DEFAULT '0.00',
    paid_amount TEXT NOT NULL DEFAULT '0.00',
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    cost_center_id TEXT REFERENCES cost_centers(id),
    profit_center_id TEXT REFERENCES profit_centers(id),
    project_id TEXT REFERENCES projects(id),
    department_id TEXT REFERENCES departments(id),
    branch_id TEXT
);

CREATE TABLE IF NOT EXISTS expense_approval_rules (
    id TEXT NOT NULL PRIMARY KEY,
    name TEXT NOT NULL,
    min_amount TEXT NOT NULL DEFAULT '0.00',
    branch_id TEXT,
    category TEXT,
    cost_center_id TEXT,
    requester_id TEXT,
    required_approvals INTEGER NOT NULL CHECK (required_approvals BETWEEN 1 AND 3),
    priority INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS expense_requests (
    id TEXT NOT NULL PRIMARY KEY,
    budget_id TEXT REFERENCES budgets(id),
    account_id TEXT NOT NULL REFERENCES accounts(id),
    period_code TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    cost_center_id TEXT,
    project_id TEXT,
    department_id TEXT,
    branch_id TEXT,
    supplier_id TEXT,
    amount TEXT NOT NULL,
    accrued_amount TEXT NOT NULL DEFAULT '0.00',
    settled_amount TEXT NOT NULL DEFAULT '0.00',
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    status TEXT NOT NULL DEFAULT 'REQUESTED' CHECK (status IN (
        'REQUESTED','APPROVED','REJECTED','ACCRUED','SETTLED','CANCELLED')),
    required_approvals INTEGER NOT NULL DEFAULT 1,
    excess_authorized INTEGER NOT NULL DEFAULT 0,
    requested_by TEXT NOT NULL,
    resolution_reason TEXT,
    payable_id TEXT REFERENCES payables(id),
    accrual_journal_entry_id TEXT REFERENCES journal_entries(id),
    document_reference TEXT,
    operation_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS expense_approvals (
    id TEXT NOT NULL PRIMARY KEY,
    expense_request_id TEXT NOT NULL REFERENCES expense_requests(id),
    approver_id TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('APPROVED','REJECTED')),
    reason TEXT NOT NULL DEFAULT '',
    decided_at TEXT NOT NULL,
    UNIQUE (expense_request_id, approver_id)
);

CREATE TABLE IF NOT EXISTS fixed_asset_categories (
    id TEXT NOT NULL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    asset_account_id TEXT NOT NULL REFERENCES accounts(id),
    depreciation_expense_account_id TEXT NOT NULL REFERENCES accounts(id),
    accumulated_depreciation_account_id TEXT NOT NULL REFERENCES accounts(id),
    default_useful_life_months INTEGER,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fixed_assets (
    id TEXT NOT NULL PRIMARY KEY,
    asset_code TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL,
    asset_category_id TEXT REFERENCES fixed_asset_categories(id),
    acquisition_date TEXT,
    acquisition_cost TEXT NOT NULL,
    residual_value TEXT NOT NULL DEFAULT '0.00',
    accumulated_depreciation TEXT NOT NULL DEFAULT '0.00',
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    useful_life_months INTEGER NOT NULL,
    depreciation_method TEXT NOT NULL DEFAULT 'STRAIGHT_LINE',
    status TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN (
        'DRAFT','ACTIVE','SUSPENDED','DISPOSED','SOLD','WRITTEN_OFF')),
    status_reason TEXT,
    capitalization_date TEXT,
    asset_account_id TEXT REFERENCES accounts(id),
    depreciation_expense_account_id TEXT REFERENCES accounts(id),
    accumulated_depreciation_account_id TEXT REFERENCES accounts(id),
    last_depreciated_period TEXT,
    disposal_date TEXT,
    disposal_journal_entry_id TEXT REFERENCES journal_entries(id),
    supplier_id TEXT,
    source_document_id TEXT,
    project_id TEXT REFERENCES projects(id),
    branch_id TEXT,
    cost_center_id TEXT REFERENCES cost_centers(id),
    operation_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS depreciation_runs (
    id TEXT NOT NULL PRIMARY KEY,
    period_code TEXT NOT NULL,
    asset_count INTEGER NOT NULL DEFAULT 0,
    total_amount TEXT NOT NULL DEFAULT '0.00',
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    run_by TEXT,
    operation_id TEXT NOT NULL UNIQUE,
    run_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS depreciation_run_lines (
    id TEXT NOT NULL PRIMARY KEY,
    depreciation_run_id TEXT NOT NULL REFERENCES depreciation_runs(id),
    fixed_asset_id TEXT NOT NULL REFERENCES fixed_assets(id),
    period_code TEXT NOT NULL,
    amount TEXT NOT NULL,
    journal_entry_id TEXT NOT NULL REFERENCES journal_entries(id),
    UNIQUE (fixed_asset_id, period_code)
);

CREATE TABLE IF NOT EXISTS loans (
    id TEXT NOT NULL PRIMARY KEY,
    lender_name TEXT NOT NULL,
    principal_amount TEXT NOT NULL,
    outstanding_principal TEXT NOT NULL,
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    start_date TEXT NOT NULL,
    maturity_date TEXT,
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','PAID','CANCELLED')),
    liability_account_id TEXT NOT NULL REFERENCES accounts(id),
    created_by TEXT,
    operation_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS capital_transactions (
    id TEXT NOT NULL PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN (
        'CONTRIBUTION','WITHDRAWAL','LOAN_RECEIVED','LOAN_REPAYMENT')),
    amount TEXT NOT NULL,
    interest_amount TEXT NOT NULL DEFAULT '0.00',
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    transaction_date TEXT NOT NULL,
    treasury_account_id TEXT NOT NULL REFERENCES treasury_accounts(id),
    counterparty TEXT NOT NULL DEFAULT '',
    loan_id TEXT REFERENCES loans(id),
    financial_document_id TEXT REFERENCES financial_documents(id),
    journal_entry_id TEXT REFERENCES journal_entries(id),
    created_by TEXT,
    branch_id TEXT,
    operation_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS posting_profiles (
    id TEXT NOT NULL PRIMARY KEY,
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

CREATE TABLE IF NOT EXISTS commercial_obligations (
    id TEXT NOT NULL PRIMARY KEY,
    instrument_type TEXT NOT NULL CHECK (instrument_type IN (
        'LOYALTY_POINTS','PROMOTIONAL_COUPON','DISCOUNT_COUPON','REFUND_VOUCHER',
        'STORE_CREDIT','GIFT_CARD','PREPAID_VOUCHER','PROMOTIONAL_BALANCE',
        'CUSTOMER_WALLET','THIRD_PARTY_VOUCHER','SWEEPSTAKES_PRIZE')),
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

CREATE TABLE IF NOT EXISTS tax_codes (
    id TEXT NOT NULL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('VAT','WITHHOLDING_VAT','WITHHOLDING_INCOME','EXCISE')),
    direction TEXT NOT NULL CHECK (direction IN ('SALES','PURCHASES')),
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tax_rates (
    id TEXT NOT NULL PRIMARY KEY,
    tax_code_id TEXT NOT NULL REFERENCES tax_codes(id),
    rate_percent TEXT NOT NULL,
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (tax_code_id, effective_from)
);

CREATE TABLE IF NOT EXISTS tax_rules (
    id TEXT NOT NULL PRIMARY KEY,
    tax_code_id TEXT NOT NULL REFERENCES tax_codes(id),
    scope TEXT NOT NULL CHECK (scope IN ('PRODUCT','CATEGORY','CHANNEL','DEFAULT')),
    scope_id TEXT,
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tax_posting_profiles (
    id TEXT NOT NULL PRIMARY KEY,
    tax_code_id TEXT NOT NULL REFERENCES tax_codes(id),
    account_id TEXT NOT NULL REFERENCES accounts(id),
    effective_from TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (tax_code_id, effective_from)
);

CREATE TABLE IF NOT EXISTS profitability_facts (
    id TEXT NOT NULL PRIMARY KEY,
    fact_type TEXT NOT NULL CHECK (fact_type IN (
        'SALE','RETURN','WASTE','DELIVERY_COST','PAYMENT_FEE','LOYALTY_COST','COMMISSION')),
    source_module TEXT NOT NULL,
    source_document_id TEXT NOT NULL,
    line_reference TEXT NOT NULL,
    journal_entry_id TEXT REFERENCES journal_entries(id),
    fact_date TEXT NOT NULL,
    branch_id TEXT,
    product_id TEXT,
    category_id TEXT,
    customer_id TEXT,
    channel TEXT,
    order_id TEXT,
    route_id TEXT,
    quantity TEXT NOT NULL DEFAULT '0',
    net_revenue TEXT NOT NULL DEFAULT '0.00',
    discount TEXT NOT NULL DEFAULT '0.00',
    cost_of_sales TEXT NOT NULL DEFAULT '0.00',
    direct_cost TEXT NOT NULL DEFAULT '0.00',
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    operation_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (fact_type, source_module, source_document_id, line_reference)
);

CREATE TABLE IF NOT EXISTS recurring_expense_plans (
    id TEXT NOT NULL PRIMARY KEY,
    name TEXT NOT NULL,
    account_id TEXT NOT NULL REFERENCES accounts(id),
    amount TEXT NOT NULL,
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    frequency TEXT NOT NULL CHECK (frequency IN ('WEEKLY','BIWEEKLY','MONTHLY','QUARTERLY','YEARLY')),
    next_date TEXT NOT NULL,
    branch_id TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS finance_settings (
    setting_key TEXT NOT NULL PRIMARY KEY,
    setting_value TEXT NOT NULL DEFAULT '',
    updated_by TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS finance_audit_log (
    id TEXT NOT NULL PRIMARY KEY,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    user_id TEXT,
    before_json TEXT NOT NULL DEFAULT '{}',
    after_json TEXT NOT NULL DEFAULT '{}',
    reason TEXT NOT NULL DEFAULT '',
    branch_id TEXT,
    occurred_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS finance_processed_events (
    event_id TEXT NOT NULL PRIMARY KEY,
    event_name TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    processed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS finance_outbox (
    id TEXT NOT NULL PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    event_name TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','DISPATCHED')),
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL,
    dispatched_at TEXT
);

CREATE TABLE IF NOT EXISTS finance_close_exceptions (
    id TEXT NOT NULL PRIMARY KEY,
    period_code TEXT NOT NULL,
    check_type TEXT NOT NULL,
    subject TEXT NOT NULL,
    expected_amount TEXT NOT NULL,
    actual_amount TEXT NOT NULL,
    difference TEXT NOT NULL,
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','RESOLVED','AUTHORIZED')),
    detected_at TEXT NOT NULL,
    resolved_by TEXT,
    resolved_at TEXT,
    resolution_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_posting_profiles_key ON posting_profiles (profile_key, effective_from);
CREATE INDEX IF NOT EXISTS idx_journal_entries_period ON journal_entries (fiscal_period_id, status);
CREATE INDEX IF NOT EXISTS idx_journal_entries_date ON journal_entries (posting_date);
CREATE INDEX IF NOT EXISTS idx_journal_entries_source ON journal_entries (source_module, source_document_id);
CREATE INDEX IF NOT EXISTS idx_journal_lines_entry ON journal_lines (journal_entry_id);
CREATE INDEX IF NOT EXISTS idx_journal_lines_account ON journal_lines (account_id);
CREATE INDEX IF NOT EXISTS idx_journal_lines_branch ON journal_lines (branch_id);
CREATE INDEX IF NOT EXISTS idx_receivables_customer ON receivables (customer_id, status);
CREATE INDEX IF NOT EXISTS idx_receivable_charges_receivable ON receivable_charges (receivable_id);
CREATE INDEX IF NOT EXISTS idx_collections_customer ON collections (customer_id, status);
CREATE INDEX IF NOT EXISTS idx_collection_applications_collection ON collection_applications (collection_id);
CREATE INDEX IF NOT EXISTS idx_collection_applications_receivable ON collection_applications (receivable_id);
CREATE INDEX IF NOT EXISTS idx_payables_supplier ON payables (supplier_id, status);
CREATE INDEX IF NOT EXISTS idx_supplier_payments_payable ON supplier_payments (payable_id, status);
CREATE INDEX IF NOT EXISTS idx_supplier_advances_supplier ON supplier_advances (supplier_id, status);
CREATE INDEX IF NOT EXISTS idx_treasury_movements_account ON treasury_movements (treasury_account_id, movement_date);
CREATE INDEX IF NOT EXISTS idx_statement_lines_statement ON bank_statement_lines (bank_statement_id, status);
CREATE INDEX IF NOT EXISTS idx_obligations_instrument ON commercial_obligations (instrument_type, status);
CREATE INDEX IF NOT EXISTS idx_obligations_customer ON commercial_obligations (customer_id);
CREATE INDEX IF NOT EXISTS idx_financial_documents_source ON financial_documents (source_module, source_document_id);
CREATE INDEX IF NOT EXISTS idx_finance_outbox_status ON finance_outbox (status);
CREATE INDEX IF NOT EXISTS idx_finance_close_exceptions_period ON finance_close_exceptions (period_code, status);
CREATE INDEX IF NOT EXISTS idx_expense_requests_status ON expense_requests (status);
CREATE INDEX IF NOT EXISTS idx_exchange_rates_lookup ON exchange_rates (from_currency, to_currency, effective_date);
CREATE INDEX IF NOT EXISTS idx_finance_audit_entity ON finance_audit_log (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_finance_audit_occurred ON finance_audit_log (occurred_at);
CREATE INDEX IF NOT EXISTS idx_profitability_facts_date ON profitability_facts (fact_date, branch_id);
CREATE INDEX IF NOT EXISTS idx_profitability_facts_product ON profitability_facts (product_id);
CREATE INDEX IF NOT EXISTS idx_depreciation_runs_period ON depreciation_runs (period_code);
CREATE UNIQUE INDEX IF NOT EXISTS ux_fixed_assets_code ON fixed_assets (asset_code) WHERE asset_code <> '';
CREATE UNIQUE INDEX IF NOT EXISTS ux_reconciliation_matches_active_journal_line
    ON reconciliation_matches (journal_line_id) WHERE active = 1;
CREATE UNIQUE INDEX IF NOT EXISTS ux_reconciliation_matches_active_statement_line
    ON reconciliation_matches (bank_statement_line_id) WHERE active = 1;
"""

#: Legacy finance tables of earlier generations (m000/035/052/059/061/066/082-084).
#: Migration 117 drops them BEFORE creating this schema; names colliding with
#: the canonical schema (journal_entries, financial_documents, fixed_assets,
#: treasury_movements de la 083) are dropped so they are recreated clean.
LEGACY_FINANCE_TABLES: tuple[str, ...] = (
    "journal_entries",
    "journal_lines",
    "financial_documents",
    "fixed_assets",
    "treasury_movements",
    "maintenance_records",
    "operating_supplies",
    "plan_cuentas",
    "terceros",
    "cuentas_financieras",
    "catalogo_cuentas_contables",
    "documentos_financieros",
    "movimientos_financieros",
    "ledger_financiero",
    "conciliaciones_financieras",
    "cortes_caja_erp",
    "financial_documents_legacy",
    "asset_depreciation_entries",
    "financial_trace_log",
    "reconciliation_records",
    "capital_movements",
    "loyalty_budget_caps",
)


def _expected_contract() -> dict[str, set[str]]:
    probe = sqlite3.connect(":memory:")
    try:
        probe.executescript(_DDL)
        tables = [r[0] for r in probe.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
        return {table: {str(r[1]) for r in probe.execute(f"PRAGMA table_info({table})")}
                for table in tables}
    finally:
        probe.close()


#: Tablas del contrato financiero (derivadas del DDL, no de una lista paralela).
FINANCE_TABLES: tuple[str, ...] = tuple(sorted(_expected_contract()))


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


def finance_schema_differences(conn) -> dict[str, list[str]]:
    """Columnas del contrato que faltan en la base, por tabla (``"*"`` = tabla ausente)."""
    differences: dict[str, list[str]] = {}
    for table, expected in _expected_contract().items():
        actual = {str(r[1]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if not actual:
            differences[table] = ["*"]
            continue
        missing = sorted(expected - actual)
        if missing:
            differences[table] = missing
    return differences
