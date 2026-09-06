"""Document Output schema — SET-11.

DDL lives only here; only migration 214 may call
`create_document_output_schema`. Backs `backend/domain/document_output/`
(SET-11): `document_templates` mirrors `DocumentTemplate`,
`document_template_versions` mirrors `DocumentTemplateVersion`,
`print_jobs` mirrors `PrintJob`.

`print_jobs.printer_device_id` FKs to `devices(id)` (migration 211) and
`print_jobs.print_route_id` FKs to `print_routes(id)` (migration 212) —
this schema deliberately depends on Device Management's schema, not the
reverse, matching migration order (211-213 before 214). Both FKs are
nullable: a job is created before routing is decided (§24 — assign_route()
happens after create()).
"""

from __future__ import annotations

_UUID_CHECK = "length({0})=36 AND lower({0})={0} AND substr({0},15,1)='7'"


def _uuid(column: str) -> str:
    return _UUID_CHECK.format(column)


_TEMPLATE_VERSION_STATUSES = (
    "'DRAFT','PENDING_APPROVAL','APPROVED','ACTIVE','INACTIVE','EXPIRED','ARCHIVED'"
)

_RENDER_FORMATS = "'ESC_POS','HTML','PDF','ZPL','VIRTUAL'"

_PRINT_JOB_STATUSES = (
    "'PENDING','RENDERING','READY','PRINTING','PRINTED','FAILED','CANCELLED','DEAD_LETTER'"
)

_PRINT_JOB_PRIORITIES = "'LOW','NORMAL','HIGH','URGENT'"

_DOCUMENT_TEMPLATES_DDL = f"""
    CREATE TABLE IF NOT EXISTS document_templates (
        id             TEXT NOT NULL PRIMARY KEY CHECK({_uuid('id')}),
        document_type  TEXT NOT NULL CHECK(trim(document_type)<>''),
        name           TEXT NOT NULL CHECK(trim(name)<>''),
        module         TEXT NOT NULL CHECK(trim(module)<>''),
        description    TEXT NOT NULL DEFAULT '',
        active         INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        created_at     TEXT NOT NULL,
        updated_at     TEXT NOT NULL
    )
"""

_DOCUMENT_TEMPLATE_VERSIONS_DDL = f"""
    CREATE TABLE IF NOT EXISTS document_template_versions (
        id                     TEXT NOT NULL PRIMARY KEY CHECK({_uuid('id')}),
        template_id            TEXT NOT NULL REFERENCES document_templates(id) CHECK({_uuid('template_id')}),
        version                INTEGER NOT NULL CHECK(version >= 1),
        content_format         TEXT NOT NULL CHECK(content_format IN ({_RENDER_FORMATS})),
        content                TEXT NOT NULL CHECK(trim(content)<>''),
        status                 TEXT NOT NULL CHECK(status IN ({_TEMPLATE_VERSION_STATUSES})),
        created_by_user_id     TEXT,
        approved_by_user_id    TEXT,
        activated_by_user_id   TEXT,
        reason                 TEXT,
        previous_version_id    TEXT REFERENCES document_template_versions(id)
                                    CHECK(previous_version_id IS NULL OR ({_uuid('previous_version_id')})),
        created_at             TEXT NOT NULL,
        updated_at             TEXT NOT NULL,
        UNIQUE(template_id, version)
    )
"""

_PRINT_JOBS_DDL = f"""
    CREATE TABLE IF NOT EXISTS print_jobs (
        id                     TEXT NOT NULL PRIMARY KEY CHECK({_uuid('id')}),
        document_type          TEXT NOT NULL CHECK(trim(document_type)<>''),
        source_module          TEXT NOT NULL CHECK(trim(source_module)<>''),
        source_document_id     TEXT NOT NULL CHECK({_uuid('source_document_id')}),
        template_version_id    TEXT NOT NULL REFERENCES document_template_versions(id)
                                    CHECK({_uuid('template_version_id')}),
        requested_by_user_id   TEXT NOT NULL,
        copies                 INTEGER NOT NULL DEFAULT 1 CHECK(copies >= 1),
        priority                TEXT NOT NULL DEFAULT 'NORMAL' CHECK(priority IN ({_PRINT_JOB_PRIORITIES})),
        print_route_id         TEXT REFERENCES print_routes(id)
                                    CHECK(print_route_id IS NULL OR ({_uuid('print_route_id')})),
        printer_device_id      TEXT REFERENCES devices(id)
                                    CHECK(printer_device_id IS NULL OR ({_uuid('printer_device_id')})),
        status                 TEXT NOT NULL CHECK(status IN ({_PRINT_JOB_STATUSES})),
        requested_at           TEXT NOT NULL,
        rendered_at            TEXT,
        printed_at             TEXT,
        failure_reason         TEXT,
        retry_count            INTEGER NOT NULL DEFAULT 0 CHECK(retry_count >= 0),
        reprint_of_job_id      TEXT REFERENCES print_jobs(id)
                                    CHECK(reprint_of_job_id IS NULL OR ({_uuid('reprint_of_job_id')})),
        reprint_reason         TEXT,
        operation_id           TEXT,
        created_at             TEXT NOT NULL,
        updated_at             TEXT NOT NULL
    )
"""

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_document_templates_document_type ON document_templates(document_type)",
    "CREATE INDEX IF NOT EXISTS idx_document_templates_active ON document_templates(active)",
    "CREATE INDEX IF NOT EXISTS idx_dtv_template ON document_template_versions(template_id)",
    "CREATE INDEX IF NOT EXISTS idx_dtv_status ON document_template_versions(status)",
    # §26: at most one ACTIVE version per template — this is the
    # constraint that actually prevents "two active versions at once",
    # not the plain UNIQUE(template_id, version) above (which only stops
    # the exact same version number from duplicating).
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_dtv_template_active "
    "ON document_template_versions(template_id) WHERE status='ACTIVE'",
    "CREATE INDEX IF NOT EXISTS idx_print_jobs_status ON print_jobs(status)",
    "CREATE INDEX IF NOT EXISTS idx_print_jobs_source ON print_jobs(source_module, source_document_id)",
    "CREATE INDEX IF NOT EXISTS idx_print_jobs_requested_at ON print_jobs(requested_at)",
    # Idempotent writes: a given operation_id may only ever produce one job.
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_print_jobs_operation_id "
    "ON print_jobs(operation_id) WHERE operation_id IS NOT NULL",
)


