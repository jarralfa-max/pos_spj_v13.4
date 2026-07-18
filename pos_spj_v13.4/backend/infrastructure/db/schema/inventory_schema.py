"""Inventory bounded context — born-clean UUIDv7 schema (single source of truth).

Rules (REGLA CERO / §8 / §9):
- Every id is ``TEXT PRIMARY KEY`` holding a lowercase UUIDv7 (PostgreSQL: UUID).
- quantity / weight / cost / threshold columns are ``TEXT`` decimal strings
  (PostgreSQL: NUMERIC); no REAL — floats are forbidden.
- The ledger (``inventory_movements`` + ``inventory_movement_lines``) is the
  source of truth; ``inventory_balances`` is a rebuildable projection, never
  mutated by UI or other contexts.
- Structural idempotency: UNIQUE(operation_id) on movements, UNIQUE(event_id)
  in processed events, UNIQUE full-dimension on balances.
- Nullable balance dimensions (location/lot/serial) are stored as ``''`` (not
  NULL) so the UNIQUE key behaves; the repository maps None ↔ '' (INV-4).

Canonical English names (warehouses, storage_locations, inventory_ledger,
inventory_balances…) do NOT collide with the legacy/partial tables
(inventario_actual, inventory_stock, inventory_movements[098], movimientos_
inventario, transferencias…), which keep their live readers until INV-6/INV-11
migrate them and INV-27 drops them (see inventory_schema_consolidation.md). The
canonical ledger is ``inventory_ledger`` (the name ``inventory_movements`` is
still owned by the legacy migration 098 and is reclaimed only at INV-27).

Only a migration in ``migrations/`` may execute this DDL.
"""

from __future__ import annotations

INVENTORY_TABLES: tuple[str, ...] = (
    "inventory_operation_limits",
    "warehouses",
    "warehouse_zones",
    "storage_locations",
    "inventory_ledger",
    "inventory_ledger_lines",
    "inventory_balances",
    "inventory_settings",
    "inventory_authorization_log",
    "inventory_audit_log",
    "inventory_outbox",
    "inventory_processed_events",
)

