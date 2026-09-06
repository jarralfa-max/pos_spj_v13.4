"""Customer Credit bounded context — born-clean UUIDv7 schema (single
source of truth for CRM-8+).

Covers Perfil de Crédito / Límites (CRM-8). Separate schema file from
``crm_schema.py``/``customer_service_schema.py`` — ``customer_credit`` is
its own sub-bounded-context per CRM-1's package layout, same convention as
every other sibling schema file in this module.

Deliberately does NOT define any accounts-receivable/CxC table
(``cuentas_por_cobrar``/``movimientos_credito`` or a parallel of either) —
§40: "CxC: Finanzas es dueño... no crear ledger financiero paralelo."
Enforced by ``tests/architecture/test_customers_crm_does_not_duplicate_cxc.py``
(CRM-1), which already scans this sub-bounded-context's roots.

Rules (REGLA CERO, master prompt §11):
- Every id is ``TEXT NOT NULL PRIMARY KEY`` holding a lowercase UUIDv7.
- Idempotency is structural: UNIQUE(operation_id), UNIQUE(customer_id) on
  the profile table (one credit profile per customer).
- Every amount is ``TEXT`` (Decimal), never ``REAL``.
- Sin secuencias auto-numéricas ni identidades de cursor.

Only a migration in ``migrations/`` may execute this DDL.
"""

from __future__ import annotations

#: Creation order (parents first). Drop order is the reverse.
CUSTOMER_CREDIT_TABLES: tuple[str, ...] = (
    "customer_credit_profiles",
    "customer_credit_audit_log",
    "customer_credit_outbox",
    "customer_credit_processed_events",
)

_DDL = (
    """
    CREATE TABLE IF NOT EXISTS customer_credit_profiles (
        id TEXT NOT NULL PRIMARY KEY,
        customer_id TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL DEFAULT 'PENDING_APPROVAL' CHECK (status IN (
            'PENDING_APPROVAL','UNDER_REVIEW','AUTHORIZED','SUSPENDED','BLOCKED','CLOSED')),
        credit_limit TEXT NOT NULL DEFAULT '0',
        payment_terms_days INTEGER NOT NULL DEFAULT 0,
        risk_level TEXT NOT NULL DEFAULT 'MEDIUM' CHECK (risk_level IN (
            'LOW','MEDIUM','HIGH','VERY_HIGH')),
        requested_by_user_id TEXT,
        authorized_at TEXT,
        authorized_by_user_id TEXT,
        suspended_at TEXT,
        blocked_at TEXT,
        review_at TEXT,
        closed_at TEXT,
        close_reason TEXT NOT NULL DEFAULT '',
        version INTEGER NOT NULL DEFAULT 1,
        operation_id TEXT UNIQUE,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS customer_credit_audit_log (
        id TEXT NOT NULL PRIMARY KEY,
        customer_id TEXT,
        profile_id TEXT,
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
    CREATE TABLE IF NOT EXISTS customer_credit_outbox (
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
    CREATE TABLE IF NOT EXISTS customer_credit_processed_events (
        event_id TEXT NOT NULL PRIMARY KEY,
        event_name TEXT NOT NULL,
        operation_id TEXT NOT NULL,
        processed_at TEXT NOT NULL
    )
    """,
)

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_customer_credit_profiles_customer"
    " ON customer_credit_profiles(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_customer_credit_profiles_status"
    " ON customer_credit_profiles(status)",
    "CREATE INDEX IF NOT EXISTS idx_customer_credit_audit_customer"
    " ON customer_credit_audit_log(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_customer_credit_audit_profile"
    " ON customer_credit_audit_log(profile_id)",
    "CREATE INDEX IF NOT EXISTS idx_customer_credit_outbox_status"
    " ON customer_credit_outbox(status)",
)


def create_customer_credit_schema(conn) -> None:
    """Create the canonical Customer Credit schema (idempotent). DDL lives
    only here."""
    for statement in _DDL:
        conn.execute(statement)
    for index in _INDEXES:
        conn.execute(index)


def drop_customer_credit_schema(conn) -> list[str]:
    """Drop the Customer Credit bounded-context tables (dev reset).
    Reverse dependency order."""
    dropped: list[str] = []
    for table in reversed(CUSTOMER_CREDIT_TABLES):
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        dropped.append(table)
    return dropped
