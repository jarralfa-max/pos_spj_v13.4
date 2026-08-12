"""Customer Service (atención al cliente) bounded context — born-clean
UUIDv7 schema (single source of truth for CRM-7+).

Covers Casos/SLA/Escalamiento (CRM-7). Separate schema file from
``crm_schema.py`` — ``customer_service`` is its own sub-bounded-context per
CRM-1's package layout (``backend/domain/customer_service/``, ...), same
convention as ``customers_crm_schema.py``/``crm_schema.py`` each owning
their own DDL.

``CRMActivity``/``CRMTask``/``CRMNote`` (from ``crm_schema.py``, CRM-6) are
reused for Service Cases via
``related_entity_type='CASE', related_entity_id=service_cases.id`` — no
parallel activity/task/note tables live here (see
backend/domain/customer_service/entities/__init__.py for why).

Rules (REGLA CERO, master prompt §11):
- Every id is ``TEXT PRIMARY KEY`` holding a lowercase UUIDv7.
- ``case_number`` (folio) is a separate UNIQUE column, never the PK.
- Idempotency is structural: UNIQUE(operation_id), UNIQUE(case_number).
- Sin secuencias auto-numéricas ni identidades de cursor.

Only a migration in ``migrations/`` may execute this DDL.
"""

from __future__ import annotations

#: Creation order (parents first). Drop order is the reverse.
CUSTOMER_SERVICE_TABLES: tuple[str, ...] = (
    "service_case_categories",
    "service_level_policies",
    "service_cases",
    "service_case_resolutions",
    "service_case_escalations",
    "sla_instances",
    "customer_service_audit_log",
    "customer_service_outbox",
    "customer_service_processed_events",
)

