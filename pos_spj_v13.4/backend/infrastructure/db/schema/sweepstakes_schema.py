"""Sweepstakes/Sorteos bounded context — born-clean UUIDv7 schema (LOY-15,
§27-28). Mirrors backend/infrastructure/db/schema/commercial_instruments_schema.py's
conventions exactly (TEXT PRIMARY KEY UUIDv7, TEXT decimal strings for money,
no enum CHECK constraints).

Verified via grep against `migrations/m000_base_schema.py` — no collision.
Table names are prefixed `sweepstakes_` specifically to avoid collision with
the pre-existing legacy `raffle_*` tables
(`migrations/standalone/113_raffle_subsystem.py`), which stay untouched
until LOY-27's legacy-deletion phase.

Only a migration in ``migrations/`` may execute this DDL.
"""

from __future__ import annotations

SWEEPSTAKES_TABLES: tuple[str, ...] = (
    "sweepstakes_campaigns",
    "sweepstakes_rules",
    "sweepstakes_prizes",
    "sweepstakes_entries",
    "sweepstakes_tickets",
    "sweepstakes_draws",
    "sweepstakes_winners",
    "sweepstakes_outbox",
)

_DDL = (
    # ── SweepstakesCampaign ──────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS sweepstakes_campaigns (
        id TEXT PRIMARY KEY,
        code TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        ticket_price TEXT NOT NULL DEFAULT '0',
        max_tickets_per_customer INTEGER NOT NULL DEFAULT 0,
        branch_id TEXT,
        status TEXT NOT NULL DEFAULT 'DRAFT',
        starts_at TEXT,
        ends_at TEXT,
        created_by_user_id TEXT NOT NULL,
        approved_by_user_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    # ── SweepstakesRule — one per campaign ──────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS sweepstakes_rules (
        id TEXT PRIMARY KEY,
        campaign_id TEXT NOT NULL UNIQUE REFERENCES sweepstakes_campaigns(id),
        entry_method TEXT NOT NULL,
        amount_per_ticket TEXT NOT NULL DEFAULT '0',
        tickets_per_sale INTEGER NOT NULL DEFAULT 1,
        max_tickets_per_sale INTEGER NOT NULL DEFAULT 0,
        max_tickets_per_customer INTEGER NOT NULL DEFAULT 0,
        requires_registered_customer INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    )
    """,
    # ── SweepstakesPrize ─────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS sweepstakes_prizes (
        id TEXT PRIMARY KEY,
        campaign_id TEXT NOT NULL REFERENCES sweepstakes_campaigns(id),
        name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        quantity INTEGER NOT NULL DEFAULT 1,
        rank INTEGER NOT NULL DEFAULT 1,
        estimated_cost TEXT NOT NULL DEFAULT '0',
        status TEXT NOT NULL DEFAULT 'PENDING',
        created_at TEXT NOT NULL
    )
    """,
    # ── SweepstakesEntry — append-only "derecho previo" (§28) ───────────
    """
    CREATE TABLE IF NOT EXISTS sweepstakes_entries (
        id TEXT PRIMARY KEY,
        campaign_id TEXT NOT NULL REFERENCES sweepstakes_campaigns(id),
        customer_id TEXT NOT NULL,
        entry_method TEXT NOT NULL,
        chances_granted INTEGER NOT NULL DEFAULT 1,
        source_sale_id TEXT,
        notes TEXT NOT NULL DEFAULT '',
        granted_by_user_id TEXT,
        created_at TEXT NOT NULL
    )
    """,
    # ── SweepstakesTicket — always references a real prior entry (§28) ──
    """
    CREATE TABLE IF NOT EXISTS sweepstakes_tickets (
        id TEXT PRIMARY KEY,
        campaign_id TEXT NOT NULL REFERENCES sweepstakes_campaigns(id),
        entry_id TEXT NOT NULL REFERENCES sweepstakes_entries(id),
        customer_id TEXT NOT NULL,
        ticket_number TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'ISSUED',
        print_count INTEGER NOT NULL DEFAULT 0,
        first_printed_at TEXT,
        last_printed_at TEXT,
        void_reason TEXT,
        created_at TEXT NOT NULL,
        UNIQUE(campaign_id, ticket_number)
    )
    """,
    # ── SweepstakesDraw ──────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS sweepstakes_draws (
        id TEXT PRIMARY KEY,
        campaign_id TEXT NOT NULL REFERENCES sweepstakes_campaigns(id),
        status TEXT NOT NULL DEFAULT 'SCHEDULED',
        scheduled_at TEXT,
        executed_at TEXT,
        executed_by_user_id TEXT,
        random_seed TEXT,
        pool_hash TEXT,
        ticket_pool_size INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """,
    # ── SweepstakesWinner — a ticket wins at most once per draw ─────────
    """
    CREATE TABLE IF NOT EXISTS sweepstakes_winners (
        id TEXT PRIMARY KEY,
        draw_id TEXT NOT NULL REFERENCES sweepstakes_draws(id),
        campaign_id TEXT NOT NULL REFERENCES sweepstakes_campaigns(id),
        ticket_id TEXT NOT NULL REFERENCES sweepstakes_tickets(id),
        customer_id TEXT NOT NULL,
        prize_id TEXT NOT NULL REFERENCES sweepstakes_prizes(id),
        rank INTEGER NOT NULL DEFAULT 1,
        status TEXT NOT NULL DEFAULT 'PENDING_VALIDATION',
        selected_at TEXT NOT NULL,
        validated_at TEXT,
        validated_by_user_id TEXT,
        disqualification_reason TEXT,
        delivered_at TEXT,
        delivered_by_user_id TEXT,
        UNIQUE(draw_id, ticket_id)
    )
    """,
    # ── transactional outbox ─────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS sweepstakes_outbox (
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
    "CREATE INDEX IF NOT EXISTS idx_sweepstakes_campaigns_status"
    " ON sweepstakes_campaigns(status)",
    "CREATE INDEX IF NOT EXISTS idx_sweepstakes_prizes_campaign"
    " ON sweepstakes_prizes(campaign_id, rank)",
    "CREATE INDEX IF NOT EXISTS idx_sweepstakes_entries_campaign_customer"
    " ON sweepstakes_entries(campaign_id, customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_sweepstakes_entries_sale"
    " ON sweepstakes_entries(source_sale_id)",
    "CREATE INDEX IF NOT EXISTS idx_sweepstakes_tickets_entry"
    " ON sweepstakes_tickets(entry_id)",
    "CREATE INDEX IF NOT EXISTS idx_sweepstakes_tickets_campaign_status"
    " ON sweepstakes_tickets(campaign_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_sweepstakes_tickets_customer"
    " ON sweepstakes_tickets(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_sweepstakes_draws_campaign"
    " ON sweepstakes_draws(campaign_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_sweepstakes_winners_draw"
    " ON sweepstakes_winners(draw_id)",
    "CREATE INDEX IF NOT EXISTS idx_sweepstakes_winners_campaign_status"
    " ON sweepstakes_winners(campaign_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_sweepstakes_outbox_status"
    " ON sweepstakes_outbox(status)",
)


def create_sweepstakes_schema(conn) -> None:
    """Create the canonical Sweepstakes schema (idempotent)."""
    for statement in _DDL:
        conn.execute(statement)
    for index in _INDEXES:
        conn.execute(index)


def drop_sweepstakes_schema(conn) -> list[str]:
    dropped: list[str] = []
    for table in reversed(SWEEPSTAKES_TABLES):
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        dropped.append(table)
    return dropped
