"""Customer Master bounded context — born-clean UUIDv7 schema (single source
of truth for CRM-3).

Rules (REGLA CERO, master prompt §11):
- Every id is ``TEXT PRIMARY KEY`` holding a lowercase UUIDv7 (PostgreSQL: UUID).
- ``customer_number`` (folio) is a separate UNIQUE column, never the PK.
- No REAL columns for money/credit — this schema has none (credit lives in
  Finanzas' CxC tables per §40; CRM-8 adds ``customer_credit_profiles`` under
  a Decimal-as-TEXT convention when that phase lands, not here).
- Idempotency is structural: UNIQUE(operation_id) where an operation must
  not repeat; UNIQUE(customer_number); UNIQUE(source event_id) in processed
  events.
- Sin secuencias auto-numéricas ni identidades de cursor; sin compatibilidad legacy —
  the legacy ``clientes`` table (docs/architecture/CRM_0_CUSTOMER_MASTER_AUDIT.md
  §4) is untouched by this file and migrates its readers in CRM-21/22.

Only a migration in ``migrations/`` may execute this DDL.
"""

from __future__ import annotations

#: Creation order (parents first). Drop order is the reverse.
CUSTOMER_TABLES: tuple[str, ...] = (
    "customers",
    "customer_accounts",
    "customer_contacts",
    "customer_addresses",
    "customer_tax_profiles",
    "customer_audit_log",
    "customer_outbox",
    "customer_processed_events",
)

