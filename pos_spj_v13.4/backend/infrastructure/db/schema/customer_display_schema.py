"""Customer Display schema — SET-17.

DDL lives only here; only migration 217 may call
`create_customer_display_schema`. Backs `backend/domain/customer_display/`
(SET-17): `customer_displays` mirrors `CustomerDisplay`, `display_layouts`
mirrors `DisplayLayout`.

`customer_displays.workstation_id` FKs to `workstations(id)` (Settings,
migration 210) — this schema deliberately depends on Settings' schema,
not the reverse, the same dependency direction Device Management (SET-7)
and Document Output (SET-11) already established relative to Settings.
"""

from __future__ import annotations

_UUID_CHECK = "length({0})=36 AND lower({0})={0} AND substr({0},15,1)='7'"


def _uuid(column: str) -> str:
    return _UUID_CHECK.format(column)


_CUSTOMER_DISPLAY_MODES = "'IDLE','CART','PAYMENT_PENDING','THANK_YOU'"

_CUSTOMER_DISPLAYS_DDL = f"""
    CREATE TABLE IF NOT EXISTS customer_displays (
        id              TEXT PRIMARY KEY CHECK({_uuid('id')}),
        workstation_id  TEXT NOT NULL REFERENCES workstations(id) CHECK({_uuid('workstation_id')}),
        name            TEXT NOT NULL CHECK(trim(name)<>''),
        current_mode    TEXT NOT NULL CHECK(current_mode IN ({_CUSTOMER_DISPLAY_MODES})),
        active          INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        created_at      TEXT NOT NULL,
        updated_at      TEXT NOT NULL
    )
"""

_DISPLAY_LAYOUTS_DDL = f"""
    CREATE TABLE IF NOT EXISTS display_layouts (
        id             TEXT PRIMARY KEY CHECK({_uuid('id')}),
        mode           TEXT NOT NULL CHECK(mode IN ({_CUSTOMER_DISPLAY_MODES})),
        sections_json  TEXT NOT NULL DEFAULT '[]',
        active         INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        created_at     TEXT NOT NULL,
        updated_at     TEXT NOT NULL
    )
"""

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_customer_displays_workstation ON customer_displays(workstation_id)",
    "CREATE INDEX IF NOT EXISTS idx_customer_displays_active ON customer_displays(active)",
    "CREATE INDEX IF NOT EXISTS idx_display_layouts_mode ON display_layouts(mode)",
    # At most one ACTIVE layout per mode — the constraint that actually
    # prevents "two active layouts at once" for the same mode, not just
    # a plain index on mode.
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_display_layouts_mode_active "
    "ON display_layouts(mode) WHERE active=1",
)


def create_customer_display_schema(conn) -> None:
    conn.execute(_CUSTOMER_DISPLAYS_DDL)
    conn.execute(_DISPLAY_LAYOUTS_DDL)
    for statement in _INDEXES:
        conn.execute(statement)


_CONTENT_TYPES = "'IMAGE','VIDEO','TEXT','HTML'"
_CONTENT_CAMPAIGN_STATUSES = (
    "'DRAFT','PENDING_APPROVAL','APPROVED','ACTIVE','INACTIVE','EXPIRED','ARCHIVED'"
)

_DISPLAY_CONTENT_DDL = f"""
    CREATE TABLE IF NOT EXISTS display_content (
        id                 TEXT PRIMARY KEY CHECK({_uuid('id')}),
        title              TEXT NOT NULL CHECK(trim(title)<>''),
        content_type       TEXT NOT NULL CHECK(content_type IN ({_CONTENT_TYPES})),
        body               TEXT NOT NULL CHECK(trim(body)<>''),
        duration_seconds   INTEGER NOT NULL DEFAULT 10 CHECK(duration_seconds > 0),
        active             INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        created_at         TEXT NOT NULL,
        updated_at         TEXT NOT NULL
    )
"""