_DDL = (
    # ── configurable limits (INV-1 §48) ───────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS inventory_operation_limits (
        id TEXT PRIMARY KEY,
        scope_type TEXT NOT NULL,           -- USER | ROLE | BRANCH | WAREHOUSE
        scope_id TEXT NOT NULL,
        operation_kind TEXT NOT NULL,       -- ADJUSTMENT | TRANSFER | WEIGHT_VARIANCE | COUNT_VARIANCE | NEGATIVE_OVERRIDE
        basis TEXT NOT NULL DEFAULT 'QUANTITY',
        warning_threshold TEXT,
        approval_threshold TEXT,
        hard_cap TEXT,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        UNIQUE (scope_type, scope_id, operation_kind)
    )
    """,
    # ── warehouses / zones / locations (§12) ───────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS warehouses (
        id TEXT PRIMARY KEY,
        code TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        branch_id TEXT NOT NULL,
        warehouse_type TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'ACTIVE',
        temperature_profile TEXT,
        allow_sales_allocation INTEGER NOT NULL DEFAULT 1,
        allow_purchase_receipt INTEGER NOT NULL DEFAULT 1,
        allow_production INTEGER NOT NULL DEFAULT 0,
        allow_quarantine INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS warehouse_zones (
        id TEXT PRIMARY KEY,
        warehouse_id TEXT NOT NULL,
        code TEXT NOT NULL,
        name TEXT NOT NULL,
        zone_type TEXT NOT NULL,
        UNIQUE (warehouse_id, code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS storage_locations (
        id TEXT PRIMARY KEY,
        warehouse_id TEXT NOT NULL,
        zone_id TEXT,
        parent_location_id TEXT,
        code TEXT NOT NULL,
        name TEXT NOT NULL,
        level INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'ACTIVE',
        UNIQUE (warehouse_id, code)
    )
    """,
    # ── ledger: movements + lines (§15) ────────────────────────────────────
    # Canonical ledger table is ``inventory_ledger`` (the legacy 098 table
    # ``inventory_movements`` keeps its readers until INV-27).
    """
    CREATE TABLE IF NOT EXISTS inventory_ledger (
        id TEXT PRIMARY KEY,
        movement_type TEXT NOT NULL,
        branch_id TEXT NOT NULL,
        warehouse_id TEXT NOT NULL,
        source_module TEXT NOT NULL,
        source_document_type TEXT NOT NULL,
        source_document_id TEXT NOT NULL,
        operation_id TEXT NOT NULL UNIQUE,
        created_by_user_id TEXT NOT NULL,
        authorized_by_user_id TEXT,
        status TEXT NOT NULL DEFAULT 'POSTED',
        occurred_at TEXT NOT NULL,
        reversal_of_id TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inventory_ledger_lines (
        id TEXT PRIMARY KEY,
        movement_id TEXT NOT NULL,
        product_id TEXT NOT NULL,
        lot_id TEXT,
        serial_id TEXT,
        quantity TEXT NOT NULL DEFAULT '0',
        weight TEXT NOT NULL DEFAULT '0',
        unit TEXT NOT NULL DEFAULT 'PZA',
        from_location_id TEXT,
        to_location_id TEXT,
        from_status TEXT,
        to_status TEXT,
        unit_cost TEXT,
        reason_code TEXT,
        FOREIGN KEY (movement_id) REFERENCES inventory_ledger(id)
    )
    """,
    # ── balance projection (§14) ───────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS inventory_balances (
        id TEXT PRIMARY KEY,
        product_id TEXT NOT NULL,
        branch_id TEXT NOT NULL,
        warehouse_id TEXT NOT NULL,
        location_id TEXT NOT NULL DEFAULT '',
        lot_id TEXT NOT NULL DEFAULT '',
        serial_id TEXT NOT NULL DEFAULT '',
        inventory_status TEXT NOT NULL DEFAULT 'AVAILABLE',
        quantity TEXT NOT NULL DEFAULT '0',
        weight TEXT NOT NULL DEFAULT '0',
        reserved_quantity TEXT NOT NULL DEFAULT '0',
        reserved_weight TEXT NOT NULL DEFAULT '0',
        version INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL,
        UNIQUE (product_id, branch_id, warehouse_id, location_id, lot_id,
                serial_id, inventory_status)
    )
    """,
    # ── configuration (§56) ────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS inventory_settings (
        id TEXT PRIMARY KEY,
        scope_type TEXT NOT NULL DEFAULT 'GLOBAL',
        scope_id TEXT NOT NULL DEFAULT '',
        setting_key TEXT NOT NULL,
        setting_value TEXT NOT NULL,
        effective_from TEXT,
        effective_to TEXT,
        version INTEGER NOT NULL DEFAULT 1,
        created_by_user_id TEXT,
        approved_by_user_id TEXT,
        UNIQUE (scope_type, scope_id, setting_key)
    )
    """,
    # ── hot authorization + audit (§48, §49) ───────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS inventory_authorization_log (
        id TEXT PRIMARY KEY,
        permission_code TEXT NOT NULL,
        requested_by TEXT NOT NULL,
        authorized_by TEXT NOT NULL,
        operation_id TEXT NOT NULL,
        reason TEXT NOT NULL,
        quantity TEXT,
        weight TEXT,
        value_reference TEXT,
        device_id TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inventory_audit_log (
        id TEXT PRIMARY KEY,
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        action TEXT NOT NULL,
        user_id TEXT,
        authorized_by TEXT,
        operation_id TEXT,
        before_json TEXT,
        after_json TEXT,
        reason TEXT,
        branch_id TEXT,
        warehouse_id TEXT,
        location_id TEXT,
        product_id TEXT,
        lot_id TEXT,
        occurred_at TEXT NOT NULL,
        device_id TEXT,
        source_module TEXT NOT NULL DEFAULT 'inventory'
    )
    """,
    # ── transactional outbox + processed events (§58, §59) ─────────────────
    """
    CREATE TABLE IF NOT EXISTS inventory_outbox (
        id TEXT PRIMARY KEY,
        event_id TEXT NOT NULL,
        event_name TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        operation_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDING',
        created_at TEXT NOT NULL,
        dispatched_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inventory_processed_events (
        event_id TEXT PRIMARY KEY,
        event_name TEXT NOT NULL,
        operation_id TEXT NOT NULL,
        processed_at TEXT NOT NULL
    )
    """,
)

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_inv_limits_scope ON inventory_operation_limits(scope_type, scope_id)",
    "CREATE INDEX IF NOT EXISTS idx_inv_warehouses_branch ON warehouses(branch_id)",
    "CREATE INDEX IF NOT EXISTS idx_inv_zones_wh ON warehouse_zones(warehouse_id)",
    "CREATE INDEX IF NOT EXISTS idx_inv_locations_wh ON storage_locations(warehouse_id)",
    "CREATE INDEX IF NOT EXISTS idx_inv_locations_parent ON storage_locations(parent_location_id)",
    "CREATE INDEX IF NOT EXISTS idx_inv_ledger_doc ON inventory_ledger(source_document_type, source_document_id)",
    "CREATE INDEX IF NOT EXISTS idx_inv_ledger_branch ON inventory_ledger(branch_id, warehouse_id)",
    "CREATE INDEX IF NOT EXISTS idx_inv_ledger_type ON inventory_ledger(movement_type)",
    "CREATE INDEX IF NOT EXISTS idx_inv_ledger_lines_mv ON inventory_ledger_lines(movement_id)",
    "CREATE INDEX IF NOT EXISTS idx_inv_ledger_lines_prod ON inventory_ledger_lines(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_inv_ledger_lines_lot ON inventory_ledger_lines(lot_id)",
    "CREATE INDEX IF NOT EXISTS idx_inv_balances_prod_branch ON inventory_balances(product_id, branch_id)",
    "CREATE INDEX IF NOT EXISTS idx_inv_balances_wh ON inventory_balances(warehouse_id)",
    "CREATE INDEX IF NOT EXISTS idx_inv_audit_entity ON inventory_audit_log(entity_type, entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_inv_audit_product ON inventory_audit_log(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_inv_outbox_status ON inventory_outbox(status)",
    "CREATE INDEX IF NOT EXISTS idx_inv_settings_scope ON inventory_settings(scope_type, scope_id)",
)


def create_inventory_schema(conn) -> None:
    """Create the canonical inventory schema (idempotent). DDL lives only here."""
    for statement in _DDL:
        conn.execute(statement)
    for index in _INDEXES:
        conn.execute(index)


def drop_inventory_schema(conn) -> list[str]:
    dropped: list[str] = []
    for table in reversed(INVENTORY_TABLES):
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        dropped.append(table)
    return dropped