def create_document_output_schema(conn) -> None:
    conn.execute(_DOCUMENT_TEMPLATES_DDL)
    conn.execute(_DOCUMENT_TEMPLATE_VERSIONS_DDL)
    conn.execute(_PRINT_JOBS_DDL)
    for statement in _INDEXES:
        conn.execute(statement)


_MARKETING_MESSAGE_CATEGORIES = "'LOYALTY','FOMO','CTA'"

_MARKETING_CAMPAIGNS_DDL = f"""
    CREATE TABLE IF NOT EXISTS marketing_campaigns (
        id                  TEXT NOT NULL PRIMARY KEY CHECK({_uuid('id')}),
        code                TEXT NOT NULL UNIQUE CHECK(trim(code)<>''),
        category            TEXT NOT NULL CHECK(category IN ({_MARKETING_MESSAGE_CATEGORIES})),
        message_template    TEXT NOT NULL CHECK(trim(message_template)<>''),
        priority            INTEGER NOT NULL DEFAULT 0,
        requires_customer   INTEGER NOT NULL DEFAULT 0 CHECK(requires_customer IN (0,1)),
        rules_json          TEXT NOT NULL DEFAULT '[]',
        active              INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        created_at          TEXT NOT NULL,
        updated_at          TEXT NOT NULL
    )
"""

_MARKETING_CAMPAIGNS_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_marketing_campaigns_category ON marketing_campaigns(category)",
    "CREATE INDEX IF NOT EXISTS idx_marketing_campaigns_active ON marketing_campaigns(active)",
)


def create_marketing_campaigns_schema(conn) -> None:
    """SET-13 (Marketing en tickets) — separate migration (215) from
    208-214, same reasoning as every prior split: a shipped migration's
    body must not change."""
    conn.execute(_MARKETING_CAMPAIGNS_DDL)
    for statement in _MARKETING_CAMPAIGNS_INDEXES:
        conn.execute(statement)


_SEQUENCE_RESET_POLICIES = "'NEVER','YEARLY','MONTHLY','DAILY'"

_DOCUMENT_NUMBER_SEQUENCES_DDL = f"""
    CREATE TABLE IF NOT EXISTS document_number_sequences (
        id              TEXT NOT NULL PRIMARY KEY CHECK({_uuid('id')}),
        prefix          TEXT NOT NULL UNIQUE CHECK(trim(prefix)<>''),
        reset_policy    TEXT NOT NULL CHECK(reset_policy IN ({_SEQUENCE_RESET_POLICIES})),
        period_key      TEXT NOT NULL DEFAULT '',
        current_value   INTEGER NOT NULL DEFAULT 0 CHECK(current_value >= 0),
        created_at      TEXT NOT NULL,
        updated_at      TEXT NOT NULL
    )
"""

_DOCUMENT_NUMBER_RESERVATIONS_DDL = f"""
    CREATE TABLE IF NOT EXISTS document_number_reservations (
        id                TEXT NOT NULL PRIMARY KEY CHECK({_uuid('id')}),
        sequence_id       TEXT NOT NULL REFERENCES document_number_sequences(id) CHECK({_uuid('sequence_id')}),
        operation_id      TEXT NOT NULL,
        prefix            TEXT NOT NULL,
        period_key        TEXT NOT NULL,
        sequence_value    INTEGER NOT NULL CHECK(sequence_value >= 1),
        document_number   TEXT NOT NULL,
        reserved_at       TEXT NOT NULL,
        UNIQUE(sequence_id, operation_id)
    )
"""

_DOCUMENT_NUMBERING_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_document_number_reservations_sequence "
    "ON document_number_reservations(sequence_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_document_number_reservations_document_number "
    "ON document_number_reservations(document_number)",
)


def create_document_numbering_schema(conn) -> None:
    """SET-16 (Numeración) — separate migration (216) from 208-215, same
    reasoning as every prior split: a shipped migration's body must not
    change."""
    conn.execute(_DOCUMENT_NUMBER_SEQUENCES_DDL)
    conn.execute(_DOCUMENT_NUMBER_RESERVATIONS_DDL)
    for statement in _DOCUMENT_NUMBERING_INDEXES:
        conn.execute(statement)