_DDL = (
    """
    CREATE TABLE IF NOT EXISTS service_case_categories (
        id TEXT PRIMARY KEY,
        code TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS service_level_policies (
        id TEXT PRIMARY KEY,
        code TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        first_response_minutes INTEGER NOT NULL,
        resolution_minutes INTEGER NOT NULL,
        case_type TEXT CHECK (case_type IS NULL OR case_type IN (
            'QUESTION','REQUEST','COMPLAINT','INCIDENT','RETURN_REQUEST',
            'DELIVERY_ISSUE','PAYMENT_ISSUE','PRODUCT_QUALITY','CREDIT_ISSUE','OTHER')),
        priority TEXT CHECK (priority IS NULL OR priority IN (
            'LOW','NORMAL','HIGH','URGENT','CRITICAL')),
        origin_branch_id TEXT,
        channel TEXT CHECK (channel IS NULL OR channel IN (
            'PHONE','EMAIL','WHATSAPP','WALK_IN','WEB','OTHER')),
        at_risk_threshold_pct INTEGER NOT NULL DEFAULT 80,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS service_cases (
        id TEXT PRIMARY KEY,
        case_number TEXT NOT NULL UNIQUE,
        customer_id TEXT NOT NULL,
        case_type TEXT NOT NULL CHECK (case_type IN (
            'QUESTION','REQUEST','COMPLAINT','INCIDENT','RETURN_REQUEST',
            'DELIVERY_ISSUE','PAYMENT_ISSUE','PRODUCT_QUALITY','CREDIT_ISSUE','OTHER')),
        subject TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'NEW' CHECK (status IN (
            'NEW','ASSIGNED','IN_PROGRESS','WAITING_CUSTOMER','WAITING_INTERNAL',
            'ESCALATED','RESOLVED','CLOSED','CANCELLED')),
        priority TEXT NOT NULL DEFAULT 'NORMAL' CHECK (priority IN (
            'LOW','NORMAL','HIGH','URGENT','CRITICAL')),
        category_id TEXT REFERENCES service_case_categories(id),
        description TEXT NOT NULL DEFAULT '',
        assigned_user_id TEXT,
        channel TEXT NOT NULL DEFAULT 'OTHER' CHECK (channel IN (
            'PHONE','EMAIL','WHATSAPP','WALK_IN','WEB','OTHER')),
        origin_branch_id TEXT,
        territory_id TEXT,
        is_sensitive INTEGER NOT NULL DEFAULT 0,
        reopen_count INTEGER NOT NULL DEFAULT 0,
        close_reason TEXT NOT NULL DEFAULT '',
        resolved_at TEXT,
        closed_at TEXT,
        created_by_user_id TEXT,
        operation_id TEXT UNIQUE,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS service_case_resolutions (
        id TEXT PRIMARY KEY,
        case_id TEXT NOT NULL REFERENCES service_cases(id),
        resolution_summary TEXT NOT NULL,
        resolved_by_user_id TEXT NOT NULL,
        root_cause TEXT NOT NULL DEFAULT '',
        customer_satisfied INTEGER,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS service_case_escalations (
        id TEXT PRIMARY KEY,
        case_id TEXT NOT NULL REFERENCES service_cases(id),
        reason TEXT NOT NULL CHECK (reason IN (
            'SLA_BREACHED','PRIORITY_CUSTOMER','CRITICAL_CASE','MULTIPLE_REOPENS',
            'FINANCIAL_IMPACT','REPUTATIONAL_RISK','OTHER')),
        level INTEGER NOT NULL,
        escalated_to_user_id TEXT NOT NULL,
        escalated_by_user_id TEXT NOT NULL,
        detail TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sla_instances (
        id TEXT PRIMARY KEY,
        case_id TEXT NOT NULL UNIQUE REFERENCES service_cases(id),
        policy_id TEXT NOT NULL REFERENCES service_level_policies(id),
        first_response_due_at TEXT NOT NULL,
        resolution_due_at TEXT NOT NULL,
        at_risk_threshold_pct INTEGER NOT NULL DEFAULT 80,
        first_response_at TEXT,
        resolved_at TEXT,
        paused INTEGER NOT NULL DEFAULT 0,
        escalation_level INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS customer_service_audit_log (
        id TEXT PRIMARY KEY,
        case_id TEXT,
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
    CREATE TABLE IF NOT EXISTS customer_service_outbox (
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
    CREATE TABLE IF NOT EXISTS customer_service_processed_events (
        event_id TEXT PRIMARY KEY,
        event_name TEXT NOT NULL,
        operation_id TEXT NOT NULL,
        processed_at TEXT NOT NULL
    )
    """,
)

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_service_cases_number ON service_cases(case_number)",
    "CREATE INDEX IF NOT EXISTS idx_service_cases_customer ON service_cases(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_service_cases_assigned ON service_cases(assigned_user_id)",
    "CREATE INDEX IF NOT EXISTS idx_service_cases_status ON service_cases(status)",
    "CREATE INDEX IF NOT EXISTS idx_service_case_resolutions_case"
    " ON service_case_resolutions(case_id)",
    "CREATE INDEX IF NOT EXISTS idx_service_case_escalations_case"
    " ON service_case_escalations(case_id)",
    "CREATE INDEX IF NOT EXISTS idx_sla_instances_case ON sla_instances(case_id)",
    "CREATE INDEX IF NOT EXISTS idx_customer_service_audit_case"
    " ON customer_service_audit_log(case_id)",
    "CREATE INDEX IF NOT EXISTS idx_customer_service_outbox_status"
    " ON customer_service_outbox(status)",
)


def create_customer_service_schema(conn) -> None:
    """Create the canonical Customer Service schema (idempotent). DDL lives
    only here."""
    for statement in _DDL:
        conn.execute(statement)
    for index in _INDEXES:
        conn.execute(index)


def drop_customer_service_schema(conn) -> list[str]:
    """Drop the Customer Service bounded-context tables (dev reset).
    Reverse dependency order."""
    dropped: list[str] = []
    for table in reversed(CUSTOMER_SERVICE_TABLES):
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        dropped.append(table)
    return dropped
