"""CRM (relationship) bounded context — born-clean UUIDv7 schema (single
source of truth for CRM-4+).

Covers Leads (CRM-4), Opportunities/pipeline (CRM-5), Activities/Tasks/
Notes/Reminders (CRM-6), and Segmentation/Tags/Territories/Portfolios/
Ownership (CRM-10). Service Cases (CRM-7) landed as a separate sibling
bounded context (customer_service) instead of extending this file — see
docs/refactor/CRM-7_atencion.md.

Rules (REGLA CERO, master prompt §11):
- Every id is ``TEXT NOT NULL PRIMARY KEY`` holding a lowercase UUIDv7.
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
    "sales_territories",
    "customer_portfolios",
    "customer_ownerships",
    "portfolio_assignments",
    "customer_segments",
    "customer_segment_memberships",
    "customer_tags",
    "customer_tag_assignments",
    "crm_automation_rules",
    "crm_automation_executions",
    "crm_sync_conflicts",
    "crm_audit_log",
    "crm_outbox",
    "crm_processed_events",
)

_DDL = (
    """
    CREATE TABLE IF NOT EXISTS leads (
        id TEXT NOT NULL PRIMARY KEY,
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
        id TEXT NOT NULL PRIMARY KEY,
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
        id TEXT NOT NULL PRIMARY KEY,
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
        id TEXT NOT NULL PRIMARY KEY,
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
        id TEXT NOT NULL PRIMARY KEY,
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
        id TEXT NOT NULL PRIMARY KEY,
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
        id TEXT NOT NULL PRIMARY KEY,
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
        id TEXT NOT NULL PRIMARY KEY,
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
        id TEXT NOT NULL PRIMARY KEY,
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
        id TEXT NOT NULL PRIMARY KEY,
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
    CREATE TABLE IF NOT EXISTS sales_territories (
        id TEXT NOT NULL PRIMARY KEY,
        code TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS customer_portfolios (
        id TEXT NOT NULL PRIMARY KEY,
        code TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        manager_user_id TEXT,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS customer_ownerships (
        id TEXT NOT NULL PRIMARY KEY,
        customer_id TEXT NOT NULL,
        ownership_type TEXT NOT NULL CHECK (ownership_type IN (
            'PRIMARY','SECONDARY','ACCOUNT_MANAGER','CREDIT_MANAGER','SERVICE_OWNER')),
        owner_user_id TEXT NOT NULL,
        assigned_by_user_id TEXT,
        reason TEXT NOT NULL DEFAULT '',
        operation_id TEXT UNIQUE,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS portfolio_assignments (
        id TEXT NOT NULL PRIMARY KEY,
        customer_id TEXT NOT NULL,
        portfolio_id TEXT NOT NULL REFERENCES customer_portfolios(id),
        assigned_by_user_id TEXT,
        reason TEXT NOT NULL DEFAULT '',
        operation_id TEXT UNIQUE,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS customer_segments (
        id TEXT NOT NULL PRIMARY KEY,
        code TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        rule_definition TEXT NOT NULL DEFAULT '',
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS customer_segment_memberships (
        id TEXT NOT NULL PRIMARY KEY,
        customer_id TEXT NOT NULL,
        segment_id TEXT NOT NULL REFERENCES customer_segments(id),
        source TEXT NOT NULL DEFAULT 'MANUAL' CHECK (source IN (
            'MANUAL','RULE_BASED','IMPORTED','ANALYTICS_GENERATED')),
        added_by_user_id TEXT,
        removed_at TEXT,
        removed_by_user_id TEXT,
        operation_id TEXT UNIQUE,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS customer_tags (
        id TEXT NOT NULL PRIMARY KEY,
        code TEXT NOT NULL UNIQUE,
        label TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS customer_tag_assignments (
        id TEXT NOT NULL PRIMARY KEY,
        customer_id TEXT NOT NULL,
        tag_id TEXT NOT NULL REFERENCES customer_tags(id),
        assigned_by_user_id TEXT,
        removed_at TEXT,
        removed_by_user_id TEXT,
        operation_id TEXT UNIQUE,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS crm_automation_rules (
        id TEXT NOT NULL PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        trigger_type TEXT NOT NULL CHECK (trigger_type IN (
            'LEAD_CREATED','LEAD_IDLE','OPPORTUNITY_STAGE_CHANGED','OPPORTUNITY_IDLE',
            'OPPORTUNITY_OVERDUE','CUSTOMER_INACTIVE','CASE_CREATED','SLA_AT_RISK',
            'SLA_BREACHED','CREDIT_REVIEW_DUE')),
        action_type TEXT NOT NULL CHECK (action_type IN (
            'CREATE_TASK','ASSIGN_OWNER','SEND_NOTIFICATION','CHANGE_PRIORITY',
            'ESCALATE_CASE','ADD_TAG','ADD_TO_SEGMENT')),
        trigger_config TEXT NOT NULL DEFAULT '{}',
        action_config TEXT NOT NULL DEFAULT '{}',
        active INTEGER NOT NULL DEFAULT 1,
        created_by_user_id TEXT,
        operation_id TEXT UNIQUE,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        version INTEGER NOT NULL DEFAULT 1
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS crm_automation_executions (
        id TEXT NOT NULL PRIMARY KEY,
        rule_id TEXT NOT NULL REFERENCES crm_automation_rules(id),
        trigger_type TEXT NOT NULL,
        target_entity_type TEXT NOT NULL,
        target_entity_id TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('SUCCEEDED','FAILED','SKIPPED')),
        result_detail TEXT NOT NULL DEFAULT '',
        created_entity_id TEXT,
        operation_id TEXT,
        executed_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS crm_sync_conflicts (
        id TEXT NOT NULL PRIMARY KEY,
        related_entity_type TEXT NOT NULL CHECK (related_entity_type IN (
            'LEAD','OPPORTUNITY','TASK','CASE')),
        related_entity_id TEXT NOT NULL,
        conflict_type TEXT NOT NULL CHECK (conflict_type IN (
            'LEAD_ASSIGNMENT_CONFLICT','OPPORTUNITY_STAGE_CONFLICT',
            'TASK_STATUS_CONFLICT','CASE_ASSIGNMENT_CONFLICT')),
        local_updated_at TEXT NOT NULL,
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
    CREATE TABLE IF NOT EXISTS crm_audit_log (
        id TEXT NOT NULL PRIMARY KEY,
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
    CREATE TABLE IF NOT EXISTS crm_processed_events (
        event_id TEXT NOT NULL PRIMARY KEY,
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
    "CREATE INDEX IF NOT EXISTS idx_customer_ownerships_customer"
    " ON customer_ownerships(customer_id, ownership_type)",
    "CREATE INDEX IF NOT EXISTS idx_customer_ownerships_owner"
    " ON customer_ownerships(owner_user_id)",
    "CREATE INDEX IF NOT EXISTS idx_portfolio_assignments_customer"
    " ON portfolio_assignments(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_portfolio_assignments_portfolio"
    " ON portfolio_assignments(portfolio_id)",
    "CREATE INDEX IF NOT EXISTS idx_customer_segment_memberships_customer"
    " ON customer_segment_memberships(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_customer_segment_memberships_segment"
    " ON customer_segment_memberships(segment_id)",
    "CREATE INDEX IF NOT EXISTS idx_customer_tag_assignments_customer"
    " ON customer_tag_assignments(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_customer_tag_assignments_tag"
    " ON customer_tag_assignments(tag_id)",
    "CREATE INDEX IF NOT EXISTS idx_crm_automation_rules_trigger"
    " ON crm_automation_rules(trigger_type, active)",
    "CREATE INDEX IF NOT EXISTS idx_crm_automation_executions_rule"
    " ON crm_automation_executions(rule_id)",
    "CREATE INDEX IF NOT EXISTS idx_crm_sync_conflicts_entity"
    " ON crm_sync_conflicts(related_entity_type, related_entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_crm_sync_conflicts_status ON crm_sync_conflicts(status)",
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
