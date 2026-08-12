"""Meat Processing bounded context — born-clean UUIDv7 schema (PROC-3).

Rules (REGLA CERO, master prompt §9):
- Every id is ``TEXT PRIMARY KEY`` holding a lowercase UUIDv7 (PostgreSQL: UUID).
  No ``INTEGER PRIMARY KEY AUTOINCREMENT``, no ``lastrowid``.
- quantity / weight / percentage / tolerance columns are ``TEXT`` decimal strings
  (PostgreSQL: NUMERIC), each with a ``CAST(x AS NUMERIC) >= 0`` guard; no REAL —
  floats are forbidden.
- Structural idempotency: ``UNIQUE(operation_id)`` on every entity table (and
  ``operation_id <> id``, matching the domain's own invariant), ``UNIQUE(event_id)``
  in processed events.
- Status/type/classification columns are constrained with
  ``CHECK (col IN (...))`` sourced directly from ``backend.domain.meat_processing.enums``
  so the schema can never drift from the domain's canonical vocabulary.
- No legacy backfill, no rescue tables, no dual writes. This file creates only the
  new bounded-context tables — the legacy ``producciones``/``produccion_detalle``
  tables (see ``docs/refactor/PROC-0_legacy_audit.md``) are untouched here and
  keep their live readers until PROC-25.

Only a migration in ``migrations/`` may execute this DDL.
"""

from __future__ import annotations

from backend.domain.meat_processing.enums import (
    ConsumptionStatus,
    ExecutionStatus,
    OutputQualityStatus,
    OutputType,
    ProcessingBatchStatus,
    ProcessingOrderStatus,
    ProcessType,
    WeighingType,
    YieldStatus,
)


def _values(enum_type) -> str:
    return ",".join(f"'{item.value}'" for item in enum_type)


PROCESS_TYPES = _values(ProcessType)
ORDER_STATUSES = _values(ProcessingOrderStatus)
BATCH_STATUSES = _values(ProcessingBatchStatus)
EXECUTION_STATUSES = _values(ExecutionStatus)
CONSUMPTION_STATUSES = _values(ConsumptionStatus)
WEIGHING_TYPES = _values(WeighingType)
OUTPUT_TYPES = _values(OutputType)
OUTPUT_QUALITY_STATUSES = _values(OutputQualityStatus)
YIELD_STATUSES = _values(YieldStatus)

_DEC = "CAST({0} AS NUMERIC) >= 0"

#: Creation order (parents first). Drop order is the reverse.
MEAT_PROCESSING_TABLES: tuple[str, ...] = (
    "processing_orders",
    "processing_batches",
    "processing_batch_source_lots",
    "process_executions",
    "material_consumptions",
    "process_outputs",
    "process_weighings",
    "yield_reconciliations",
    "meat_processing_authorization_log",
    "meat_processing_audit_log",
    "meat_processing_outbox",
    "meat_processing_processed_events",
)

