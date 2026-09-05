"""Procurement bounded context — born-clean UUIDv7 schema (single source of truth).

Rules:
- Every id is ``TEXT PRIMARY KEY`` holding a lowercase UUIDv7 (PostgreSQL: UUID).
- Money/weight/quantity columns are ``TEXT`` decimal strings (PostgreSQL:
  NUMERIC); no REAL — floats are forbidden for money/weight/quantity.
- Structural idempotency: UNIQUE(operation_id) / UNIQUE(document_number) /
  UNIQUE(event_id) in processed events.
- Canonical names (direct_purchases, purchase_orders, goods_receipts,
  purchase_requisitions, supplier_invoices…) do not collide with the legacy
  Spanish tables (compras/ordenes_compra/recepciones/purchase_requests), which
  keep their live readers until PUR-11 migrates them.

Only a migration in ``migrations/`` may execute this DDL.
"""

from __future__ import annotations

PROCUREMENT_TABLES: tuple[str, ...] = (
    "user_purchase_limits",
    "role_purchase_limits",
    "branch_purchase_limits",
    "direct_purchases",
    "direct_purchase_lines",
    "direct_purchase_authorizations",
    "purchase_requisitions",
    "purchase_requisition_lines",
    "requests_for_quotation",
    "rfq_supplier_invitations",
    "supplier_quotes",
    "supplier_quote_lines",
    "purchase_awards",
    "purchase_award_lines",
    "purchase_orders",
    "purchase_order_lines",
    "purchase_order_versions",
    "goods_receipts",
    "goods_receipt_lines",
    "receipt_discrepancies",
    "supplier_invoices",
    "supplier_invoice_lines",
    "supplier_invoice_matches",
    "purchase_authorization_log",
    "procurement_audit_log",
    "procurement_outbox",
    "procurement_processed_events",
)

