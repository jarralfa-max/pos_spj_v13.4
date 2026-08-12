"""CRM (relationship) bounded context — born-clean UUIDv7 schema (single
source of truth for CRM-4+).

Covers Leads (CRM-4), Opportunities/pipeline (CRM-5), and Activities/Tasks/
Notes/Reminders (CRM-6). Service Cases (CRM-7) extend this same file with
their own tables when that phase lands — one schema file per sub-bounded-
context, same convention as
backend/infrastructure/db/schema/customers_crm_schema.py.

Rules (REGLA CERO, master prompt §11):
- Every id is ``TEXT PRIMARY KEY`` holding a lowercase UUIDv7.
- ``lead_number`` (folio) is a separate UNIQUE column, never the PK.
- Idempotency is structural: UNIQUE(operation_id), UNIQUE(lead_number).
- Sin secuencias auto-numéricas ni identidades de cursor.

Only a migration in ``migrations/`` may execute this DDL.
"""

from __future__ import annotations

#: Creation order (parents first). Drop order is the reverse.
CRM_TABLES: tuple[str, ...] = (
    "leads",
    "lead_qualifications",
    "crm_stage_definitions",
    "opportunities",
    "opportunity_stage_history",
    "opportunity_product_interests",
    "crm_activities",
    "crm_tasks",
    "crm_notes",
    "crm_reminders",
    "crm_audit_log",
    "crm_outbox",
    "crm_processed_events",
)