_CONTENT_CAMPAIGNS_DDL = f"""
    CREATE TABLE IF NOT EXISTS content_campaigns (
        id                     TEXT PRIMARY KEY CHECK({_uuid('id')}),
        name                   TEXT NOT NULL CHECK(trim(name)<>''),
        content_id             TEXT NOT NULL REFERENCES display_content(id) CHECK({_uuid('content_id')}),
        status                 TEXT NOT NULL CHECK(status IN ({_CONTENT_CAMPAIGN_STATUSES})),
        starts_at              TEXT,
        ends_at                TEXT,
        created_by_user_id     TEXT,
        approved_by_user_id    TEXT,
        activated_by_user_id   TEXT,
        reason                 TEXT,
        created_at             TEXT NOT NULL,
        updated_at             TEXT NOT NULL
    )
"""

_ADVERTISING_SLOTS_DDL = f"""
    CREATE TABLE IF NOT EXISTS advertising_slots (
        id             TEXT PRIMARY KEY CHECK({_uuid('id')}),
        code           TEXT NOT NULL UNIQUE CHECK(trim(code)<>''),
        mode           TEXT NOT NULL CHECK(mode IN ({_CUSTOMER_DISPLAY_MODES})),
        display_order  INTEGER NOT NULL DEFAULT 0 CHECK(display_order >= 0),
        active         INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        created_at     TEXT NOT NULL,
        updated_at     TEXT NOT NULL
    )
"""

_CAMPAIGN_PLACEMENTS_DDL = f"""
    CREATE TABLE IF NOT EXISTS campaign_placements (
        id                    TEXT PRIMARY KEY CHECK({_uuid('id')}),
        campaign_id           TEXT NOT NULL REFERENCES content_campaigns(id) CHECK({_uuid('campaign_id')}),
        slot_id               TEXT NOT NULL REFERENCES advertising_slots(id) CHECK({_uuid('slot_id')}),
        active                INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        assigned_by_user_id   TEXT,
        assigned_at           TEXT NOT NULL,
        unassigned_at         TEXT
    )
"""

_CONTENT_IMPRESSIONS_DDL = f"""
    CREATE TABLE IF NOT EXISTS content_impressions (
        id                       TEXT PRIMARY KEY CHECK({_uuid('id')}),
        placement_id             TEXT NOT NULL REFERENCES campaign_placements(id) CHECK({_uuid('placement_id')}),
        duration_shown_seconds   INTEGER NOT NULL CHECK(duration_shown_seconds >= 0),
        displayed_at             TEXT NOT NULL
    )
"""

_CONTENT_AND_PLACEMENT_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_display_content_active ON display_content(active)",
    "CREATE INDEX IF NOT EXISTS idx_content_campaigns_content ON content_campaigns(content_id)",
    "CREATE INDEX IF NOT EXISTS idx_content_campaigns_status ON content_campaigns(status)",
    "CREATE INDEX IF NOT EXISTS idx_advertising_slots_mode ON advertising_slots(mode)",
    "CREATE INDEX IF NOT EXISTS idx_campaign_placements_campaign ON campaign_placements(campaign_id)",
    # §"Placements": at most one ACTIVE placement per slot — the same
    # partial-unique-index discipline
    # `ux_wda_workstation_role_active` (device_management, SET-7) and
    # `ux_dtv_template_active` (document_output, SET-11) already
    # established.
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_campaign_placements_slot_active "
    "ON campaign_placements(slot_id) WHERE active=1",
    "CREATE INDEX IF NOT EXISTS idx_content_impressions_placement ON content_impressions(placement_id)",
)


def create_content_and_advertising_schema(conn) -> None:
    """SET-18 (Contenido y publicidad) — separate migration (218) from
    217, same reasoning as every prior split: a shipped migration's body
    must not change."""
    conn.execute(_DISPLAY_CONTENT_DDL)
    conn.execute(_CONTENT_CAMPAIGNS_DDL)
    conn.execute(_ADVERTISING_SLOTS_DDL)
    conn.execute(_CAMPAIGN_PLACEMENTS_DDL)
    conn.execute(_CONTENT_IMPRESSIONS_DDL)
    for statement in _CONTENT_AND_PLACEMENT_INDEXES:
        conn.execute(statement)