_DDL = (
    # ── limits ────────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS user_purchase_limits (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        currency_code TEXT NOT NULL DEFAULT 'MXN',
        maximum_per_transaction TEXT,
        maximum_per_day TEXT,
        maximum_per_month TEXT,
        requires_approval_above TEXT,
        valid_from TEXT,
        valid_to TEXT,
        active INTEGER NOT NULL DEFAULT 1,
        UNIQUE (user_id, currency_code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS role_purchase_limits (
        id TEXT PRIMARY KEY,
        role_code TEXT NOT NULL,
        currency_code TEXT NOT NULL DEFAULT 'MXN',
        maximum_per_transaction TEXT,
        requires_approval_above TEXT,
        active INTEGER NOT NULL DEFAULT 1,
        UNIQUE (role_code, currency_code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS branch_purchase_limits (
        id TEXT PRIMARY KEY,
        branch_id TEXT NOT NULL,
        currency_code TEXT NOT NULL DEFAULT 'MXN',
        maximum_per_transaction TEXT,
        allows_direct_purchase INTEGER NOT NULL DEFAULT 1,
        receiving_window_start TEXT,
        receiving_window_end TEXT,
        active INTEGER NOT NULL DEFAULT 1,
        UNIQUE (branch_id, currency_code)
    )
    """,
    # ── direct purchase ───────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS direct_purchases (
        id TEXT PRIMARY KEY,
        document_number TEXT NOT NULL UNIQUE,
        supplier_id TEXT NOT NULL,
        branch_id TEXT NOT NULL,
        warehouse_id TEXT NOT NULL,
        mode TEXT NOT NULL,
        payment_condition TEXT NOT NULL,
        currency_code TEXT NOT NULL DEFAULT 'MXN',
        source_channel TEXT NOT NULL DEFAULT 'PROCUREMENT_DIRECT',
        purchase_type TEXT NOT NULL DEFAULT 'DIRECT',
        status TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN (
            'DRAFT','PENDING_AUTHORIZATION','CONFIRMED','PARTIALLY_RECEIVED',
            'RECEIVED','CANCELLED','REVERSED')),
        subtotal TEXT NOT NULL DEFAULT '0',
        tax_total TEXT NOT NULL DEFAULT '0',
        total TEXT NOT NULL DEFAULT '0',
        payment_source TEXT,
        created_by_user_id TEXT,
        authorized_by_user_id TEXT,
        authorization_reason TEXT NOT NULL DEFAULT '',
        operation_id TEXT UNIQUE,
        goods_receipt_id TEXT,
        payable_id TEXT,
        payment_instruction_id TEXT,
        source_requisition_id TEXT REFERENCES purchase_requisitions(id),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS direct_purchase_lines (
        id TEXT PRIMARY KEY,
        direct_purchase_id TEXT NOT NULL REFERENCES direct_purchases(id),
        product_id TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        quantity TEXT NOT NULL,
        unit_cost TEXT NOT NULL,
        purchase_nature TEXT NOT NULL CHECK (purchase_nature IN (
            'INVENTORY','EXPENSE','ASSET','SERVICE','CONSUMABLE','PACKAGING','MAINTENANCE')),
        currency_code TEXT NOT NULL DEFAULT 'MXN',
        purchase_unit TEXT NOT NULL DEFAULT 'PZA',
        inventory_unit TEXT NOT NULL DEFAULT 'PZA',
        conversion_factor TEXT NOT NULL DEFAULT '1',
        discount TEXT NOT NULL DEFAULT '0',
        tax TEXT NOT NULL DEFAULT '0',
        line_total TEXT NOT NULL DEFAULT '0',
        destination_branch_id TEXT,
        destination_warehouse_id TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS direct_purchase_authorizations (
        id TEXT PRIMARY KEY,
        direct_purchase_id TEXT NOT NULL REFERENCES direct_purchases(id),
        requested_by_user_id TEXT NOT NULL,
        authorized_by_user_id TEXT NOT NULL,
        permission_code TEXT NOT NULL,
        reason TEXT NOT NULL,
        amount TEXT NOT NULL,
        terminal_id TEXT,
        operation_id TEXT,
        created_at TEXT NOT NULL
    )
    """,
    # ── requisitions ──────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS purchase_requisitions (
        id TEXT PRIMARY KEY,
        document_number TEXT NOT NULL UNIQUE,
        branch_id TEXT NOT NULL,
        requested_by_user_id TEXT NOT NULL,
        purchase_type TEXT NOT NULL,
        priority TEXT NOT NULL DEFAULT 'NORMAL',
        business_reason TEXT NOT NULL DEFAULT '',
        required_date TEXT,
        status TEXT NOT NULL DEFAULT 'DRAFT',
        source_channel TEXT NOT NULL DEFAULT 'PROCUREMENT_DESKTOP',
        source_reference_id TEXT,
        approved_by_user_id TEXT,
        operation_id TEXT UNIQUE,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS purchase_requisition_lines (
        id TEXT PRIMARY KEY,
        requisition_id TEXT NOT NULL REFERENCES purchase_requisitions(id),
        product_id TEXT NOT NULL,
        quantity TEXT NOT NULL,
        purchase_nature TEXT NOT NULL CHECK (purchase_nature IN (
            'INVENTORY','EXPENSE','ASSET','SERVICE','CONSUMABLE','PACKAGING','MAINTENANCE')),
        estimated_unit_cost TEXT,
        currency_code TEXT NOT NULL DEFAULT 'MXN',
        required_date TEXT
    )
    """,
    # ── rfq / quotes ──────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS requests_for_quotation (
        id TEXT PRIMARY KEY,
        document_number TEXT NOT NULL UNIQUE,
        requisition_id TEXT REFERENCES purchase_requisitions(id),
        response_deadline TEXT,
        status TEXT NOT NULL DEFAULT 'DRAFT',
        operation_id TEXT UNIQUE,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rfq_supplier_invitations (
        id TEXT PRIMARY KEY,
        rfq_id TEXT NOT NULL REFERENCES requests_for_quotation(id),
        supplier_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'INVITED',
        invited_at TEXT NOT NULL,
        UNIQUE (rfq_id, supplier_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS supplier_quotes (
        id TEXT PRIMARY KEY,
        rfq_id TEXT NOT NULL REFERENCES requests_for_quotation(id),
        supplier_id TEXT NOT NULL,
        currency_code TEXT NOT NULL DEFAULT 'MXN',
        lead_time_days INTEGER NOT NULL DEFAULT 0,
        total TEXT NOT NULL DEFAULT '0',
        operation_id TEXT UNIQUE,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS supplier_quote_lines (
        id TEXT PRIMARY KEY,
        quote_id TEXT NOT NULL REFERENCES supplier_quotes(id),
        product_id TEXT NOT NULL,
        quantity TEXT NOT NULL,
        unit_price TEXT NOT NULL,
        purchase_nature TEXT NOT NULL CHECK (purchase_nature IN (
            'INVENTORY','EXPENSE','ASSET','SERVICE','CONSUMABLE','PACKAGING','MAINTENANCE')),
        discount TEXT NOT NULL DEFAULT '0',
        tax TEXT NOT NULL DEFAULT '0',
        currency_code TEXT NOT NULL DEFAULT 'MXN'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS purchase_awards (
        id TEXT PRIMARY KEY,
        rfq_id TEXT NOT NULL REFERENCES requests_for_quotation(id),
        approved_by_user_id TEXT NOT NULL,
        operation_id TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS purchase_award_lines (
        id TEXT PRIMARY KEY,
        award_id TEXT NOT NULL REFERENCES purchase_awards(id),
        quote_line_id TEXT NOT NULL REFERENCES supplier_quote_lines(id),
        supplier_id TEXT NOT NULL,
        awarded_quantity TEXT NOT NULL,
        justification TEXT NOT NULL,
        UNIQUE (award_id, quote_line_id, supplier_id)
    )
    """,
    # ── purchase orders ───────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS purchase_orders (
        id TEXT PRIMARY KEY,
        document_number TEXT NOT NULL UNIQUE,
        supplier_id TEXT NOT NULL,
        branch_id TEXT NOT NULL,
        warehouse_id TEXT NOT NULL,
        currency_code TEXT NOT NULL DEFAULT 'MXN',
        purchase_type TEXT NOT NULL DEFAULT 'INVENTORY',
        status TEXT NOT NULL DEFAULT 'DRAFT',
        total TEXT NOT NULL DEFAULT '0',
        version INTEGER NOT NULL DEFAULT 1,
        created_by_user_id TEXT,
        approved_by_user_id TEXT,
        source_requisition_id TEXT REFERENCES purchase_requisitions(id),
        source_rfq_id TEXT REFERENCES requests_for_quotation(id),
        source_award_id TEXT REFERENCES purchase_awards(id),
        operation_id TEXT UNIQUE,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        payment_terms TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS purchase_order_lines (
        id TEXT PRIMARY KEY,
        purchase_order_id TEXT NOT NULL REFERENCES purchase_orders(id),
        product_id TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        ordered_quantity TEXT NOT NULL,
        unit_price TEXT NOT NULL,
        purchase_nature TEXT NOT NULL CHECK (purchase_nature IN (
            'INVENTORY','EXPENSE','ASSET','SERVICE','CONSUMABLE','PACKAGING','MAINTENANCE')),
        currency_code TEXT NOT NULL DEFAULT 'MXN',
        conversion_factor TEXT NOT NULL DEFAULT '1',
        received_quantity TEXT NOT NULL DEFAULT '0',
        accepted_quantity TEXT NOT NULL DEFAULT '0',
        rejected_quantity TEXT NOT NULL DEFAULT '0',
        invoiced_quantity TEXT NOT NULL DEFAULT '0',
        destination_warehouse_id TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS purchase_order_versions (
        id TEXT PRIMARY KEY,
        purchase_order_id TEXT NOT NULL REFERENCES purchase_orders(id),
        version INTEGER NOT NULL,
        before_json TEXT,
        after_json TEXT,
        reason TEXT NOT NULL DEFAULT '',
        changed_by_user_id TEXT,
        created_at TEXT NOT NULL
    )
    """,
    # ── goods receipts ────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS goods_receipts (
        id TEXT PRIMARY KEY,
        document_number TEXT NOT NULL UNIQUE,
        supplier_id TEXT NOT NULL,
        branch_id TEXT NOT NULL,
        warehouse_id TEXT NOT NULL,
        purchase_order_id TEXT,
        direct_purchase_id TEXT,
        status TEXT NOT NULL DEFAULT 'STARTED' CHECK (status IN (
            'STARTED','COMPLETED','REVERSED')),
        received_by_user_id TEXT,
        operation_id TEXT UNIQUE,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS goods_receipt_lines (
        id TEXT PRIMARY KEY,
        goods_receipt_id TEXT NOT NULL REFERENCES goods_receipts(id),
        product_id TEXT NOT NULL,
        ordered_quantity TEXT NOT NULL DEFAULT '0',
        received_quantity TEXT NOT NULL,
        accepted_quantity TEXT NOT NULL,
        rejected_quantity TEXT NOT NULL DEFAULT '0',
        lot TEXT,
        expiration TEXT,
        temperature TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS receipt_discrepancies (
        id TEXT PRIMARY KEY,
        goods_receipt_id TEXT NOT NULL REFERENCES goods_receipts(id),
        discrepancy_type TEXT NOT NULL,
        expected TEXT NOT NULL,
        actual TEXT NOT NULL,
        reason TEXT NOT NULL DEFAULT ''
    )
    """,
    # ── invoices ──────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS supplier_invoices (
        id TEXT PRIMARY KEY,
        document_number TEXT NOT NULL UNIQUE,
        supplier_id TEXT NOT NULL,
        invoice_number TEXT NOT NULL,
        subtotal TEXT NOT NULL,
        tax_total TEXT NOT NULL,
        total TEXT NOT NULL,
        currency_code TEXT NOT NULL DEFAULT 'MXN',
        purchase_order_id TEXT,
        direct_purchase_id TEXT,
        uuid_fiscal TEXT,
        status TEXT NOT NULL DEFAULT 'CAPTURED',
        match_result TEXT,
        captured_by_user_id TEXT NOT NULL,
        matched_by_user_id TEXT,
        released_by_user_id TEXT,
        payable_id TEXT,
        operation_id TEXT UNIQUE,
        created_at TEXT NOT NULL,
        UNIQUE (supplier_id, invoice_number)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS supplier_invoice_lines (
        id TEXT PRIMARY KEY,
        supplier_invoice_id TEXT NOT NULL REFERENCES supplier_invoices(id),
        product_id TEXT NOT NULL,
        invoiced_quantity TEXT NOT NULL,
        unit_price TEXT NOT NULL,
        tax TEXT NOT NULL DEFAULT '0',
        currency_code TEXT NOT NULL,
        purchase_order_line_id TEXT REFERENCES purchase_order_lines(id),
        direct_purchase_line_id TEXT REFERENCES direct_purchase_lines(id),
        receipt_line_id TEXT REFERENCES goods_receipt_lines(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS supplier_invoice_matches (
        id TEXT PRIMARY KEY,
        supplier_invoice_id TEXT NOT NULL REFERENCES supplier_invoices(id),
        result TEXT NOT NULL,
        released_by_user_id TEXT,
        notes TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    )
    """,
    # ── authorization log / audit / outbox ────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS purchase_authorization_log (
        id TEXT PRIMARY KEY,
        operation_id TEXT NOT NULL,
        permission_code TEXT NOT NULL,
        requested_by_user_id TEXT NOT NULL,
        authorized_by_user_id TEXT NOT NULL,
        reason TEXT NOT NULL,
        amount TEXT NOT NULL,
        document_id TEXT,
        terminal_id TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS procurement_audit_log (
        id TEXT PRIMARY KEY,
        document_id TEXT,
        action TEXT NOT NULL,
        actor_user_id TEXT,
        authorized_by TEXT,
        before_json TEXT,
        after_json TEXT,
        reason TEXT NOT NULL DEFAULT '',
        operation_id TEXT,
        branch_id TEXT,
        terminal_id TEXT,
        source_channel TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS procurement_outbox (
        id TEXT PRIMARY KEY,
        event_id TEXT NOT NULL,
        event_name TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        operation_id TEXT NOT NULL,
        deduplication_key TEXT UNIQUE,
        status TEXT NOT NULL DEFAULT 'PENDING',
        attempt_count INTEGER NOT NULL DEFAULT 0,
        next_attempt_at TEXT,
        last_error TEXT,
        created_at TEXT NOT NULL,
        dispatched_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS procurement_processed_events (
        event_id TEXT PRIMARY KEY,
        event_name TEXT NOT NULL,
        operation_id TEXT NOT NULL,
        processed_at TEXT NOT NULL
    )
    """,
)

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_direct_purchases_status ON direct_purchases(status)",
    "CREATE INDEX IF NOT EXISTS idx_direct_purchases_supplier ON direct_purchases(supplier_id)",
    "CREATE INDEX IF NOT EXISTS idx_direct_purchases_branch ON direct_purchases(branch_id)",
    "CREATE INDEX IF NOT EXISTS idx_direct_purchase_lines_dp ON direct_purchase_lines(direct_purchase_id)",
    "CREATE INDEX IF NOT EXISTS idx_requisitions_status ON purchase_requisitions(status)",
    "CREATE INDEX IF NOT EXISTS idx_requisition_lines_req ON purchase_requisition_lines(requisition_id)",
    "CREATE INDEX IF NOT EXISTS idx_quotes_rfq ON supplier_quotes(rfq_id)",
    "CREATE INDEX IF NOT EXISTS idx_orders_status ON purchase_orders(status)",
    "CREATE INDEX IF NOT EXISTS idx_orders_supplier ON purchase_orders(supplier_id)",
    "CREATE INDEX IF NOT EXISTS idx_order_lines_po ON purchase_order_lines(purchase_order_id)",
    "CREATE INDEX IF NOT EXISTS idx_receipts_po ON goods_receipts(purchase_order_id)",
    "CREATE INDEX IF NOT EXISTS idx_receipts_dp ON goods_receipts(direct_purchase_id)",
    "CREATE INDEX IF NOT EXISTS idx_receipt_lines_gr ON goods_receipt_lines(goods_receipt_id)",
    "CREATE INDEX IF NOT EXISTS idx_invoices_supplier ON supplier_invoices(supplier_id)",
    "CREATE INDEX IF NOT EXISTS idx_user_limits_user ON user_purchase_limits(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_proc_outbox_status ON procurement_outbox(status)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_proc_outbox_event ON procurement_outbox(event_id)",
    "CREATE INDEX IF NOT EXISTS idx_proc_audit_doc ON procurement_audit_log(document_id)",
)


def _column_exists(conn, table: str, column: str) -> bool:
    return any(r[1] == column for r in conn.execute(f"PRAGMA table_info({table})"))


def create_procurement_schema(conn) -> None:
    """Create the canonical procurement schema (idempotent). DDL lives only here."""
    for statement in _DDL:
        conn.execute(statement)
    for index in _INDEXES:
        conn.execute(index)
    # purchase_orders.payment_terms (migration 253) — CREATE TABLE IF NOT EXISTS
    # above only covers a never-before-created table; a purchase_orders table
    # created by an earlier run of this same function still needs the ALTER.
    if not _column_exists(conn, "purchase_orders", "payment_terms"):
        conn.execute("ALTER TABLE purchase_orders ADD COLUMN payment_terms TEXT")


def drop_procurement_schema(conn) -> list[str]:
    dropped: list[str] = []
    for table in reversed(PROCUREMENT_TABLES):
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        dropped.append(table)
    return dropped


# ── purchase returns (devoluciones a proveedor) — migration 205 ────────────────
# A separate, later-added table group. Kept out of PROCUREMENT_TABLES/_DDL/
# create_procurement_schema on purpose: databases that already ran migration
# "120" have that migration marked done in schema_migrations and will never
# re-run it, so extending create_procurement_schema would silently skip
# existing installs. create_purchase_returns_schema() is called only by
# migration 205.
PURCHASE_RETURN_TABLES: tuple[str, ...] = (
    "purchase_returns",
    "purchase_return_lines",
)

_RETURNS_DDL = (
    """
    CREATE TABLE IF NOT EXISTS purchase_returns (
        id TEXT PRIMARY KEY,
        document_number TEXT NOT NULL UNIQUE,
        supplier_id TEXT NOT NULL,
        branch_id TEXT NOT NULL,
        warehouse_id TEXT NOT NULL,
        goods_receipt_id TEXT REFERENCES goods_receipts(id),
        purchase_order_id TEXT REFERENCES purchase_orders(id),
        reason TEXT NOT NULL CHECK (reason IN (
            'QUALITY','DAMAGED','WRONG_PRODUCT','EXCESS','EXPIRED',
            'SANITARY_FAILURE','COMMERCIAL_AGREEMENT')),
        status TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN (
            'DRAFT','CONFIRMED','CANCELLED')),
        created_by_user_id TEXT,
        operation_id TEXT UNIQUE,
        created_at TEXT NOT NULL,
        confirmed_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS purchase_return_lines (
        id TEXT PRIMARY KEY,
        purchase_return_id TEXT NOT NULL REFERENCES purchase_returns(id),
        product_id TEXT NOT NULL,
        quantity TEXT NOT NULL,
        unit_cost TEXT,
        lot TEXT,
        goods_receipt_line_id TEXT REFERENCES goods_receipt_lines(id),
        notes TEXT NOT NULL DEFAULT ''
    )
    """,
)

_RETURNS_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_purchase_returns_status ON purchase_returns(status)",
    "CREATE INDEX IF NOT EXISTS idx_purchase_returns_supplier ON purchase_returns(supplier_id)",
    "CREATE INDEX IF NOT EXISTS idx_purchase_returns_branch ON purchase_returns(branch_id)",
    "CREATE INDEX IF NOT EXISTS idx_purchase_returns_receipt"
    " ON purchase_returns(goods_receipt_id)",
    "CREATE INDEX IF NOT EXISTS idx_purchase_return_lines_return"
    " ON purchase_return_lines(purchase_return_id)",
)


def create_purchase_returns_schema(conn) -> None:
    """Create the purchase_returns / purchase_return_lines tables (idempotent).

    DDL lives only here; only migration 205 may call this.
    """
    for statement in _RETURNS_DDL:
        conn.execute(statement)
    for index in _RETURNS_INDEXES:
        conn.execute(index)


def drop_purchase_returns_schema(conn) -> list[str]:
    dropped: list[str] = []
    for table in reversed(PURCHASE_RETURN_TABLES):
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        dropped.append(table)
    return dropped
