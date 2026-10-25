"""Commercial Instruments bounded context — born-clean UUIDv7 schema
(LOY-12, §21-22). Mirrors backend/infrastructure/db/schema/loyalty_schema.py's
conventions exactly (same REGLA CERO rules: TEXT NOT NULL PRIMARY KEY UUIDv7, TEXT
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
    "instrument_batches",
    "instrument_batch_items",
    "voucher_instance_rules",
    "commercial_instrument_secrets",
)

_DDL = (
    # ── CouponDefinition ─────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS coupon_definitions (
        id TEXT NOT NULL PRIMARY KEY,
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
        id TEXT NOT NULL PRIMARY KEY,
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
        id TEXT NOT NULL PRIMARY KEY,
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
        id TEXT NOT NULL PRIMARY KEY,
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
        id TEXT NOT NULL PRIMARY KEY,
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
        id TEXT NOT NULL PRIMARY KEY,
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
        id TEXT NOT NULL PRIMARY KEY,
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
        id TEXT NOT NULL PRIMARY KEY,
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

#: Lotes físicos de cupones y vales (auditoría de Fidelidad 968e0bc, ampliación).
#: El código impreso es un token de alta entropía derivado con HMAC del secreto
#: de la instalación y del id de la PIEZA; sólo se guarda su huella (SHA-256) y
#: un prefijo corto para soporte. El folio es el identificador legible, no
#: canjeable.
_BATCH_DDL = (
    """
    CREATE TABLE IF NOT EXISTS instrument_batches (
        id TEXT NOT NULL PRIMARY KEY,
        kind TEXT NOT NULL,
        definition_id TEXT NOT NULL,
        name TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        unit_value TEXT NOT NULL,
        funding_source TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'DRAFT',
        valid_from TEXT,
        valid_to TEXT,
        branch_ids_json TEXT NOT NULL DEFAULT '[]',
        redemption_mode TEXT NOT NULL,
        max_redemptions INTEGER,
        max_percent_per_sale TEXT,
        percent_base TEXT NOT NULL,
        leftover_policy TEXT NOT NULL,
        created_by_user_id TEXT NOT NULL,
        approved_by_user_id TEXT,
        approved_at TEXT,
        printed_count INTEGER NOT NULL DEFAULT 0,
        activated_at TEXT,
        cancelled_reason TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS instrument_batch_items (
        id TEXT NOT NULL PRIMARY KEY,
        batch_id TEXT NOT NULL REFERENCES instrument_batches(id),
        sequence_no INTEGER NOT NULL,
        folio TEXT NOT NULL UNIQUE,
        instance_kind TEXT NOT NULL,
        instance_id TEXT NOT NULL UNIQUE,
        token_hash TEXT NOT NULL UNIQUE,
        token_prefix TEXT NOT NULL,
        token_version INTEGER NOT NULL DEFAULT 1,
        status TEXT NOT NULL DEFAULT 'ISSUED',
        print_count INTEGER NOT NULL DEFAULT 0,
        revoked_reason TEXT,
        created_at TEXT NOT NULL,
        UNIQUE(batch_id, sequence_no)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS voucher_instance_rules (
        voucher_instance_id TEXT NOT NULL PRIMARY KEY REFERENCES voucher_instances(id),
        batch_id TEXT REFERENCES instrument_batches(id),
        redemption_mode TEXT NOT NULL,
        max_redemptions INTEGER,
        max_percent_per_sale TEXT,
        percent_base TEXT NOT NULL,
        leftover_policy TEXT NOT NULL,
        funding_source TEXT NOT NULL,
        branch_ids_json TEXT NOT NULL DEFAULT '[]',
        valid_from TEXT,
        valid_to TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS commercial_instrument_secrets (
        id TEXT NOT NULL PRIMARY KEY,
        value TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
)

_BATCH_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_instrument_batches_status ON instrument_batches(status)",
    "CREATE INDEX IF NOT EXISTS idx_instrument_batch_items_batch"
    " ON instrument_batch_items(batch_id, status)",
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
    create_instrument_batch_schema(conn)


def create_instrument_batch_schema(conn) -> None:
    """Lotes físicos de cupones y vales (migración 349). Idempotente."""
    for statement in _BATCH_DDL:
        conn.execute(statement)
    for index in _BATCH_INDEXES:
        conn.execute(index)


def drop_commercial_instruments_schema(conn) -> list[str]:
    dropped: list[str] = []
    for table in reversed(COMMERCIAL_INSTRUMENTS_TABLES):
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        dropped.append(table)
    return dropped
