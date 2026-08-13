"""Customer Privacy bounded context — born-clean UUIDv7 schema (single
source of truth for CRM-9+).

Covers Consentimientos/Preferencias/Solicitudes/Retención (CRM-9).
Separate schema file from ``crm_schema.py``/``customer_service_schema.py``/
``customer_credit_schema.py`` — ``customer_privacy`` is its own
sub-bounded-context per CRM-1's package layout, the last of the five CRM-1
scaffolded.

Rules (REGLA CERO, master prompt §11):
- Every id is ``TEXT PRIMARY KEY`` holding a lowercase UUIDv7.
- ``request_number`` (folio) is a separate UNIQUE column, never the PK.
- Idempotency is structural: UNIQUE(operation_id) where applicable,
  UNIQUE(customer_id) on the 1:1 preference table.
- Sin secuencias auto-numéricas ni identidades de cursor.

Only a migration in ``migrations/`` may execute this DDL.
"""

from __future__ import annotations

#: Creation order (parents first). Drop order is the reverse.
CUSTOMER_PRIVACY_TABLES: tuple[str, ...] = (
    "customer_consents",
    "customer_communication_preferences",
    "customer_data_retention_policies",
    "customer_privacy_requests",
    "customer_privacy_audit_log",
    "customer_privacy_outbox",
    "customer_privacy_processed_events",
)

_DDL = (
    """
    CREATE TABLE IF NOT EXISTS customer_consents (
        id TEXT PRIMARY KEY,
        customer_id TEXT NOT NULL,
        consent_type TEXT NOT NULL CHECK (consent_type IN (
            'PRIVACY_NOTICE','WHATSAPP','EMAIL','SMS','MARKETING','PROFILING',
            'TERMS','DATA_SHARING')),
        status TEXT NOT NULL CHECK (status IN (
            'PENDING','GRANTED','WITHDRAWN','NOT_REQUIRED')),
        channel TEXT NOT NULL DEFAULT 'OTHER' CHECK (channel IN (
            'WEB','WHATSAPP','IN_PERSON','PHONE','EMAIL','IMPORTED','OTHER')),
        evidence_reference TEXT NOT NULL DEFAULT '',
        captured_by_user_id TEXT,
        granted_at TEXT,
        withdrawn_at TEXT,
        withdrawal_reason TEXT NOT NULL DEFAULT '',
        expires_at TEXT,
        operation_id TEXT UNIQUE,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS customer_communication_preferences (
        id TEXT PRIMARY KEY,
        customer_id TEXT NOT NULL UNIQUE,
        preferred_channel TEXT NOT NULL DEFAULT 'WHATSAPP' CHECK (preferred_channel IN (
            'WHATSAPP','EMAIL','SMS','PHONE','NONE')),
        preferred_language TEXT NOT NULL DEFAULT 'es',
        contact_hours_start TEXT,
        contact_hours_end TEXT,
        allow_transactional INTEGER NOT NULL DEFAULT 1,
        allow_operational INTEGER NOT NULL DEFAULT 1,
        allow_marketing INTEGER NOT NULL DEFAULT 0,
        allow_promotions INTEGER NOT NULL DEFAULT 0,
        allow_reminders INTEGER NOT NULL DEFAULT 1,
        updated_by_user_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS customer_data_retention_policies (
        id TEXT PRIMARY KEY,
        code TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        data_category TEXT NOT NULL,
        retention_days INTEGER NOT NULL,
        legal_basis TEXT NOT NULL DEFAULT '',
        customer_type TEXT CHECK (customer_type IS NULL OR customer_type IN (
            'INDIVIDUAL','BUSINESS')),
        customer_status TEXT,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS customer_privacy_requests (
        id TEXT PRIMARY KEY,
        request_number TEXT NOT NULL UNIQUE,
        customer_id TEXT NOT NULL,
        request_type TEXT NOT NULL CHECK (request_type IN (
            'ACCESS','RECTIFICATION','CANCELLATION','OPPOSITION','EXPORT',
            'ANONYMIZATION','CONSENT_WITHDRAWAL')),
        description TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'RECEIVED' CHECK (status IN (
            'RECEIVED','VALIDATING','IN_PROGRESS','COMPLETED','REJECTED','CANCELLED')),
        related_consent_id TEXT,
        logged_by_user_id TEXT,
        validated_by_user_id TEXT,
        processed_by_user_id TEXT,
        resolution_notes TEXT NOT NULL DEFAULT '',
        received_at TEXT NOT NULL,
        validated_at TEXT,
        started_at TEXT,
        completed_at TEXT,
        rejected_at TEXT,
        cancelled_at TEXT,
        operation_id TEXT UNIQUE,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS customer_privacy_audit_log (
        id TEXT PRIMARY KEY,
        customer_id TEXT,
        request_id TEXT,
        consent_id TEXT,
        action TEXT NOT NULL,
        actor_user_id TEXT,
        authorized_by_user_id TEXT,
        before_json TEXT,
        after_json TEXT,
        reason TEXT NOT NULL DEFAULT '',
        operation_id TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS customer_privacy_outbox (
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
    CREATE TABLE IF NOT EXISTS customer_privacy_processed_events (
        event_id TEXT PRIMARY KEY,
        event_name TEXT NOT NULL,
        operation_id TEXT NOT NULL,
        processed_at TEXT NOT NULL
    )
    """,
)

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_customer_consents_customer ON customer_consents(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_customer_consents_type ON customer_consents(consent_type)",
    "CREATE INDEX IF NOT EXISTS idx_customer_privacy_requests_number"
    " ON customer_privacy_requests(request_number)",
    "CREATE INDEX IF NOT EXISTS idx_customer_privacy_requests_customer"
    " ON customer_privacy_requests(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_customer_privacy_requests_status"
    " ON customer_privacy_requests(status)",
    "CREATE INDEX IF NOT EXISTS idx_customer_privacy_audit_customer"
    " ON customer_privacy_audit_log(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_customer_privacy_audit_request"
    " ON customer_privacy_audit_log(request_id)",
    "CREATE INDEX IF NOT EXISTS idx_customer_privacy_outbox_status"
    " ON customer_privacy_outbox(status)",
)


def create_customer_privacy_schema(conn) -> None:
    """Create the canonical Customer Privacy schema (idempotent). DDL lives
    only here."""
    for statement in _DDL:
        conn.execute(statement)
    for index in _INDEXES:
        conn.execute(index)


def drop_customer_privacy_schema(conn) -> list[str]:
    """Drop the Customer Privacy bounded-context tables (dev reset).
    Reverse dependency order."""
    dropped: list[str] = []
    for table in reversed(CUSTOMER_PRIVACY_TABLES):
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        dropped.append(table)
    return dropped
