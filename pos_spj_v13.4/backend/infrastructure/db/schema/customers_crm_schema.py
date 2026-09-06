"""Customer Master bounded context — born-clean UUIDv7 schema (single source
of truth for CRM-3).

Rules (REGLA CERO, master prompt §11):
- Every id is ``TEXT NOT NULL PRIMARY KEY`` holding a lowercase UUIDv7 (PostgreSQL: UUID).
- ``customer_number`` (folio) is a separate UNIQUE column, never the PK.
- No REAL columns for money/credit — this schema has none (credit lives in
  Finanzas' CxC tables per §40; CRM-8 adds ``customer_credit_profiles`` under
  a Decimal-as-TEXT convention when that phase lands, not here).
- Idempotency is structural: UNIQUE(operation_id) where an operation must
  not repeat; UNIQUE(customer_number); UNIQUE(source event_id) in processed
  events.
- Sin secuencias auto-numéricas ni identidades de cursor; sin compatibilidad legacy —
  the legacy ``clientes`` table (docs/architecture/CRM_0_CUSTOMER_MASTER_AUDIT.md
  §4) is untouched by this file. CRM-21 added ``customers.legacy_customer_id``
  (nullable, unique-when-set) as a bridge column so read-side consumers can
  resolve a legacy ``clientes.id`` to this aggregate without migrating
  ``clientes`` itself — see
  ``backend/application/customers/use_cases/legacy_customer_bridge_use_cases.py``.
  Writers on the six legacy consumer areas (POS/Ventas/WhatsApp/Delivery/
  Fidelidad/Finanzas) still target ``clientes`` directly; that full cutover
  remains future work.

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
    "customer_duplicate_candidates",
    "customer_merge_records",
    "customer_data_quality_issues",
    "customer_import_batches",
    "customer_sync_conflicts",
    "customer_audit_log",
    "customer_outbox",
    "customer_processed_events",
)

_DDL = (
    """
    CREATE TABLE IF NOT EXISTS customers (
        id TEXT NOT NULL PRIMARY KEY,
        customer_number TEXT NOT NULL UNIQUE,
        customer_type TEXT NOT NULL CHECK (customer_type IN (
            'INDIVIDUAL','BUSINESS','PUBLIC_CUSTOMER','EMPLOYEE','INTERNAL','OTHER')),
        display_name TEXT NOT NULL,
        normalized_name TEXT NOT NULL DEFAULT '',
        legal_name TEXT NOT NULL DEFAULT '',
        normalized_legal_name TEXT NOT NULL DEFAULT '',
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
        closed_at TEXT,
        last_purchase_at TEXT,
        purchase_count INTEGER NOT NULL DEFAULT 0,
        legacy_customer_id TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS customer_accounts (
        id TEXT NOT NULL PRIMARY KEY,
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
        id TEXT NOT NULL PRIMARY KEY,
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
        id TEXT NOT NULL PRIMARY KEY,
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
        id TEXT NOT NULL PRIMARY KEY,
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
    CREATE TABLE IF NOT EXISTS customer_duplicate_candidates (
        id TEXT NOT NULL PRIMARY KEY,
        customer_id_a TEXT NOT NULL REFERENCES customers(id),
        customer_id_b TEXT NOT NULL REFERENCES customers(id),
        match_reasons_json TEXT NOT NULL DEFAULT '[]',
        status TEXT NOT NULL DEFAULT 'DETECTED' CHECK (status IN (
            'DETECTED','UNDER_REVIEW','CONFIRMED_DUPLICATE','DISMISSED','MERGED')),
        reviewed_by_user_id TEXT,
        reviewed_at TEXT,
        resolution_reason TEXT NOT NULL DEFAULT '',
        operation_id TEXT UNIQUE,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS customer_merge_records (
        id TEXT NOT NULL PRIMARY KEY,
        master_customer_id TEXT NOT NULL REFERENCES customers(id),
        merged_customer_id TEXT NOT NULL REFERENCES customers(id),
        duplicate_candidate_id TEXT REFERENCES customer_duplicate_candidates(id),
        proposed_by_user_id TEXT NOT NULL,
        reason TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'PROPOSED' CHECK (status IN (
            'PROPOSED','EXECUTED','REJECTED')),
        executed_by_user_id TEXT,
        executed_at TEXT,
        rejected_by_user_id TEXT,
        rejected_at TEXT,
        rejection_reason TEXT NOT NULL DEFAULT '',
        operation_id TEXT UNIQUE,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS customer_data_quality_issues (
        id TEXT NOT NULL PRIMARY KEY,
        customer_id TEXT NOT NULL REFERENCES customers(id),
        rule_code TEXT NOT NULL CHECK (rule_code IN (
            'INCOMPLETE_NAME','INVALID_PHONE','INVALID_EMAIL','INVALID_TAX_ID',
            'INCOMPLETE_ADDRESS')),
        description TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN (
            'OPEN','ACKNOWLEDGED','CORRECTED','DISMISSED')),
        acknowledged_by_user_id TEXT,
        acknowledged_at TEXT,
        corrected_at TEXT,
        dismissed_by_user_id TEXT,
        dismissed_at TEXT,
        dismissal_reason TEXT NOT NULL DEFAULT '',
        operation_id TEXT UNIQUE,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS customer_import_batches (
        id TEXT NOT NULL PRIMARY KEY,
        submitted_by_user_id TEXT NOT NULL,
        is_sensitive INTEGER NOT NULL DEFAULT 0,
        total_rows INTEGER NOT NULL DEFAULT 0,
        created_count INTEGER NOT NULL DEFAULT 0,
        updated_count INTEGER NOT NULL DEFAULT 0,
        rejected_count INTEGER NOT NULL DEFAULT 0,
        duplicate_count INTEGER NOT NULL DEFAULT 0,
        error_count INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'PROCESSING' CHECK (status IN (
            'PENDING_APPROVAL','PROCESSING','COMPLETED','PARTIAL','FAILED','REJECTED')),
        approved_by_user_id TEXT,
        approved_at TEXT,
        pending_rows_json TEXT,
        operation_id TEXT UNIQUE,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS customer_sync_conflicts (
        id TEXT NOT NULL PRIMARY KEY,
        customer_id TEXT NOT NULL REFERENCES customers(id),
        conflict_type TEXT NOT NULL CHECK (conflict_type IN (
            'CUSTOMER_UPDATED_REMOTELY','DUPLICATE_CREATED','CONTACT_CONFLICT',
            'ADDRESS_CONFLICT','CONSENT_CONFLICT','CREDIT_CONFLICT')),
        local_version INTEGER NOT NULL,
        remote_snapshot_json TEXT NOT NULL DEFAULT '{}',
        status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN (
            'OPEN','RESOLVED_LOCAL','RESOLVED_REMOTE','RESOLVED_MERGED')),
        detail TEXT NOT NULL DEFAULT '',
        detected_at TEXT NOT NULL,
        resolved_at TEXT,
        resolved_by_user_id TEXT,
        resolution_note TEXT NOT NULL DEFAULT '',
        operation_id TEXT UNIQUE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS customer_audit_log (
        id TEXT NOT NULL PRIMARY KEY,
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
        id TEXT NOT NULL PRIMARY KEY,
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
        event_id TEXT NOT NULL PRIMARY KEY,
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
    # CRM-41 (Fase 7): blocking keys for CustomerDuplicatePolicy — lets
    # find_duplicate_rows() filter in SQL instead of loading every customer.
    "CREATE INDEX IF NOT EXISTS idx_customers_normalized_name ON customers(normalized_name)",
    "CREATE INDEX IF NOT EXISTS idx_customers_normalized_legal_name"
    " ON customers(normalized_legal_name)",
    "CREATE INDEX IF NOT EXISTS idx_customers_owner ON customers(account_owner_user_id)",
    "CREATE INDEX IF NOT EXISTS idx_customers_branch ON customers(origin_branch_id)",
    "CREATE INDEX IF NOT EXISTS idx_customers_territory ON customers(territory_id)",
    # CRM-21: legacy `clientes.id` bridge — nullable+partial so customers
    # created natively (no legacy origin) never collide on NULL.
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_customers_legacy_customer_id ON customers(legacy_customer_id)"
    " WHERE legacy_customer_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_customer_accounts_customer ON customer_accounts(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_customer_contacts_customer ON customer_contacts(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_customer_contacts_account ON customer_contacts(customer_account_id)",
    # CRM-41 (Fase 7): blocking keys for duplicate detection + typeahead —
    # both previously only reachable via a full LEFT JOIN scan.
    "CREATE INDEX IF NOT EXISTS idx_customer_contacts_phone ON customer_contacts(phone_e164)",
    "CREATE INDEX IF NOT EXISTS idx_customer_contacts_email ON customer_contacts(email)",
    "CREATE INDEX IF NOT EXISTS idx_customer_addresses_customer ON customer_addresses(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_customer_tax_profiles_customer ON customer_tax_profiles(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_customer_tax_profiles_identifier"
    " ON customer_tax_profiles(tax_identifier)",
    "CREATE INDEX IF NOT EXISTS idx_customer_dupe_candidates_a"
    " ON customer_duplicate_candidates(customer_id_a)",
    "CREATE INDEX IF NOT EXISTS idx_customer_dupe_candidates_b"
    " ON customer_duplicate_candidates(customer_id_b)",
    "CREATE INDEX IF NOT EXISTS idx_customer_dupe_candidates_status"
    " ON customer_duplicate_candidates(status)",
    "CREATE INDEX IF NOT EXISTS idx_customer_merge_records_master"
    " ON customer_merge_records(master_customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_customer_merge_records_merged"
    " ON customer_merge_records(merged_customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_customer_quality_issues_customer"
    " ON customer_data_quality_issues(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_customer_quality_issues_status"
    " ON customer_data_quality_issues(status)",
    "CREATE INDEX IF NOT EXISTS idx_customer_import_batches_status"
    " ON customer_import_batches(status)",
    "CREATE INDEX IF NOT EXISTS idx_customer_sync_conflicts_customer"
    " ON customer_sync_conflicts(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_customer_sync_conflicts_status"
    " ON customer_sync_conflicts(status)",
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
