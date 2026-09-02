"""Loyalty Cards bounded context — born-clean UUIDv7 schema (LOY-16,
§31-32). Mirrors backend/infrastructure/db/schema/sweepstakes_schema.py's
conventions exactly.

Verified via grep against `migrations/m000_base_schema.py` before naming —
no collision with the legacy `tarjetas_fidelidad`/`card_batches`/
`card_assignment_history`/`historico_tarjetas`/`config_diseno_tarjetas`
tables, which stay untouched until LOY-27's legacy-deletion phase.

Only a migration in ``migrations/`` may execute this DDL.
"""

from __future__ import annotations

LOYALTY_CARDS_TABLES: tuple[str, ...] = (
    "loyalty_cards",
    "loyalty_card_tokens",
    "loyalty_card_templates",
    "loyalty_card_template_versions",
    "loyalty_card_sheet_profiles",
    "loyalty_card_imposition_profiles",
    "loyalty_card_batches",
    "loyalty_card_batch_items",
    "loyalty_card_print_jobs",
    "loyalty_digital_card_projections",
    "loyalty_cards_outbox",
)

_DDL = (
    # ── LoyaltyCard ──────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS loyalty_cards (
        id TEXT PRIMARY KEY,
        card_number TEXT NOT NULL UNIQUE,
        card_type TEXT NOT NULL,
        customer_id TEXT NOT NULL,
        membership_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'ISSUED',
        issued_at TEXT NOT NULL,
        activated_at TEXT,
        blocked_at TEXT,
        block_reason TEXT,
        replaces_card_id TEXT REFERENCES loyalty_cards(id),
        replaced_by_card_id TEXT REFERENCES loyalty_cards(id),
        cancelled_at TEXT,
        cancel_reason TEXT,
        expires_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    # ── LoyaltyCardPublicToken — rotatable QR identifier (§32) ──────────
    """
    CREATE TABLE IF NOT EXISTS loyalty_card_tokens (
        id TEXT PRIMARY KEY,
        card_id TEXT NOT NULL REFERENCES loyalty_cards(id),
        token TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL DEFAULT 'ACTIVE',
        created_at TEXT NOT NULL,
        rotated_at TEXT,
        revoked_at TEXT
    )
    """,
    # ── LoyaltyCardTemplate (§33) ────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS loyalty_card_templates (
        id TEXT PRIMARY KEY,
        code TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        target_type TEXT NOT NULL DEFAULT 'PHYSICAL',
        status TEXT NOT NULL DEFAULT 'DRAFT',
        active_version_id TEXT,
        created_by_user_id TEXT NOT NULL,
        approved_by_user_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    # ── LoyaltyCardTemplateVersion — versioned design snapshot (§33-34) ──
    """
    CREATE TABLE IF NOT EXISTS loyalty_card_template_versions (
        id TEXT PRIMARY KEY,
        template_id TEXT NOT NULL REFERENCES loyalty_card_templates(id),
        version_number INTEGER NOT NULL,
        design_schema_json TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'DRAFT',
        created_by_user_id TEXT NOT NULL,
        approved_by_user_id TEXT,
        activated_at TEXT,
        created_at TEXT NOT NULL,
        UNIQUE(template_id, version_number)
    )
    """,
    # ── LoyaltyCardSheetProfile (§38-40) ─────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS loyalty_card_sheet_profiles (
        id TEXT PRIMARY KEY,
        code TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        width_mm TEXT NOT NULL,
        height_mm TEXT NOT NULL,
        orientation TEXT NOT NULL DEFAULT 'PORTRAIT',
        margin_top_mm TEXT NOT NULL DEFAULT '0',
        margin_bottom_mm TEXT NOT NULL DEFAULT '0',
        margin_left_mm TEXT NOT NULL DEFAULT '0',
        margin_right_mm TEXT NOT NULL DEFAULT '0',
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    # ── LoyaltyCardImpositionProfile — derived columns/rows (§38-40) ─────
    """
    CREATE TABLE IF NOT EXISTS loyalty_card_imposition_profiles (
        id TEXT PRIMARY KEY,
        sheet_profile_id TEXT NOT NULL REFERENCES loyalty_card_sheet_profiles(id),
        card_width_mm TEXT NOT NULL,
        card_height_mm TEXT NOT NULL,
        columns INTEGER NOT NULL,
        rows INTEGER NOT NULL,
        bleed_mm TEXT NOT NULL DEFAULT '0',
        safe_area_mm TEXT NOT NULL DEFAULT '0',
        gutter_horizontal_mm TEXT NOT NULL DEFAULT '0',
        gutter_vertical_mm TEXT NOT NULL DEFAULT '0',
        created_at TEXT NOT NULL
    )
    """,
    # ── LoyaltyCardBatch (§43-44) ────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS loyalty_card_batches (
        id TEXT PRIMARY KEY,
        template_id TEXT NOT NULL REFERENCES loyalty_card_templates(id),
        imposition_profile_id TEXT NOT NULL REFERENCES loyalty_card_imposition_profiles(id),
        item_count INTEGER NOT NULL,
        cards_per_sheet INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'DRAFT',
        created_by_user_id TEXT NOT NULL,
        approved_by_user_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    # ── LoyaltyCardBatchItem — one physical card slot within a batch ────
    """
    CREATE TABLE IF NOT EXISTS loyalty_card_batch_items (
        id TEXT PRIMARY KEY,
        batch_id TEXT NOT NULL REFERENCES loyalty_card_batches(id),
        card_id TEXT NOT NULL REFERENCES loyalty_cards(id),
        sheet_number INTEGER NOT NULL,
        position_in_sheet INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDING',
        failure_reason TEXT,
        printed_at TEXT,
        created_at TEXT NOT NULL,
        UNIQUE(batch_id, card_id)
    )
    """,
    # ── LoyaltyCardPrintJob (§50-51) — own schema, no cross-context FK ──
    """
    CREATE TABLE IF NOT EXISTS loyalty_card_print_jobs (
        id TEXT PRIMARY KEY,
        batch_id TEXT NOT NULL REFERENCES loyalty_card_batches(id),
        requested_by_user_id TEXT NOT NULL,
        only_sheet_number INTEGER,
        status TEXT NOT NULL DEFAULT 'PENDING',
        failure_reason TEXT,
        reprint_of_job_id TEXT REFERENCES loyalty_card_print_jobs(id),
        reprint_reason TEXT,
        requested_at TEXT NOT NULL,
        rendered_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    # ── LoyaltyDigitalCardProjection — one per DIGITAL card (§48) ───────
    """
    CREATE TABLE IF NOT EXISTS loyalty_digital_card_projections (
        id TEXT PRIMARY KEY,
        card_id TEXT NOT NULL UNIQUE REFERENCES loyalty_cards(id),
        customer_id TEXT NOT NULL,
        card_number TEXT NOT NULL,
        qr_token TEXT NOT NULL,
        display_fields_json TEXT NOT NULL DEFAULT '{}',
        last_refreshed_at TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    # ── transactional outbox ─────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS loyalty_cards_outbox (
        id TEXT PRIMARY KEY,
        event_id TEXT NOT NULL UNIQUE,
        event_name TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        operation_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDING',
        created_at TEXT NOT NULL,
        dispatched_at TEXT
    )
    """,
)

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_loyalty_cards_customer ON loyalty_cards(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_cards_membership ON loyalty_cards(membership_id)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_cards_status ON loyalty_cards(status)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_card_tokens_card ON loyalty_card_tokens(card_id)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_card_tokens_status ON loyalty_card_tokens(status)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_card_templates_status ON loyalty_card_templates(status)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_card_template_versions_template"
    " ON loyalty_card_template_versions(template_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_card_sheet_profiles_active"
    " ON loyalty_card_sheet_profiles(active)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_card_imposition_profiles_sheet"
    " ON loyalty_card_imposition_profiles(sheet_profile_id)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_card_batches_template ON loyalty_card_batches(template_id)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_card_batches_status ON loyalty_card_batches(status)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_card_batch_items_batch"
    " ON loyalty_card_batch_items(batch_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_card_print_jobs_batch"
    " ON loyalty_card_print_jobs(batch_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_digital_card_projections_customer"
    " ON loyalty_digital_card_projections(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_cards_outbox_status ON loyalty_cards_outbox(status)",
)


def create_loyalty_cards_schema(conn) -> None:
    """Create the canonical Loyalty Cards schema (idempotent)."""
    for statement in _DDL:
        conn.execute(statement)
    for index in _INDEXES:
        conn.execute(index)


def drop_loyalty_cards_schema(conn) -> list[str]:
    dropped: list[str] = []
    for table in reversed(LOYALTY_CARDS_TABLES):
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        dropped.append(table)
    return dropped
