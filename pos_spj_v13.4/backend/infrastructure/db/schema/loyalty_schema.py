"""Fidelidad/Loyalty bounded context — born-clean UUIDv7 schema (LOY-3).
Mirrors backend/infrastructure/db/schema/sales_schema.py's conventions
exactly.

Rules (REGLA CERO / §8 / §32-42):
- Every id is ``TEXT PRIMARY KEY`` holding a lowercase UUIDv7 (PostgreSQL: UUID).
- ``points_amount`` is a ``TEXT`` decimal string (PostgreSQL: NUMERIC); no
  REAL — floats are forbidden. Conversion to/from ``Decimal`` happens in the
  repository layer (a future phase, not built yet), never in SQL.
- Structural idempotency (§12): ``UNIQUE(operation_id)`` on
  ``loyalty_transactions``, plus ``UNIQUE(source_module, source_document_id,
  transaction_type, reason_code)`` to block double accrual/redemption for
  the same source document — both enforced as real SQL constraints, not
  merely application-layer checks.
- Status/enum values are NOT enforced via SQL CHECK — the domain layer
  (``backend/domain/loyalty/enums.py`` + entities) is the single source of
  truth for valid transitions, matching this repo's established convention
  (confirmed: sales_schema.py/inventory_schema.py have zero enum CHECK
  constraints either).

Canonical English names (``loyalty_program_definitions``, ``loyalty_accounts``,
``loyalty_memberships``, ``loyalty_transactions``) do NOT collide with the
legacy operational tables this bounded context does not touch or replace
yet (``loyalty_ledger``, ``loyalty_pasivo_log``, ``tarjetas_fidelidad`` —
see ``docs/refactor/LOY-0_auditoria.md``). Loyalty Cards
(``backend/infrastructure/db/schema/loyalty_cards_schema.py``) is a separate
bounded context with its own schema module, built in a later phase.

**Real naming collision found and fixed while building this schema, not
anticipated by the LOY-0 audit**: ``migrations/m000_base_schema.py::
_create_loyalty`` ALREADY creates a legacy ``loyalty_programs`` table
(Spanish columns — ``nombre``/``activo``/``puntos_por_peso``, REAL floats,
hardcoded ``nivel_bronce``/``nivel_plata``/``nivel_oro``/``nivel_platino``
thresholds — exactly the Growth Engine anti-pattern this whole
transformation exists to replace, per LOY-27's eventual target). A first
draft of this schema used the plain, obvious name ``loyalty_programs`` and
it silently no-opped against the pre-existing legacy table via ``CREATE
TABLE IF NOT EXISTS`` (proven by bootstrapping a real fresh DB, not
assumed) — then ``CREATE INDEX ... loyalty_programs(status)`` failed with
``no such column: status`` since the REAL (legacy) table has no such
column. Renamed to ``loyalty_program_definitions`` to avoid the collision,
following the same disambiguation principle SALES-4 already established
for ``sale_payments`` vs. legacy ``payments`` — a real, distinguishing word,
never a ``_v2``/``_new`` suffix. ``loyalty_accounts``/``loyalty_memberships``/
``loyalty_transactions`` do NOT collide with anything (confirmed via
repo-wide grep before naming them, not assumed this time).

Only a migration in ``migrations/`` may execute this DDL.
"""

from __future__ import annotations

LOYALTY_TABLES: tuple[str, ...] = (
    "loyalty_program_definitions",
    "loyalty_accounts",
    "loyalty_memberships",
    "loyalty_transactions",
    "loyalty_tiers",
    "loyalty_tier_history",
    "loyalty_rewards",
    "loyalty_reward_redemptions",
    "loyalty_challenge_definitions",
    "loyalty_challenge_member_progress",
    "loyalty_streaks",
    "loyalty_badges",
    "loyalty_referrals",
    "loyalty_campaigns",
    "loyalty_birthday_configs",
    "loyalty_fraud_cases",
    "loyalty_outbox",
)

