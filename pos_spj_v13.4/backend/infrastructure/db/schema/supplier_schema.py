"""Suppliers bounded context — born-clean UUIDv7 schema (single source of truth).

Rules:
- Every id is ``TEXT PRIMARY KEY`` holding a lowercase UUIDv7 (PostgreSQL: UUID).
- Money columns are ``TEXT`` decimal strings (PostgreSQL: NUMERIC); no REAL.
- Idempotency is structural: UNIQUE(operation_id) where an operation must not
  repeat; UNIQUE(supplier_code); UNIQUE(source event_id) in processed events.
- Sin autoincrementos ni identidades de cursor; sin compatibilidad legacy.

The canonical master table is ``supplier_master`` (the legacy minimal tables
``proveedores``/``suppliers`` still have live purchase/finance readers and are
migrated to this master in SUP-6 — they are intentionally NOT dropped here).

Only a migration in ``migrations/`` may execute this DDL.
"""

from __future__ import annotations

#: Creation order (parents first). Drop order is the reverse.
SUPPLIER_TABLES: tuple[str, ...] = (
    "supplier_master",
    "supplier_categories",
    "supplier_category_links",
    "supplier_contacts",
    "supplier_addresses",
    "supplier_bank_accounts",
    "supplier_commercial_terms",
    "supplier_products",
    "supplier_documents",
    "supplier_evaluations",
    "supplier_evaluation_items",
    "supplier_blocks",
    "supplier_branch_authorizations",
    "supplier_audit_log",
    "supplier_outbox",
    "supplier_processed_events",
)