_DDL = (
    # ── processing_orders (§12/§13) ────────────────────────────────────────
    f"""
    CREATE TABLE IF NOT EXISTS processing_orders (
        id TEXT PRIMARY KEY,
        operation_id TEXT NOT NULL UNIQUE CHECK (operation_id <> id),
        branch_id TEXT NOT NULL,
        warehouse_id TEXT NOT NULL,
        production_area_id TEXT,
        work_center_id TEXT,
        process_type TEXT NOT NULL CHECK (process_type IN ({PROCESS_TYPES})),
        target_product_id TEXT NOT NULL,
        recipe_version_id TEXT,
        cutting_scheme_version_id TEXT,
        yield_profile_version_id TEXT,
        source_type TEXT,
        source_reference_id TEXT,
        planned_quantity TEXT NOT NULL DEFAULT '0' CHECK ({_DEC.format('planned_quantity')}),
        planned_weight TEXT NOT NULL DEFAULT '0' CHECK ({_DEC.format('planned_weight')}),
        scheduled_start_at TEXT,
        scheduled_end_at TEXT,
        priority INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN ({ORDER_STATUSES})),
        created_by_user_id TEXT NOT NULL,
        approved_by_user_id TEXT,
        released_by_user_id TEXT,
        started_by_user_id TEXT,
        completed_by_user_id TEXT,
        closed_by_user_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        CHECK (approved_by_user_id IS NULL OR approved_by_user_id <> created_by_user_id),
        CHECK (CAST(planned_quantity AS NUMERIC) > 0 OR CAST(planned_weight AS NUMERIC) > 0)
    )
    """,
    # ── processing_batches (§19) ────────────────────────────────────────────
    f"""
    CREATE TABLE IF NOT EXISTS processing_batches (
        id TEXT PRIMARY KEY,
        operation_id TEXT NOT NULL UNIQUE CHECK (operation_id <> id),
        processing_order_id TEXT NOT NULL REFERENCES processing_orders(id),
        batch_number TEXT NOT NULL CHECK (trim(batch_number) <> ''),
        target_lot_code TEXT,
        inventory_lot_id TEXT,
        quality_status TEXT,
        planned_quantity TEXT NOT NULL DEFAULT '0' CHECK ({_DEC.format('planned_quantity')}),
        planned_weight TEXT NOT NULL DEFAULT '0' CHECK ({_DEC.format('planned_weight')}),
        actual_quantity TEXT NOT NULL DEFAULT '0' CHECK ({_DEC.format('actual_quantity')}),
        actual_weight TEXT NOT NULL DEFAULT '0' CHECK ({_DEC.format('actual_weight')}),
        status TEXT NOT NULL DEFAULT 'PLANNED' CHECK (status IN ({BATCH_STATUSES})),
        started_at TEXT,
        completed_at TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS processing_batch_source_lots (
        id TEXT PRIMARY KEY,
        processing_batch_id TEXT NOT NULL REFERENCES processing_batches(id) ON DELETE CASCADE,
        source_lot_id TEXT NOT NULL,
        UNIQUE (processing_batch_id, source_lot_id)
    )
    """,
    # ── process_executions (§20) ────────────────────────────────────────────
    f"""
    CREATE TABLE IF NOT EXISTS process_executions (
        id TEXT PRIMARY KEY,
        operation_id TEXT NOT NULL UNIQUE CHECK (operation_id <> id),
        processing_order_id TEXT NOT NULL REFERENCES processing_orders(id),
        processing_batch_id TEXT REFERENCES processing_batches(id),
        work_center_id TEXT,
        status TEXT NOT NULL DEFAULT 'NOT_STARTED' CHECK (status IN ({EXECUTION_STATUSES})),
        started_at TEXT,
        paused_at TEXT,
        resumed_at TEXT,
        completed_at TEXT,
        total_paused_seconds TEXT NOT NULL DEFAULT '0' CHECK ({_DEC.format('total_paused_seconds')}),
        created_at TEXT NOT NULL
    )
    """,
    # ── material_consumptions (§17) — Processing requests movements, never
    # posts them itself (§39); inventory_operation_id is filled by Inventory. ──
    f"""
    CREATE TABLE IF NOT EXISTS material_consumptions (
        id TEXT PRIMARY KEY,
        operation_id TEXT NOT NULL UNIQUE CHECK (operation_id <> id),
        processing_order_id TEXT NOT NULL REFERENCES processing_orders(id),
        processing_batch_id TEXT REFERENCES processing_batches(id),
        product_id TEXT NOT NULL,
        warehouse_id TEXT NOT NULL,
        location_id TEXT,
        lot_id TEXT,
        captured_by_user_id TEXT NOT NULL,
        planned_quantity TEXT NOT NULL DEFAULT '0' CHECK ({_DEC.format('planned_quantity')}),
        planned_weight TEXT NOT NULL DEFAULT '0' CHECK ({_DEC.format('planned_weight')}),
        actual_quantity TEXT NOT NULL DEFAULT '0' CHECK ({_DEC.format('actual_quantity')}),
        actual_weight TEXT NOT NULL DEFAULT '0' CHECK ({_DEC.format('actual_weight')}),
        unit TEXT NOT NULL CHECK (trim(unit) <> ''),
        weighing_id TEXT,
        inventory_operation_id TEXT,
        status TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN ({CONSUMPTION_STATUSES})),
        consumed_at TEXT,
        created_at TEXT NOT NULL
    )
    """,
    # ── process_outputs (§22) — MAIN_PRODUCT/CO_PRODUCT/BY_PRODUCT/WASTE/… all
    # share this one table, discriminated by output_type (see PROC-2_domain.md). ──
    f"""
    CREATE TABLE IF NOT EXISTS process_outputs (
        id TEXT PRIMARY KEY,
        operation_id TEXT NOT NULL UNIQUE CHECK (operation_id <> id),
        processing_order_id TEXT NOT NULL REFERENCES processing_orders(id),
        processing_batch_id TEXT REFERENCES processing_batches(id),
        product_id TEXT NOT NULL,
        lot_id TEXT,
        warehouse_id TEXT NOT NULL,
        location_id TEXT,
        captured_by_user_id TEXT NOT NULL,
        output_type TEXT NOT NULL CHECK (output_type IN ({OUTPUT_TYPES})),
        quantity TEXT NOT NULL DEFAULT '0' CHECK ({_DEC.format('quantity')}),
        weight TEXT NOT NULL DEFAULT '0' CHECK ({_DEC.format('weight')}),
        pieces INTEGER CHECK (pieces IS NULL OR pieces >= 0),
        unit TEXT NOT NULL CHECK (trim(unit) <> ''),
        quality_status TEXT NOT NULL DEFAULT 'PENDING_INSPECTION'
            CHECK (quality_status IN ({OUTPUT_QUALITY_STATUSES})),
        inventory_operation_id TEXT,
        produced_at TEXT NOT NULL,
        CHECK (CAST(quantity AS NUMERIC) > 0 OR CAST(weight AS NUMERIC) > 0)
    )
    """,
    # ── process_weighings (§21) ─────────────────────────────────────────────
    f"""
    CREATE TABLE IF NOT EXISTS process_weighings (
        id TEXT PRIMARY KEY,
        operation_id TEXT NOT NULL UNIQUE CHECK (operation_id <> id),
        processing_order_id TEXT NOT NULL REFERENCES processing_orders(id),
        processing_batch_id TEXT REFERENCES processing_batches(id),
        captured_by_user_id TEXT NOT NULL,
        weighing_type TEXT NOT NULL CHECK (weighing_type IN ({WEIGHING_TYPES})),
        gross_weight TEXT NOT NULL CHECK ({_DEC.format('gross_weight')}),
        tare_weight TEXT NOT NULL DEFAULT '0' CHECK ({_DEC.format('tare_weight')}),
        unit TEXT NOT NULL DEFAULT 'kg' CHECK (trim(unit) <> ''),
        scale_id TEXT,
        stable INTEGER NOT NULL DEFAULT 1 CHECK (stable IN (0,1)),
        manual_override INTEGER NOT NULL DEFAULT 0 CHECK (manual_override IN (0,1)),
        authorized_by_user_id TEXT,
        source_reference TEXT,
        captured_at TEXT NOT NULL,
        CHECK (CAST(tare_weight AS NUMERIC) <= CAST(gross_weight AS NUMERIC)),
        CHECK (stable = 1 OR manual_override = 1),
        CHECK (manual_override = 0 OR authorized_by_user_id IS NOT NULL)
    )
    """,
    # ── yield_reconciliations (§26) — tolerance thresholds are never
    # hardcoded; tolerance_pct is the value actually applied, always caller-
    # supplied (see YieldReconciliationPolicy). ─────────────────────────────
    f"""
    CREATE TABLE IF NOT EXISTS yield_reconciliations (
        id TEXT PRIMARY KEY,
        operation_id TEXT NOT NULL UNIQUE CHECK (operation_id <> id),
        processing_order_id TEXT NOT NULL REFERENCES processing_orders(id),
        processing_batch_id TEXT REFERENCES processing_batches(id),
        input_quantity TEXT NOT NULL DEFAULT '0' CHECK ({_DEC.format('input_quantity')}),
        input_weight TEXT NOT NULL DEFAULT '0' CHECK ({_DEC.format('input_weight')}),
        expected_output_quantity TEXT NOT NULL DEFAULT '0' CHECK ({_DEC.format('expected_output_quantity')}),
        expected_output_weight TEXT NOT NULL DEFAULT '0' CHECK ({_DEC.format('expected_output_weight')}),
        actual_output_quantity TEXT NOT NULL DEFAULT '0' CHECK ({_DEC.format('actual_output_quantity')}),
        actual_output_weight TEXT NOT NULL DEFAULT '0' CHECK ({_DEC.format('actual_output_weight')}),
        co_product_weight TEXT NOT NULL DEFAULT '0' CHECK ({_DEC.format('co_product_weight')}),
        by_product_weight TEXT NOT NULL DEFAULT '0' CHECK ({_DEC.format('by_product_weight')}),
        waste_weight TEXT NOT NULL DEFAULT '0' CHECK ({_DEC.format('waste_weight')}),
        tolerance_pct TEXT NOT NULL CHECK ({_DEC.format('tolerance_pct')}),
        status TEXT NOT NULL DEFAULT 'PENDING_REVIEW' CHECK (status IN ({YIELD_STATUSES})),
        reviewed_by_user_id TEXT,
        calculated_at TEXT NOT NULL
    )
    """,
    # ── security / audit / outbox support tables (§48, §52, §60-62) ────────
    """
    CREATE TABLE IF NOT EXISTS meat_processing_authorization_log (
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
    CREATE TABLE IF NOT EXISTS meat_processing_audit_log (
        id TEXT PRIMARY KEY,
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        action TEXT NOT NULL,
        user_id TEXT,
        authorized_by TEXT,
        operation_id TEXT,
        before_json TEXT,
        after_json TEXT,
        reason TEXT NOT NULL DEFAULT '',
        branch_id TEXT,
        warehouse_id TEXT,
        processing_order_id TEXT,
        processing_batch_id TEXT,
        device_id TEXT,
        source_module TEXT NOT NULL DEFAULT 'meat_processing',
        occurred_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS meat_processing_outbox (
        id TEXT PRIMARY KEY,
        event_id TEXT NOT NULL UNIQUE,
        event_name TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        operation_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','DISPATCHED')),
        created_at TEXT NOT NULL,
        dispatched_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS meat_processing_processed_events (
        event_id TEXT PRIMARY KEY,
        event_name TEXT NOT NULL,
        operation_id TEXT NOT NULL,
        processed_at TEXT NOT NULL
    )
    """,
)

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_processing_orders_branch ON processing_orders(branch_id)",
    "CREATE INDEX IF NOT EXISTS idx_processing_orders_warehouse ON processing_orders(warehouse_id)",
    "CREATE INDEX IF NOT EXISTS idx_processing_orders_status ON processing_orders(status)",
    "CREATE INDEX IF NOT EXISTS idx_processing_orders_product ON processing_orders(target_product_id)",
    "CREATE INDEX IF NOT EXISTS idx_processing_batches_order ON processing_batches(processing_order_id)",
    "CREATE INDEX IF NOT EXISTS idx_processing_batches_status ON processing_batches(status)",
    "CREATE INDEX IF NOT EXISTS idx_processing_batches_number ON processing_batches(batch_number)",
    "CREATE INDEX IF NOT EXISTS idx_batch_source_lots_batch ON processing_batch_source_lots(processing_batch_id)",
    "CREATE INDEX IF NOT EXISTS idx_process_executions_order ON process_executions(processing_order_id)",
    "CREATE INDEX IF NOT EXISTS idx_process_executions_batch ON process_executions(processing_batch_id)",
    "CREATE INDEX IF NOT EXISTS idx_material_consumptions_order ON material_consumptions(processing_order_id)",
    "CREATE INDEX IF NOT EXISTS idx_material_consumptions_batch ON material_consumptions(processing_batch_id)",
    "CREATE INDEX IF NOT EXISTS idx_material_consumptions_product ON material_consumptions(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_material_consumptions_status ON material_consumptions(status)",
    "CREATE INDEX IF NOT EXISTS idx_process_outputs_order ON process_outputs(processing_order_id)",
    "CREATE INDEX IF NOT EXISTS idx_process_outputs_batch ON process_outputs(processing_batch_id)",
    "CREATE INDEX IF NOT EXISTS idx_process_outputs_product ON process_outputs(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_process_outputs_type ON process_outputs(output_type)",
    "CREATE INDEX IF NOT EXISTS idx_process_outputs_quality ON process_outputs(quality_status)",
    "CREATE INDEX IF NOT EXISTS idx_process_weighings_order ON process_weighings(processing_order_id)",
    "CREATE INDEX IF NOT EXISTS idx_process_weighings_batch ON process_weighings(processing_batch_id)",
    "CREATE INDEX IF NOT EXISTS idx_yield_reconciliations_order ON yield_reconciliations(processing_order_id)",
    "CREATE INDEX IF NOT EXISTS idx_yield_reconciliations_batch ON yield_reconciliations(processing_batch_id)",
    "CREATE INDEX IF NOT EXISTS idx_yield_reconciliations_status ON yield_reconciliations(status)",
    "CREATE INDEX IF NOT EXISTS idx_mp_audit_entity ON meat_processing_audit_log(entity_type, entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_mp_audit_order ON meat_processing_audit_log(processing_order_id)",
    "CREATE INDEX IF NOT EXISTS idx_mp_outbox_status ON meat_processing_outbox(status)",
)


def create_meat_processing_schema(conn) -> None:
    """Create the canonical Meat Processing schema (idempotent). DDL lives only here."""
    for statement in _DDL:
        conn.execute(statement)
    for index in _INDEXES:
        conn.execute(index)


def drop_meat_processing_schema(conn) -> list[str]:
    """Drop the Meat Processing bounded-context tables (dev reset). Reverse
    dependency order."""
    dropped: list[str] = []
    for table in reversed(MEAT_PROCESSING_TABLES):
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        dropped.append(table)
    return dropped
