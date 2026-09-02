"""Commercial Instruments bounded context — born-clean UUIDv7 schema
(LOY-12, §21-22). Mirrors backend/infrastructure/db/schema/loyalty_schema.py's
conventions exactly (same REGLA CERO rules: TEXT PRIMARY KEY UUIDv7, TEXT
decimal strings for money, no enum CHECK constraints).

Separate schema module from Loyalty's own — coupons/vouchers are a distinct
bounded context (master prompt §7.2/§7.4), not owned by Fidelidad, even
though they share the same `GROWTH_ENGINE` permission/nav surface
(`backend/application/loyalty/permissions.py::LoyaltyPermissions.COUPON_*`).

Verified via grep against `migrations/m000_base_schema.py` before naming —
no `coupon_definitions`/`coupon_instances`/`coupon_redemptions` collision.

Only a migration in ``migrations/`` may execute this DDL.
"""

from __future__ import annotations

COMMERCIAL_INSTRUMENTS_TABLES: tuple[str, ...] = (
    "coupon_definitions",
    "coupon_instances",
    "coupon_redemptions",
    "voucher_definitions",
    "voucher_instances",
    "voucher_transactions",
    "voucher_redemptions",
    "commercial_instruments_outbox",
)

_DDL = (
    # ── CouponDefinition ─────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS coupon_definitions (
        id TEXT PRIMARY KEY,
        code TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        coupon_type TEXT NOT NULL,
        benefit_type TEXT NOT NULL,
        benefit_value TEXT NOT NULL,
        max_redemptions_per_instance INTEGER NOT NULL DEFAULT 1,
        valid_from TEXT,
        valid_to TEXT,
        source_program_id TEXT,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    # ── CouponInstance ───────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS coupon_instances (
        id TEXT PRIMARY KEY,
        definition_id TEXT NOT NULL REFERENCES coupon_definitions(id),
        code TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL DEFAULT 'ACTIVE',
        customer_id TEXT,
        sale_id TEXT,
        issued_at TEXT NOT NULL,
        reserved_at TEXT,
        redeemed_at TEXT,
        closed_at TEXT,
        closed_reason TEXT
    )
    """,
    # ── CouponRedemption — append-only audit trail ──────────────────────
    """
    CREATE TABLE IF NOT EXISTS coupon_redemptions (
        id TEXT PRIMARY KEY,
        coupon_instance_id TEXT NOT NULL REFERENCES coupon_instances(id),
        sale_id TEXT NOT NULL,
        amount_applied TEXT NOT NULL,
        redeemed_by_user_id TEXT NOT NULL,
        redeemed_at TEXT NOT NULL,
        UNIQUE(coupon_instance_id)
    )
    """,
    # ── VoucherDefinition (LOY-13 §22) ──────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS voucher_definitions (
        id TEXT PRIMARY KEY,
        code TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        voucher_type TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    # ── VoucherInstance ──────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS voucher_instances (
        id TEXT PRIMARY KEY,
        definition_id TEXT NOT NULL REFERENCES voucher_definitions(id),
        code TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL DEFAULT 'ACTIVE',
        customer_id TEXT,
        sale_id TEXT,
        issued_at TEXT NOT NULL,
        expires_at TEXT,
        closed_at TEXT,
        closed_reason TEXT
    )
    """,
    # ── VoucherTransaction ledger — §22 idempotency: UNIQUE(operation_id) ─
    """
    CREATE TABLE IF NOT EXISTS voucher_transactions (
        id TEXT PRIMARY KEY,
        voucher_instance_id TEXT NOT NULL REFERENCES voucher_instances(id),
        transaction_type TEXT NOT NULL,
        amount TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'AVAILABLE',
        operation_id TEXT NOT NULL UNIQUE,
        sale_id TEXT,
        reversal_transaction_id TEXT REFERENCES voucher_transactions(id),
        reason_code TEXT,
        notes TEXT NOT NULL DEFAULT '',
        created_by_user_id TEXT,
        created_at TEXT NOT NULL
    )
    """,
    # ── VoucherRedemption — append-only, MULTIPLE per instance (partial) ──
    """
    CREATE TABLE IF NOT EXISTS voucher_redemptions (
        id TEXT PRIMARY KEY,
        voucher_instance_id TEXT NOT NULL REFERENCES voucher_instances(id),
        sale_id TEXT NOT NULL,
        amount_applied TEXT NOT NULL,
        redeemed_by_user_id TEXT NOT NULL,
        redeemed_at TEXT NOT NULL
    )
    """,
    # ── transactional outbox ─────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS commercial_instruments_outbox (
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
    "CREATE INDEX IF NOT EXISTS idx_coupon_definitions_active"
    " ON coupon_definitions(active)",
    "CREATE INDEX IF NOT EXISTS idx_coupon_instances_definition"
    " ON coupon_instances(definition_id)",
    "CREATE INDEX IF NOT EXISTS idx_coupon_instances_customer"
    " ON coupon_instances(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_coupon_instances_status"
    " ON coupon_instances(status)",
    "CREATE INDEX IF NOT EXISTS idx_coupon_redemptions_sale"
    " ON coupon_redemptions(sale_id)",
    "CREATE INDEX IF NOT EXISTS idx_voucher_instances_definition"
    " ON voucher_instances(definition_id)",
    "CREATE INDEX IF NOT EXISTS idx_voucher_instances_customer"
    " ON voucher_instances(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_voucher_instances_status"
    " ON voucher_instances(status)",
    "CREATE INDEX IF NOT EXISTS idx_voucher_transactions_instance"
    " ON voucher_transactions(voucher_instance_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_voucher_redemptions_instance"
    " ON voucher_redemptions(voucher_instance_id)",
    "CREATE INDEX IF NOT EXISTS idx_commercial_instruments_outbox_status"
    " ON commercial_instruments_outbox(status)",
)


def create_commercial_instruments_schema(conn) -> None:
    """Create the canonical Commercial Instruments schema (idempotent)."""
    for statement in _DDL:
        conn.execute(statement)
    for index in _INDEXES:
        conn.execute(index)


def drop_commercial_instruments_schema(conn) -> list[str]:
    dropped: list[str] = []
    for table in reversed(COMMERCIAL_INSTRUMENTS_TABLES):
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        dropped.append(table)
    return dropped