_DDL = (
    """
    CREATE TABLE IF NOT EXISTS leads (
        id TEXT PRIMARY KEY,
        lead_number TEXT NOT NULL UNIQUE,
        display_name TEXT NOT NULL,
        company_name TEXT NOT NULL DEFAULT '',
        contact_name TEXT NOT NULL DEFAULT '',
        phone_e164 TEXT,
        email TEXT,
        source TEXT NOT NULL DEFAULT 'OTHER' CHECK (source IN (
            'WALK_IN','POS','WHATSAPP','PHONE','REFERRAL','SOCIAL_MEDIA',
            'WEBSITE','CAMPAIGN','IMPORT','SALES_REP','OTHER')),
        campaign_reference_id TEXT,
        origin_branch_id TEXT,
        assigned_user_id TEXT,
        territory_id TEXT,
        status TEXT NOT NULL DEFAULT 'NEW' CHECK (status IN (
            'NEW','ASSIGNED','CONTACTED','NURTURING','QUALIFIED',
            'UNQUALIFIED','CONVERTED','LOST','ARCHIVED')),
        score INTEGER NOT NULL DEFAULT 0,
        priority TEXT NOT NULL DEFAULT 'NORMAL' CHECK (priority IN (
            'LOW','NORMAL','HIGH','URGENT')),
        estimated_value TEXT,
        expected_purchase_date TEXT,
        last_contact_at TEXT,
        next_action_at TEXT,
        created_by_user_id TEXT,
        operation_id TEXT UNIQUE,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS lead_qualifications (
        id TEXT PRIMARY KEY,
        lead_id TEXT NOT NULL REFERENCES leads(id),
        model TEXT NOT NULL CHECK (model IN (
            'MANUAL','SCORE_BASED','BANT_LIKE','CUSTOM_RULE')),
        decision TEXT NOT NULL CHECK (decision IN ('QUALIFIED','UNQUALIFIED')),
        qualified_by_user_id TEXT NOT NULL,
        criteria_json TEXT NOT NULL DEFAULT '{}',
        notes TEXT NOT NULL DEFAULT '',
        score INTEGER,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS crm_stage_definitions (
        id TEXT PRIMARY KEY,
        code TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        sequence_order INTEGER NOT NULL,
        probability_default INTEGER NOT NULL DEFAULT 0,
        is_won_stage INTEGER NOT NULL DEFAULT 0,
        is_lost_stage INTEGER NOT NULL DEFAULT 0,
        required_fields_json TEXT NOT NULL DEFAULT '[]',
        min_activities INTEGER NOT NULL DEFAULT 0,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS opportunities (
        id TEXT PRIMARY KEY,
        opportunity_number TEXT NOT NULL UNIQUE,
        customer_id TEXT NOT NULL,
        account_id TEXT,
        name TEXT NOT NULL,
        source_lead_id TEXT,
        owner_user_id TEXT,
        stage_id TEXT NOT NULL REFERENCES crm_stage_definitions(id),
        status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN (
            'OPEN','WON','LOST','CANCELLED','ON_HOLD')),
        amount TEXT,
        probability INTEGER NOT NULL DEFAULT 0,
        expected_close_date TEXT,
        territory_id TEXT,
        origin_branch_id TEXT,
        description TEXT NOT NULL DEFAULT '',
        close_reason TEXT NOT NULL DEFAULT '',
        closed_at TEXT,
        created_by_user_id TEXT,
        operation_id TEXT UNIQUE,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS opportunity_stage_history (
        id TEXT PRIMARY KEY,
        opportunity_id TEXT NOT NULL REFERENCES opportunities(id),
        from_stage_id TEXT,
        to_stage_id TEXT NOT NULL REFERENCES crm_stage_definitions(id),
        changed_by_user_id TEXT NOT NULL,
        reason TEXT NOT NULL DEFAULT '',
        probability INTEGER,
        expected_close_date TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS opportunity_product_interests (
        id TEXT PRIMARY KEY,
        opportunity_id TEXT NOT NULL REFERENCES opportunities(id),
        product_reference_id TEXT,
        product_name TEXT NOT NULL,
        quantity TEXT NOT NULL,
        estimated_unit_price TEXT,
        notes TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS crm_activities (
        id TEXT PRIMARY KEY,
        activity_type TEXT NOT NULL CHECK (activity_type IN (
            'CALL','MEETING','VISIT','EMAIL','WHATSAPP','FOLLOW_UP',
            'QUOTE_REVIEW','PAYMENT_FOLLOW_UP','OTHER')),
        related_entity_type TEXT NOT NULL CHECK (related_entity_type IN (
            'LEAD','OPPORTUNITY','CUSTOMER','CASE')),
        related_entity_id TEXT NOT NULL,
        subject TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'PLANNED' CHECK (status IN (
            'PLANNED','IN_PROGRESS','COMPLETED','CANCELLED')),
        scheduled_at TEXT,
        completed_at TEXT,
        assigned_user_id TEXT,
        description TEXT NOT NULL DEFAULT '',
        created_by_user_id TEXT,
        operation_id TEXT UNIQUE,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS crm_tasks (
        id TEXT PRIMARY KEY,
        related_entity_type TEXT NOT NULL CHECK (related_entity_type IN (
            'LEAD','OPPORTUNITY','CUSTOMER','CASE')),
        related_entity_id TEXT NOT NULL,
        title TEXT NOT NULL,
        due_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'PLANNED' CHECK (status IN (
            'PLANNED','COMPLETED','CANCELLED')),
        assigned_user_id TEXT,
        description TEXT NOT NULL DEFAULT '',
        completed_at TEXT,
        created_by_user_id TEXT,
        operation_id TEXT UNIQUE,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS crm_notes (
        id TEXT PRIMARY KEY,
        related_entity_type TEXT NOT NULL CHECK (related_entity_type IN (
            'LEAD','OPPORTUNITY','CUSTOMER','CASE')),
        related_entity_id TEXT NOT NULL,
        body TEXT NOT NULL,
        author_user_id TEXT NOT NULL,
        is_private INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS crm_reminders (
        id TEXT PRIMARY KEY,
        channel TEXT NOT NULL CHECK (channel IN (
            'IN_APP','EMAIL','WHATSAPP_INTERNAL','PUSH_FUTURE')),
        remind_at TEXT NOT NULL,
        recipient_user_id TEXT NOT NULL,
        task_id TEXT REFERENCES crm_tasks(id),
        activity_id TEXT REFERENCES crm_activities(id),
        message TEXT NOT NULL DEFAULT '',
        created_by_user_id TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS crm_audit_log (
        id TEXT PRIMARY KEY,
        lead_id TEXT,
        opportunity_id TEXT,
        activity_id TEXT,
        task_id TEXT,
        note_id TEXT,
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
    CREATE TABLE IF NOT EXISTS crm_outbox (
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
    CREATE TABLE IF NOT EXISTS crm_processed_events (
        event_id TEXT PRIMARY KEY,
        event_name TEXT NOT NULL,
        operation_id TEXT NOT NULL,
        processed_at TEXT NOT NULL
    )
    """,
)

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_leads_number ON leads(lead_number)",
    "CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status)",
    "CREATE INDEX IF NOT EXISTS idx_leads_assigned ON leads(assigned_user_id)",
    "CREATE INDEX IF NOT EXISTS idx_leads_branch ON leads(origin_branch_id)",
    "CREATE INDEX IF NOT EXISTS idx_leads_territory ON leads(territory_id)",
    "CREATE INDEX IF NOT EXISTS idx_lead_qualifications_lead ON lead_qualifications(lead_id)",
    "CREATE INDEX IF NOT EXISTS idx_opportunities_number ON opportunities(opportunity_number)",
    "CREATE INDEX IF NOT EXISTS idx_opportunities_customer ON opportunities(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_opportunities_owner ON opportunities(owner_user_id)",
    "CREATE INDEX IF NOT EXISTS idx_opportunities_stage ON opportunities(stage_id)",
    "CREATE INDEX IF NOT EXISTS idx_opportunities_status ON opportunities(status)",
    "CREATE INDEX IF NOT EXISTS idx_opp_stage_history_opp"
    " ON opportunity_stage_history(opportunity_id)",
    "CREATE INDEX IF NOT EXISTS idx_opp_product_interests_opp"
    " ON opportunity_product_interests(opportunity_id)",
    "CREATE INDEX IF NOT EXISTS idx_crm_activities_related"
    " ON crm_activities(related_entity_type, related_entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_crm_activities_assigned ON crm_activities(assigned_user_id)",
    "CREATE INDEX IF NOT EXISTS idx_crm_activities_status ON crm_activities(status)",
    "CREATE INDEX IF NOT EXISTS idx_crm_tasks_related"
    " ON crm_tasks(related_entity_type, related_entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_crm_tasks_assigned ON crm_tasks(assigned_user_id)",
    "CREATE INDEX IF NOT EXISTS idx_crm_tasks_due ON crm_tasks(due_at)",
    "CREATE INDEX IF NOT EXISTS idx_crm_notes_related"
    " ON crm_notes(related_entity_type, related_entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_crm_reminders_task ON crm_reminders(task_id)",
    "CREATE INDEX IF NOT EXISTS idx_crm_reminders_activity ON crm_reminders(activity_id)",
    "CREATE INDEX IF NOT EXISTS idx_crm_audit_lead ON crm_audit_log(lead_id)",
    "CREATE INDEX IF NOT EXISTS idx_crm_audit_opportunity ON crm_audit_log(opportunity_id)",
    "CREATE INDEX IF NOT EXISTS idx_crm_audit_activity ON crm_audit_log(activity_id)",
    "CREATE INDEX IF NOT EXISTS idx_crm_audit_task ON crm_audit_log(task_id)",
    "CREATE INDEX IF NOT EXISTS idx_crm_audit_note ON crm_audit_log(note_id)",
    "CREATE INDEX IF NOT EXISTS idx_crm_outbox_status ON crm_outbox(status)",
)


def create_crm_schema(conn) -> None:
    """Create the canonical CRM (relationship) schema (idempotent). DDL
    lives only here."""
    for statement in _DDL:
        conn.execute(statement)
    for index in _INDEXES:
        conn.execute(index)


def drop_crm_schema(conn) -> list[str]:
    """Drop the CRM bounded-context tables (dev reset). Reverse dependency
    order."""
    dropped: list[str] = []
    for table in reversed(CRM_TABLES):
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        dropped.append(table)
    return dropped