_DDL = (
    """
    CREATE TABLE IF NOT EXISTS supplier_master (
        id TEXT PRIMARY KEY,
        supplier_code TEXT NOT NULL UNIQUE,
        legal_name TEXT NOT NULL,
        trade_name TEXT NOT NULL DEFAULT '',
        normalized_name TEXT NOT NULL DEFAULT '',
        tax_identifier TEXT,
        person_type TEXT,
        tax_regime TEXT,
        country_code TEXT NOT NULL DEFAULT 'MX',
        preferred_currency TEXT NOT NULL DEFAULT 'MXN',
        language TEXT NOT NULL DEFAULT 'es-MX',
        website TEXT,
        notes TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN (
            'DRAFT','PENDING_APPROVAL','ACTIVE','SUSPENDED','BLOCKED',
            'INACTIVE','REJECTED')),
        risk_level TEXT CHECK (risk_level IN ('LOW','MEDIUM','HIGH','CRITICAL')),
        rating_grade TEXT CHECK (rating_grade IN ('A','B','C','D')),
        rating_score INTEGER,
        created_by_user_id TEXT,
        approved_by_user_id TEXT,
        has_history INTEGER NOT NULL DEFAULT 0,
        active INTEGER NOT NULL DEFAULT 1,
        operation_id TEXT UNIQUE,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS supplier_categories (
        code TEXT PRIMARY KEY,
        kind TEXT NOT NULL CHECK (kind IN ('CLASSIFICATION','COMMERCIAL')),
        name TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS supplier_category_links (
        id TEXT PRIMARY KEY,
        supplier_id TEXT NOT NULL REFERENCES supplier_master(id),
        category_type TEXT NOT NULL CHECK (category_type IN ('CLASSIFICATION','COMMERCIAL')),
        category_code TEXT NOT NULL,
        UNIQUE (supplier_id, category_type, category_code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS supplier_contacts (
        id TEXT PRIMARY KEY,
        supplier_id TEXT NOT NULL REFERENCES supplier_master(id),
        name TEXT NOT NULL,
        contact_type TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT '',
        phone_e164 TEXT,
        email TEXT,
        is_primary INTEGER NOT NULL DEFAULT 0,
        receives_purchase_orders INTEGER NOT NULL DEFAULT 0,
        receives_payment_receipts INTEGER NOT NULL DEFAULT 0,
        receives_notifications INTEGER NOT NULL DEFAULT 0,
        active INTEGER NOT NULL DEFAULT 1
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS supplier_addresses (
        id TEXT PRIMARY KEY,
        supplier_id TEXT NOT NULL REFERENCES supplier_master(id),
        address_type TEXT NOT NULL,
        line TEXT NOT NULL,
        city TEXT NOT NULL DEFAULT '',
        state TEXT NOT NULL DEFAULT '',
        postal_code TEXT NOT NULL DEFAULT '',
        country_code TEXT NOT NULL DEFAULT 'MX',
        latitude REAL,
        longitude REAL,
        geocoding_source TEXT,
        validation_state TEXT NOT NULL DEFAULT 'MANUAL'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS supplier_bank_accounts (
        id TEXT PRIMARY KEY,
        supplier_id TEXT NOT NULL REFERENCES supplier_master(id),
        bank_name TEXT NOT NULL,
        account_holder TEXT NOT NULL,
        currency_code TEXT NOT NULL DEFAULT 'MXN',
        account_type TEXT NOT NULL DEFAULT 'CHECKING',
        account_number TEXT NOT NULL DEFAULT '',
        clabe TEXT NOT NULL DEFAULT '',
        swift_bic TEXT NOT NULL DEFAULT '',
        country_code TEXT NOT NULL DEFAULT 'MX',
        status TEXT NOT NULL DEFAULT 'UNVERIFIED' CHECK (status IN (
            'UNVERIFIED','PENDING_VERIFICATION','VERIFIED','REJECTED','BLOCKED')),
        document_reference TEXT,
        verified_by_user_id TEXT,
        verified_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS supplier_commercial_terms (
        id TEXT PRIMARY KEY,
        supplier_id TEXT NOT NULL REFERENCES supplier_master(id),
        currency_code TEXT NOT NULL DEFAULT 'MXN',
        price_list TEXT,
        credit_days INTEGER NOT NULL DEFAULT 0,
        credit_limit TEXT NOT NULL DEFAULT '0',
        advance_required INTEGER NOT NULL DEFAULT 0,
        advance_percentage TEXT NOT NULL DEFAULT '0',
        prompt_payment_discount TEXT NOT NULL DEFAULT '0',
        min_order_amount TEXT NOT NULL DEFAULT '0',
        quantity_tolerance TEXT NOT NULL DEFAULT '0',
        price_tolerance TEXT NOT NULL DEFAULT '0',
        lead_time_days INTEGER NOT NULL DEFAULT 0,
        delivery_days TEXT NOT NULL DEFAULT '',
        receiving_window_start TEXT,
        receiving_window_end TEXT,
        accepts_returns INTEGER NOT NULL DEFAULT 1,
        return_window_days INTEGER NOT NULL DEFAULT 0,
        UNIQUE (supplier_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS supplier_products (
        id TEXT PRIMARY KEY,
        supplier_id TEXT NOT NULL REFERENCES supplier_master(id),
        product_id TEXT NOT NULL,
        supplier_sku TEXT NOT NULL DEFAULT '',
        supplier_description TEXT NOT NULL DEFAULT '',
        purchase_unit TEXT NOT NULL DEFAULT '',
        conversion_factor TEXT NOT NULL DEFAULT '1',
        minimum_order_quantity TEXT NOT NULL DEFAULT '0',
        package_size TEXT NOT NULL DEFAULT '1',
        lead_time_days INTEGER NOT NULL DEFAULT 0,
        last_cost TEXT,
        current_cost TEXT,
        currency_code TEXT NOT NULL DEFAULT 'MXN',
        preferred INTEGER NOT NULL DEFAULT 0,
        active INTEGER NOT NULL DEFAULT 1,
        valid_from TEXT,
        valid_to TEXT,
        UNIQUE (supplier_id, product_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS supplier_documents (
        id TEXT PRIMARY KEY,
        supplier_id TEXT NOT NULL REFERENCES supplier_master(id),
        document_type TEXT NOT NULL,
        file_reference TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDING_REVIEW' CHECK (status IN (
            'VALID','EXPIRING','EXPIRED','PENDING_REVIEW','REJECTED')),
        issued_at TEXT,
        expires_at TEXT,
        verified_by_user_id TEXT,
        verified_at TEXT,
        notes TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS supplier_evaluations (
        id TEXT PRIMARY KEY,
        supplier_id TEXT NOT NULL REFERENCES supplier_master(id),
        period TEXT NOT NULL,
        score INTEGER NOT NULL DEFAULT 0,
        rating_grade TEXT CHECK (rating_grade IN ('A','B','C','D')),
        evaluated_by_user_id TEXT NOT NULL,
        comments TEXT NOT NULL DEFAULT '',
        evidence_reference TEXT,
        operation_id TEXT UNIQUE,
        created_at TEXT NOT NULL,
        UNIQUE (supplier_id, period)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS supplier_evaluation_items (
        id TEXT PRIMARY KEY,
        evaluation_id TEXT NOT NULL REFERENCES supplier_evaluations(id),
        dimension TEXT NOT NULL,
        score INTEGER NOT NULL,
        weight TEXT NOT NULL DEFAULT '1'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS supplier_blocks (
        id TEXT PRIMARY KEY,
        supplier_id TEXT NOT NULL REFERENCES supplier_master(id),
        block_type TEXT NOT NULL CHECK (block_type IN (
            'PURCHASING_BLOCK','PAYMENT_BLOCK','RECEIVING_BLOCK',
            'QUALITY_BLOCK','GENERAL_BLOCK')),
        reason TEXT NOT NULL,
        effective_at TEXT NOT NULL,
        expires_at TEXT,
        created_by_user_id TEXT NOT NULL,
        approved_by_user_id TEXT,
        operation_id TEXT UNIQUE,
        active INTEGER NOT NULL DEFAULT 1
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS supplier_branch_authorizations (
        id TEXT PRIMARY KEY,
        supplier_id TEXT NOT NULL REFERENCES supplier_master(id),
        branch_id TEXT NOT NULL,
        can_purchase INTEGER NOT NULL DEFAULT 1,
        can_receive INTEGER NOT NULL DEFAULT 1,
        can_pay INTEGER NOT NULL DEFAULT 1,
        preferred INTEGER NOT NULL DEFAULT 0,
        active INTEGER NOT NULL DEFAULT 1,
        UNIQUE (supplier_id, branch_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS supplier_audit_log (
        id TEXT PRIMARY KEY,
        supplier_id TEXT,
        action TEXT NOT NULL,
        actor_user_id TEXT,
        before_json TEXT,
        after_json TEXT,
        reason TEXT NOT NULL DEFAULT '',
        operation_id TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS supplier_outbox (
        id TEXT PRIMARY KEY,
        event_id TEXT NOT NULL,
        event_name TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        operation_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDING',
        created_at TEXT NOT NULL,
        dispatched_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS supplier_processed_events (
        event_id TEXT PRIMARY KEY,
        event_name TEXT NOT NULL,
        operation_id TEXT NOT NULL,
        processed_at TEXT NOT NULL
    )
    """,
)

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_supplier_master_tax ON supplier_master(tax_identifier)",
    "CREATE INDEX IF NOT EXISTS idx_supplier_master_code ON supplier_master(supplier_code)",
    "CREATE INDEX IF NOT EXISTS idx_supplier_master_name ON supplier_master(normalized_name)",
    "CREATE INDEX IF NOT EXISTS idx_supplier_master_status ON supplier_master(status)",
    "CREATE INDEX IF NOT EXISTS idx_supplier_master_risk ON supplier_master(risk_level)",
    "CREATE INDEX IF NOT EXISTS idx_supplier_master_rating ON supplier_master(rating_grade)",
    "CREATE INDEX IF NOT EXISTS idx_supplier_master_active ON supplier_master(active)",
    "CREATE INDEX IF NOT EXISTS idx_supplier_cat_links_sup ON supplier_category_links(supplier_id)",
    "CREATE INDEX IF NOT EXISTS idx_supplier_cat_links_code ON supplier_category_links(category_code)",
    "CREATE INDEX IF NOT EXISTS idx_supplier_contacts_sup ON supplier_contacts(supplier_id)",
    "CREATE INDEX IF NOT EXISTS idx_supplier_addresses_sup ON supplier_addresses(supplier_id)",
    "CREATE INDEX IF NOT EXISTS idx_supplier_bank_sup ON supplier_bank_accounts(supplier_id)",
    "CREATE INDEX IF NOT EXISTS idx_supplier_products_sup ON supplier_products(supplier_id)",
    "CREATE INDEX IF NOT EXISTS idx_supplier_products_prod ON supplier_products(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_supplier_documents_sup ON supplier_documents(supplier_id)",
    "CREATE INDEX IF NOT EXISTS idx_supplier_blocks_sup ON supplier_blocks(supplier_id)",
    "CREATE INDEX IF NOT EXISTS idx_supplier_branch_auth_branch ON supplier_branch_authorizations(branch_id)",
    "CREATE INDEX IF NOT EXISTS idx_supplier_audit_sup ON supplier_audit_log(supplier_id)",
    "CREATE INDEX IF NOT EXISTS idx_supplier_outbox_status ON supplier_outbox(status)",
)


def create_supplier_schema(conn) -> None:
    """Create the canonical supplier schema (idempotent). DDL lives only here."""
    for statement in _DDL:
        conn.execute(statement)
    for index in _INDEXES:
        conn.execute(index)


def drop_supplier_schema(conn) -> list[str]:
    """Drop the supplier bounded-context tables (dev reset). Reverse dependency order."""
    dropped: list[str] = []
    for table in reversed(SUPPLIER_TABLES):
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        dropped.append(table)
    return dropped