_DDL = (
    # ── LoyaltyProgram (backend/domain/loyalty/entities/loyalty_program.py) ─
    # Named "loyalty_program_definitions", NOT "loyalty_programs" — that
    # name is already taken by the legacy Growth Engine table
    # (migrations/m000_base_schema.py::_create_loyalty), see module docstring.
    """
    CREATE TABLE IF NOT EXISTS loyalty_program_definitions (
        id TEXT PRIMARY KEY,
        code TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        currency_name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        currency_symbol TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'DRAFT',   -- DRAFT | PENDING_APPROVAL | ACTIVE | SUSPENDED | CLOSED | ARCHIVED
        enrollment_mode TEXT NOT NULL DEFAULT 'OPEN',
        earning_enabled INTEGER NOT NULL DEFAULT 1,
        redemption_enabled INTEGER NOT NULL DEFAULT 1,
        tiering_enabled INTEGER NOT NULL DEFAULT 0,
        expiration_enabled INTEGER NOT NULL DEFAULT 0,
        branch_scope TEXT,
        channel_scope TEXT,
        effective_from TEXT,
        effective_to TEXT,
        created_by_user_id TEXT,
        approved_by_user_id TEXT,
        approved_at TEXT,
        activated_at TEXT,
        suspended_at TEXT,
        closed_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    # ── LoyaltyAccount (backend/domain/loyalty/entities/loyalty_account.py) ─
    # customer_id references the Customer Master's `customers` table
    # logically, not via a SQL FK — Loyalty never owns/duplicates customer
    # identity (master prompt §4/§52), and the two bounded contexts must
    # stay independently deployable.
    """
    CREATE TABLE IF NOT EXISTS loyalty_accounts (
        id TEXT PRIMARY KEY,
        customer_id TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL DEFAULT 'ACTIVE',   -- ACTIVE | SUSPENDED | CLOSED
        suspended_at TEXT,
        closed_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    # ── LoyaltyMembership (backend/domain/loyalty/entities/loyalty_membership.py) ─
    """
    CREATE TABLE IF NOT EXISTS loyalty_memberships (
        id TEXT PRIMARY KEY,
        loyalty_account_id TEXT NOT NULL REFERENCES loyalty_accounts(id),
        program_id TEXT NOT NULL REFERENCES loyalty_program_definitions(id),
        current_tier_id TEXT,
        status TEXT NOT NULL DEFAULT 'ACTIVE',   -- ACTIVE | SUSPENDED | BLOCKED | CLOSED
        enrolled_at TEXT NOT NULL,
        suspended_at TEXT,
        closed_at TEXT,
        updated_at TEXT NOT NULL,
        UNIQUE(loyalty_account_id, program_id)
    )
    """,
    # ── LoyaltyTransaction ledger (backend/domain/loyalty/entities/loyalty_transaction.py) ─
    # §12 idempotency: UNIQUE(operation_id) blocks any duplicate ledger
    # write outright; the second UNIQUE blocks re-accruing/re-redeeming for
    # the exact same source document + reason (allows NULLs to repeat since
    # SQLite treats NULL as distinct in a UNIQUE index, matching source rows
    # that legitimately have no source_document_id, e.g. manual adjustments).
    """
    CREATE TABLE IF NOT EXISTS loyalty_transactions (
        id TEXT PRIMARY KEY,
        loyalty_account_id TEXT NOT NULL REFERENCES loyalty_accounts(id),
        membership_id TEXT REFERENCES loyalty_memberships(id),
        transaction_type TEXT NOT NULL,   -- EARN | BONUS | REDEEM | RESERVE | RELEASE | EXPIRE | ADJUSTMENT | REVERSAL | TRANSFER_IN | TRANSFER_OUT
        points_amount TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'AVAILABLE',   -- PENDING | AVAILABLE | RESERVED | CONSUMED | EXPIRED | REVERSED | CANCELLED
        operation_id TEXT NOT NULL UNIQUE,
        source_module TEXT NOT NULL DEFAULT '',
        source_document_type TEXT,
        source_document_id TEXT,
        sale_id TEXT,
        branch_id TEXT,
        reversal_transaction_id TEXT REFERENCES loyalty_transactions(id),
        reason_code TEXT,
        notes TEXT NOT NULL DEFAULT '',
        created_by_user_id TEXT,
        available_at TEXT,
        expires_at TEXT,
        created_at TEXT NOT NULL,
        UNIQUE(source_module, source_document_id, transaction_type, reason_code)
    )
    """,
    # ── LoyaltyTier (backend/domain/loyalty/entities/loyalty_tier.py, LOY-7 §14) ─
    """
    CREATE TABLE IF NOT EXISTS loyalty_tiers (
        id TEXT PRIMARY KEY,
        program_id TEXT NOT NULL REFERENCES loyalty_program_definitions(id),
        code TEXT NOT NULL,
        name TEXT NOT NULL,
        rank INTEGER NOT NULL,
        minimum_points TEXT NOT NULL DEFAULT '0',
        minimum_spend TEXT NOT NULL DEFAULT '0',
        minimum_visits INTEGER NOT NULL DEFAULT 0,
        evaluation_method TEXT NOT NULL DEFAULT 'LIFETIME',
        evaluation_window_days INTEGER,
        benefit_multiplier TEXT NOT NULL DEFAULT '1',
        effective_from TEXT,
        effective_to TEXT,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(program_id, code),
        UNIQUE(program_id, rank)
    )
    """,
    # ── LoyaltyTierHistory (backend/domain/loyalty/entities/loyalty_tier_history.py) ─
    # Append-only — no UPDATE path anywhere in the repository layer (LOY-7).
    """
    CREATE TABLE IF NOT EXISTS loyalty_tier_history (
        id TEXT PRIMARY KEY,
        membership_id TEXT NOT NULL REFERENCES loyalty_memberships(id),
        previous_tier_id TEXT REFERENCES loyalty_tiers(id),
        new_tier_id TEXT REFERENCES loyalty_tiers(id),
        reason TEXT NOT NULL,
        evaluated_at TEXT NOT NULL
    )
    """,
    # ── Reward (backend/domain/loyalty/entities/reward.py, LOY-8 §15) ──────
    """
    CREATE TABLE IF NOT EXISTS loyalty_rewards (
        id TEXT PRIMARY KEY,
        program_id TEXT NOT NULL REFERENCES loyalty_program_definitions(id),
        code TEXT NOT NULL,
        name TEXT NOT NULL,
        reward_type TEXT NOT NULL,
        points_cost TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        value TEXT NOT NULL DEFAULT '0',
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(program_id, code)
    )
    """,
    # ── RewardRedemption (backend/domain/loyalty/entities/reward_redemption.py) ─
    """
    CREATE TABLE IF NOT EXISTS loyalty_reward_redemptions (
        id TEXT PRIMARY KEY,
        reward_id TEXT NOT NULL REFERENCES loyalty_rewards(id),
        membership_id TEXT NOT NULL REFERENCES loyalty_memberships(id),
        loyalty_account_id TEXT NOT NULL REFERENCES loyalty_accounts(id),
        points_transaction_id TEXT NOT NULL REFERENCES loyalty_transactions(id),
        status TEXT NOT NULL DEFAULT 'RESERVED',
        sale_id TEXT,
        requested_at TEXT NOT NULL,
        confirmed_at TEXT,
        cancelled_at TEXT,
        UNIQUE(points_transaction_id)
    )
    """,
    # ── LoyaltyChallenge (backend/domain/loyalty/entities/loyalty_challenge.py,
    #    LOY-9 §16). Named "loyalty_challenge_definitions", NOT
    #    "loyalty_challenges" — that name (and "loyalty_challenge_progress"
    #    below) is already taken by the legacy Growth Engine tables
    #    (migrations/m000_base_schema.py::_create_loyalty), same collision
    #    class LOY-3 already found and fixed for "loyalty_programs". ────────
    """
    CREATE TABLE IF NOT EXISTS loyalty_challenge_definitions (
        id TEXT PRIMARY KEY,
        program_id TEXT NOT NULL REFERENCES loyalty_program_definitions(id),
        code TEXT NOT NULL,
        name TEXT NOT NULL,
        criteria_type TEXT NOT NULL,
        target_value TEXT NOT NULL,
        points_reward TEXT NOT NULL,
        mode TEXT NOT NULL DEFAULT 'CHALLENGE',
        description TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'DRAFT',
        start_date TEXT,
        end_date TEXT,
        branch_scope TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(program_id, code)
    )
    """,
    # ── ChallengeProgress (backend/domain/loyalty/entities/challenge_progress.py) ─
    """
    CREATE TABLE IF NOT EXISTS loyalty_challenge_member_progress (
        id TEXT PRIMARY KEY,
        challenge_id TEXT NOT NULL REFERENCES loyalty_challenge_definitions(id),
        membership_id TEXT NOT NULL REFERENCES loyalty_memberships(id),
        current_value TEXT NOT NULL DEFAULT '0',
        completed INTEGER NOT NULL DEFAULT 0,
        completed_at TEXT,
        points_awarded TEXT NOT NULL DEFAULT '0',
        updated_at TEXT NOT NULL,
        UNIQUE(challenge_id, membership_id)
    )
    """,
    # ── LoyaltyStreak (backend/domain/loyalty/entities/loyalty_streak.py) ──
    """
    CREATE TABLE IF NOT EXISTS loyalty_streaks (
        id TEXT PRIMARY KEY,
        membership_id TEXT NOT NULL REFERENCES loyalty_memberships(id),
        streak_type TEXT NOT NULL,
        current_count INTEGER NOT NULL DEFAULT 0,
        longest_count INTEGER NOT NULL DEFAULT 0,
        last_period TEXT,
        updated_at TEXT NOT NULL,
        UNIQUE(membership_id, streak_type)
    )
    """,
    # ── LoyaltyBadge (backend/domain/loyalty/entities/loyalty_badge.py) ────
    # Append-only — no UPDATE path in the repository layer.
    """
    CREATE TABLE IF NOT EXISTS loyalty_badges (
        id TEXT PRIMARY KEY,
        membership_id TEXT NOT NULL REFERENCES loyalty_memberships(id),
        badge_code TEXT NOT NULL,
        source_challenge_id TEXT REFERENCES loyalty_challenge_definitions(id),
        earned_at TEXT NOT NULL
    )
    """,
    # ── Referral (backend/domain/loyalty/entities/referral.py, LOY-10 §17) ─
    # "loyalty_referrals", NOT "referidos" — that legacy Spanish table
    # (migrations/m000_base_schema.py) has INTEGER cliente_referidor/
    # cliente_referido columns (LOY-0's own finding); no collision either
    # way (different names), but flagged here for context.
    """
    CREATE TABLE IF NOT EXISTS loyalty_referrals (
        id TEXT PRIMARY KEY,
        program_id TEXT NOT NULL REFERENCES loyalty_program_definitions(id),
        referrer_membership_id TEXT NOT NULL REFERENCES loyalty_memberships(id),
        referred_customer_id TEXT NOT NULL,
        referrer_bonus_points TEXT NOT NULL,
        referred_bonus_points TEXT NOT NULL DEFAULT '0',
        minimum_purchase_amount TEXT NOT NULL DEFAULT '0',
        status TEXT NOT NULL DEFAULT 'REGISTERED',
        registered_at TEXT NOT NULL,
        qualified_at TEXT,
        rewarded_at TEXT,
        closed_at TEXT,
        closed_reason TEXT,
        expires_at TEXT
    )
    """,
    # ── Campaign (backend/domain/loyalty/entities/campaign.py, LOY-11 §19) ─
    # Distinct from the unrelated `marketing_campaigns` table (Settings/
    # Document Output, migration 215 — ticket-based FOMO promos, a
    # different bounded context) and from legacy `campanas` (does not
    # exist in this repo, confirmed via grep). ──────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS loyalty_campaigns (
        id TEXT PRIMARY KEY,
        program_id TEXT NOT NULL REFERENCES loyalty_program_definitions(id),
        code TEXT NOT NULL,
        name TEXT NOT NULL,
        campaign_type TEXT NOT NULL,
        created_by_user_id TEXT NOT NULL,
        audience_definition TEXT NOT NULL DEFAULT '',
        start_at TEXT,
        end_at TEXT,
        budget_limit TEXT,
        benefit_type TEXT NOT NULL DEFAULT '',
        benefit_reference_id TEXT,
        branch_scope TEXT,
        channel_scope TEXT,
        frequency_cap INTEGER,
        customer_cap INTEGER,
        status TEXT NOT NULL DEFAULT 'DRAFT',
        approved_by_user_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(program_id, code)
    )
    """,
    # ── BirthdayBenefitConfig (LOY-14 §18) ─────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS loyalty_birthday_configs (
        id TEXT PRIMARY KEY,
        program_id TEXT NOT NULL UNIQUE REFERENCES loyalty_program_definitions(id),
        enabled INTEGER NOT NULL DEFAULT 1,
        benefit_type TEXT NOT NULL DEFAULT 'NONE',
        points_amount TEXT NOT NULL DEFAULT '0',
        coupon_definition_id TEXT,
        voucher_definition_id TEXT,
        reward_id TEXT,
        days_before INTEGER NOT NULL DEFAULT 0,
        days_after INTEGER NOT NULL DEFAULT 0,
        notification_channel TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    # ── FraudCase (§29, LOY-26) ──────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS loyalty_fraud_cases (
        id TEXT PRIMARY KEY,
        subject_type TEXT NOT NULL,
        subject_id TEXT NOT NULL,
        customer_id TEXT NOT NULL,
        reason TEXT NOT NULL,
        opened_by_user_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'OPEN',
        reviewed_by_user_id TEXT,
        resolution_notes TEXT,
        opened_at TEXT NOT NULL,
        resolved_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    # ── transactional outbox (§39-equivalent for Loyalty; LOY-2's events.py) ─
    """
    CREATE TABLE IF NOT EXISTS loyalty_outbox (
        id TEXT PRIMARY KEY,
        event_id TEXT NOT NULL UNIQUE,
        event_name TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        operation_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDING',   -- PENDING | DISPATCHED | DEAD_LETTER
        created_at TEXT NOT NULL,
        dispatched_at TEXT
    )
    """,
)

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_loyalty_program_definitions_status"
    " ON loyalty_program_definitions(status)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_accounts_status ON loyalty_accounts(status)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_memberships_account"
    " ON loyalty_memberships(loyalty_account_id)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_memberships_program"
    " ON loyalty_memberships(program_id)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_transactions_account"
    " ON loyalty_transactions(loyalty_account_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_transactions_membership"
    " ON loyalty_transactions(membership_id)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_transactions_sale"
    " ON loyalty_transactions(sale_id)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_transactions_branch"
    " ON loyalty_transactions(branch_id)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_transactions_expires"
    " ON loyalty_transactions(expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_tiers_program"
    " ON loyalty_tiers(program_id, active)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_tier_history_membership"
    " ON loyalty_tier_history(membership_id)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_rewards_program"
    " ON loyalty_rewards(program_id, active)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_reward_redemptions_membership"
    " ON loyalty_reward_redemptions(membership_id)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_reward_redemptions_reward"
    " ON loyalty_reward_redemptions(reward_id)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_challenge_definitions_program"
    " ON loyalty_challenge_definitions(program_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_challenge_member_progress_membership"
    " ON loyalty_challenge_member_progress(membership_id)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_streaks_membership"
    " ON loyalty_streaks(membership_id)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_badges_membership"
    " ON loyalty_badges(membership_id)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_referrals_referrer"
    " ON loyalty_referrals(referrer_membership_id)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_referrals_referred"
    " ON loyalty_referrals(referred_customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_referrals_status ON loyalty_referrals(status)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_campaigns_program"
    " ON loyalty_campaigns(program_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_fraud_cases_customer"
    " ON loyalty_fraud_cases(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_fraud_cases_status"
    " ON loyalty_fraud_cases(status)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_outbox_status ON loyalty_outbox(status)",
)


def create_loyalty_schema(conn) -> None:
    """Create the canonical Fidelidad/Loyalty schema (idempotent). DDL lives
    only here."""
    for statement in _DDL:
        conn.execute(statement)
    for index in _INDEXES:
        conn.execute(index)


def drop_loyalty_schema(conn) -> list[str]:
    dropped: list[str] = []
    for table in reversed(LOYALTY_TABLES):
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        dropped.append(table)
    return dropped