_DDL = (
    """
    CREATE TABLE IF NOT EXISTS customers (
        id TEXT PRIMARY KEY,
        customer_number TEXT NOT NULL UNIQUE,
        customer_type TEXT NOT NULL CHECK (customer_type IN (
            'INDIVIDUAL','BUSINESS','PUBLIC_CUSTOMER','EMPLOYEE','INTERNAL','OTHER')),
        display_name TEXT NOT NULL,
        legal_name TEXT NOT NULL DEFAULT '',
        first_name TEXT NOT NULL DEFAULT '',
        last_name TEXT NOT NULL DEFAULT '',
        second_last_name TEXT NOT NULL DEFAULT '',
        commercial_name TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN (
            'DRAFT','PROSPECT','ACTIVE','INACTIVE','SUSPENDED','BLOCKED',
            'CLOSED','MERGED','ANONYMIZED')),
        lifecycle_stage TEXT NOT NULL DEFAULT 'CUSTOMER' CHECK (lifecycle_stage IN (
            'PROSPECT','LEAD','QUALIFIED','CUSTOMER','REPEAT_CUSTOMER',
            'AT_RISK','INACTIVE','LOST')),
        source TEXT NOT NULL DEFAULT '',
        origin_branch_id TEXT,
        primary_contact_id TEXT,
        default_billing_address_id TEXT,
        default_delivery_address_id TEXT,
        account_owner_user_id TEXT,
        territory_id TEXT,
        created_by_user_id TEXT,
        operation_id TEXT UNIQUE,
        version INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        activated_at TEXT,
        suspended_at TEXT,
        blocked_at TEXT,
        closed_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS customer_accounts (
        id TEXT PRIMARY KEY,
        customer_id TEXT NOT NULL REFERENCES customers(id),
        account_type TEXT NOT NULL DEFAULT 'BUSINESS',
        industry TEXT NOT NULL DEFAULT '',
        company_size TEXT NOT NULL DEFAULT '',
        website TEXT NOT NULL DEFAULT '',
        parent_account_id TEXT,
        account_owner_user_id TEXT,
        territory_id TEXT,
        status TEXT NOT NULL DEFAULT 'ACTIVE'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS customer_contacts (
        id TEXT PRIMARY KEY,
        customer_id TEXT NOT NULL REFERENCES customers(id),
        customer_account_id TEXT REFERENCES customer_accounts(id),
        first_name TEXT NOT NULL,
        last_name TEXT NOT NULL DEFAULT '',
        job_title TEXT NOT NULL DEFAULT '',
        department TEXT NOT NULL DEFAULT '',
        phone_e164 TEXT,
        email TEXT,
        decision_role TEXT NOT NULL DEFAULT 'OTHER' CHECK (decision_role IN (
            'DECISION_MAKER','INFLUENCER','BUYER','USER',
            'FINANCE_CONTACT','DELIVERY_CONTACT','OTHER')),
        is_primary INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'ACTIVE'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS customer_addresses (
        id TEXT PRIMARY KEY,
        customer_id TEXT NOT NULL REFERENCES customers(id),
        address_type TEXT NOT NULL CHECK (address_type IN (
            'FISCAL','BILLING','DELIVERY','COMMERCIAL','PERSONAL')),
        street TEXT NOT NULL,
        external_number TEXT NOT NULL DEFAULT '',
        internal_number TEXT NOT NULL DEFAULT '',
        neighborhood TEXT NOT NULL DEFAULT '',
        postal_code TEXT NOT NULL DEFAULT '',
        locality TEXT NOT NULL DEFAULT '',
        municipality TEXT NOT NULL DEFAULT '',
        state TEXT NOT NULL DEFAULT '',
        country TEXT NOT NULL DEFAULT 'MX',
        address_references TEXT NOT NULL DEFAULT '',
        latitude REAL,
        longitude REAL,
        validation_status TEXT NOT NULL DEFAULT 'MANUAL' CHECK (validation_status IN (
            'MANUAL','VALIDATED','FAILED')),
        is_default INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS customer_tax_profiles (
        id TEXT PRIMARY KEY,
        customer_id TEXT NOT NULL REFERENCES customers(id),
        tax_identifier TEXT NOT NULL DEFAULT '',
        legal_name TEXT NOT NULL DEFAULT '',
        tax_regime TEXT NOT NULL DEFAULT '',
        fiscal_postal_code TEXT NOT NULL DEFAULT '',
        default_cfdi_use TEXT NOT NULL DEFAULT '',
        billing_email TEXT,
        validation_status TEXT NOT NULL DEFAULT 'MANUAL' CHECK (validation_status IN (
            'MANUAL','VALIDATED','FAILED')),
        validated_at TEXT,
        UNIQUE (customer_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS customer_audit_log (
        id TEXT PRIMARY KEY,
        customer_id TEXT,
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
    CREATE TABLE IF NOT EXISTS customer_outbox (
        id TEXT PRIMARY KEY,
        event_id TEXT NOT NULL,
        event_name TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        operation_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','DISPATCHED')),
        created_at TEXT NOT NULL,
        dispatched_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS customer_processed_events (
        event_id TEXT PRIMARY KEY,
        event_name TEXT NOT NULL,
        operation_id TEXT NOT NULL,
        processed_at TEXT NOT NULL
    )
    """,
)

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_customers_number ON customers(customer_number)",
    "CREATE INDEX IF NOT EXISTS idx_customers_status ON customers(status)",
    "CREATE INDEX IF NOT EXISTS idx_customers_display_name ON customers(display_name)",
    "CREATE INDEX IF NOT EXISTS idx_customers_owner ON customers(account_owner_user_id)",
    "CREATE INDEX IF NOT EXISTS idx_customers_branch ON customers(origin_branch_id)",
    "CREATE INDEX IF NOT EXISTS idx_customers_territory ON customers(territory_id)",
    "CREATE INDEX IF NOT EXISTS idx_customer_accounts_customer ON customer_accounts(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_customer_contacts_customer ON customer_contacts(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_customer_contacts_account ON customer_contacts(customer_account_id)",
    "CREATE INDEX IF NOT EXISTS idx_customer_addresses_customer ON customer_addresses(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_customer_tax_profiles_customer ON customer_tax_profiles(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_customer_audit_customer ON customer_audit_log(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_customer_outbox_status ON customer_outbox(status)",
)


def create_customers_crm_schema(conn) -> None:
    """Create the canonical Customer Master schema (idempotent). DDL lives only here."""
    for statement in _DDL:
        conn.execute(statement)
    for index in _INDEXES:
        conn.execute(index)


def drop_customers_crm_schema(conn) -> list[str]:
    """Drop the Customer Master bounded-context tables (dev reset). Reverse
    dependency order."""
    dropped: list[str] = []
    for table in reversed(CUSTOMER_TABLES):
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        dropped.append(table)
    return dropped
