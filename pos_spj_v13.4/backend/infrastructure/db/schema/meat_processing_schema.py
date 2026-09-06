"""Meat Processing bounded context — born-clean UUIDv7 schema (PROC-3).

Rules (REGLA CERO, master prompt §9):
- Every id is ``TEXT NOT NULL PRIMARY KEY`` holding a lowercase UUIDv7 (PostgreSQL: UUID).
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
    EquipmentStatus,
    ExecutionStatus,
    IncidentStatus,
    IncidentType,
    MaterialRequirementStatus,
    OperatorRole,
    OutputQualityStatus,
    OutputType,
    ProcessingBatchStatus,
    ProcessingOrderStatus,
    ProcessType,
    ReworkOrderStatus,
    ReworkOrigin,
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
MATERIAL_REQUIREMENT_STATUSES = _values(MaterialRequirementStatus)
OPERATOR_ROLES = _values(OperatorRole)
INCIDENT_TYPES = _values(IncidentType)
INCIDENT_STATUSES = _values(IncidentStatus)
REWORK_ORIGINS = _values(ReworkOrigin)
REWORK_ORDER_STATUSES = _values(ReworkOrderStatus)
EQUIPMENT_STATUSES = _values(EquipmentStatus)

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
    # ── PROC-7/PROC-8 (248) ──────────────────────────────────────────────
    "material_requirements",
    "operator_assignments",
    "process_step_executions",
    "process_incidents",
    # ── PROC-13 (249) ────────────────────────────────────────────────────
    "packaging_executions",
    "production_labels",
    # ── PROC-17 (250) ────────────────────────────────────────────────────
    "rework_orders",
    # ── PROC-18 (251) ────────────────────────────────────────────────────
    "process_genealogy_links",
    # ── PROC-19 (252) ────────────────────────────────────────────────────
    "production_areas",
    "work_centers",
    "production_stations",
    "production_equipment",
    "equipment_assignments",
)

_DDL = (
    # ── processing_orders (§12/§13) ────────────────────────────────────────
    f"""
    CREATE TABLE IF NOT EXISTS processing_orders (
        id TEXT NOT NULL PRIMARY KEY,
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
        id TEXT NOT NULL PRIMARY KEY,
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
        id TEXT NOT NULL PRIMARY KEY,
        processing_batch_id TEXT NOT NULL REFERENCES processing_batches(id) ON DELETE CASCADE,
        source_lot_id TEXT NOT NULL,
        UNIQUE (processing_batch_id, source_lot_id)
    )
    """,
    # ── process_executions (§20) ────────────────────────────────────────────
    f"""
    CREATE TABLE IF NOT EXISTS process_executions (
        id TEXT NOT NULL PRIMARY KEY,
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
        id TEXT NOT NULL PRIMARY KEY,
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
        id TEXT NOT NULL PRIMARY KEY,
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
        id TEXT NOT NULL PRIMARY KEY,
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
        id TEXT NOT NULL PRIMARY KEY,
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
        id TEXT NOT NULL PRIMARY KEY,
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
        id TEXT NOT NULL PRIMARY KEY,
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
        id TEXT NOT NULL PRIMARY KEY,
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
        event_id TEXT NOT NULL PRIMARY KEY,
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


# ── PROC-7 (Preparación) / PROC-8 (Ejecución) — migration 248 ──────────────
# Kept as a separate DDL group + function so migration 187 stays exactly as
# documented in MIGRATION_LOG.md; migration 248 calls only this one.
_DDL_PREPARATION_EXECUTION = (
    # ── material_requirements (§16) ─────────────────────────────────────────
    f"""
    CREATE TABLE IF NOT EXISTS material_requirements (
        id TEXT NOT NULL PRIMARY KEY,
        operation_id TEXT NOT NULL UNIQUE CHECK (operation_id <> id),
        processing_order_id TEXT NOT NULL REFERENCES processing_orders(id),
        product_id TEXT NOT NULL,
        required_quantity TEXT NOT NULL DEFAULT '0' CHECK ({_DEC.format('required_quantity')}),
        required_weight TEXT NOT NULL DEFAULT '0' CHECK ({_DEC.format('required_weight')}),
        unit TEXT NOT NULL CHECK (trim(unit) <> ''),
        substitution_allowed INTEGER NOT NULL DEFAULT 0 CHECK (substitution_allowed IN (0,1)),
        quality_required INTEGER NOT NULL DEFAULT 0 CHECK (quality_required IN (0,1)),
        lot_required INTEGER NOT NULL DEFAULT 0 CHECK (lot_required IN (0,1)),
        status TEXT NOT NULL DEFAULT 'REQUIRED' CHECK (status IN ({MATERIAL_REQUIREMENT_STATUSES})),
        reserved_quantity TEXT NOT NULL DEFAULT '0' CHECK ({_DEC.format('reserved_quantity')}),
        reserved_weight TEXT NOT NULL DEFAULT '0' CHECK ({_DEC.format('reserved_weight')}),
        allocated_quantity TEXT NOT NULL DEFAULT '0' CHECK ({_DEC.format('allocated_quantity')}),
        allocated_weight TEXT NOT NULL DEFAULT '0' CHECK ({_DEC.format('allocated_weight')}),
        consumed_quantity TEXT NOT NULL DEFAULT '0' CHECK ({_DEC.format('consumed_quantity')}),
        consumed_weight TEXT NOT NULL DEFAULT '0' CHECK ({_DEC.format('consumed_weight')}),
        created_at TEXT NOT NULL
    )
    """,
    # ── operator_assignments (§32) ──────────────────────────────────────────
    f"""
    CREATE TABLE IF NOT EXISTS operator_assignments (
        id TEXT NOT NULL PRIMARY KEY,
        operation_id TEXT NOT NULL UNIQUE CHECK (operation_id <> id),
        processing_order_id TEXT NOT NULL REFERENCES processing_orders(id),
        user_id TEXT NOT NULL,
        role_type TEXT NOT NULL CHECK (role_type IN ({OPERATOR_ROLES})),
        work_center_id TEXT,
        assigned_at TEXT NOT NULL,
        released_at TEXT
    )
    """,
    # ── process_step_executions (§20) ───────────────────────────────────────
    f"""
    CREATE TABLE IF NOT EXISTS process_step_executions (
        id TEXT NOT NULL PRIMARY KEY,
        operation_id TEXT NOT NULL UNIQUE CHECK (operation_id <> id),
        process_execution_id TEXT NOT NULL REFERENCES process_executions(id),
        step_name TEXT NOT NULL CHECK (trim(step_name) <> ''),
        sequence INTEGER NOT NULL DEFAULT 0 CHECK (sequence >= 0),
        status TEXT NOT NULL DEFAULT 'NOT_STARTED' CHECK (status IN ({EXECUTION_STATUSES})),
        started_at TEXT,
        completed_at TEXT,
        created_at TEXT NOT NULL
    )
    """,
    # ── process_incidents (§30) ─────────────────────────────────────────────
    f"""
    CREATE TABLE IF NOT EXISTS process_incidents (
        id TEXT NOT NULL PRIMARY KEY,
        operation_id TEXT NOT NULL UNIQUE CHECK (operation_id <> id),
        processing_order_id TEXT NOT NULL REFERENCES processing_orders(id),
        process_execution_id TEXT REFERENCES process_executions(id),
        incident_type TEXT NOT NULL CHECK (incident_type IN ({INCIDENT_TYPES})),
        status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ({INCIDENT_STATUSES})),
        reported_by_user_id TEXT NOT NULL,
        description TEXT NOT NULL CHECK (trim(description) <> ''),
        reported_at TEXT NOT NULL,
        resolved_by_user_id TEXT,
        resolved_at TEXT,
        resolution_notes TEXT NOT NULL DEFAULT ''
    )
    """,
)

_INDEXES_PREPARATION_EXECUTION = (
    "CREATE INDEX IF NOT EXISTS idx_material_requirements_order ON material_requirements(processing_order_id)",
    "CREATE INDEX IF NOT EXISTS idx_material_requirements_product ON material_requirements(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_material_requirements_status ON material_requirements(status)",
    "CREATE INDEX IF NOT EXISTS idx_operator_assignments_order ON operator_assignments(processing_order_id)",
    "CREATE INDEX IF NOT EXISTS idx_operator_assignments_user ON operator_assignments(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_process_step_executions_execution ON process_step_executions(process_execution_id)",
    "CREATE INDEX IF NOT EXISTS idx_process_incidents_order ON process_incidents(processing_order_id)",
    "CREATE INDEX IF NOT EXISTS idx_process_incidents_status ON process_incidents(status)",
)


def create_meat_processing_preparation_execution_schema(conn) -> None:
    """Create the PROC-7/PROC-8 tables (idempotent). Called by migration 248."""
    for statement in _DDL_PREPARATION_EXECUTION:
        conn.execute(statement)
    for index in _INDEXES_PREPARATION_EXECUTION:
        conn.execute(index)


# ── PROC-13 (Empaque) — migration 249 ───────────────────────────────────────
_DDL_PACKAGING = (
    # ── packaging_executions (§25) — immutable capture, no status/workflow ──
    f"""
    CREATE TABLE IF NOT EXISTS packaging_executions (
        id TEXT NOT NULL PRIMARY KEY,
        operation_id TEXT NOT NULL UNIQUE CHECK (operation_id <> id),
        processing_order_id TEXT NOT NULL REFERENCES processing_orders(id),
        process_output_id TEXT REFERENCES process_outputs(id),
        product_id TEXT NOT NULL,
        lot_id TEXT,
        packaging_material_id TEXT NOT NULL,
        package_quantity INTEGER NOT NULL CHECK (package_quantity > 0),
        net_weight TEXT NOT NULL CHECK (CAST(net_weight AS NUMERIC) > 0),
        gross_weight TEXT NOT NULL CHECK (CAST(gross_weight AS NUMERIC) > 0),
        tare_weight TEXT NOT NULL DEFAULT '0' CHECK ({_DEC.format('tare_weight')}),
        packaged_by_user_id TEXT NOT NULL,
        production_date TEXT NOT NULL,
        expiration_date TEXT,
        packaged_at TEXT NOT NULL,
        CHECK (CAST(tare_weight AS NUMERIC) <= CAST(gross_weight AS NUMERIC)),
        CHECK (CAST(net_weight AS NUMERIC) <= CAST(gross_weight AS NUMERIC))
    )
    """,
    # ── production_labels (§25) ─────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS production_labels (
        id TEXT NOT NULL PRIMARY KEY,
        operation_id TEXT NOT NULL UNIQUE CHECK (operation_id <> id),
        packaging_execution_id TEXT NOT NULL REFERENCES packaging_executions(id),
        label_template_id TEXT NOT NULL,
        barcode TEXT NOT NULL CHECK (trim(barcode) <> ''),
        qr_traceability_reference TEXT NOT NULL CHECK (trim(qr_traceability_reference) <> ''),
        printed_at TEXT,
        printed_by_user_id TEXT,
        reprint_count INTEGER NOT NULL DEFAULT 0 CHECK (reprint_count >= 0),
        created_at TEXT NOT NULL
    )
    """,
)

_INDEXES_PACKAGING = (
    "CREATE INDEX IF NOT EXISTS idx_packaging_executions_order ON packaging_executions(processing_order_id)",
    "CREATE INDEX IF NOT EXISTS idx_packaging_executions_output ON packaging_executions(process_output_id)",
    "CREATE INDEX IF NOT EXISTS idx_production_labels_packaging ON production_labels(packaging_execution_id)",
)


def create_meat_processing_packaging_schema(conn) -> None:
    """Create the PROC-13 tables (idempotent). Called by migration 249."""
    for statement in _DDL_PACKAGING:
        conn.execute(statement)
    for index in _INDEXES_PACKAGING:
        conn.execute(index)


# ── PROC-17 (Reprocesos) — migration 250 ────────────────────────────────────
_DDL_REWORK = (
    # ── rework_orders (§29) — never touches the source order/output directly;
    # links to a *new* processing_orders row that executes the rework. ──────
    f"""
    CREATE TABLE IF NOT EXISTS rework_orders (
        id TEXT NOT NULL PRIMARY KEY,
        operation_id TEXT NOT NULL UNIQUE CHECK (operation_id <> id),
        source_output_id TEXT NOT NULL REFERENCES process_outputs(id),
        product_id TEXT NOT NULL,
        origin TEXT NOT NULL CHECK (origin IN ({REWORK_ORIGINS})),
        quantity TEXT NOT NULL DEFAULT '0' CHECK ({_DEC.format('quantity')}),
        weight TEXT NOT NULL DEFAULT '0' CHECK ({_DEC.format('weight')}),
        reason TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'CREATED' CHECK (status IN ({REWORK_ORDER_STATUSES})),
        created_by_user_id TEXT NOT NULL,
        approved_by_user_id TEXT,
        processing_order_id TEXT REFERENCES processing_orders(id),
        created_at TEXT NOT NULL,
        CHECK (approved_by_user_id IS NULL OR approved_by_user_id <> created_by_user_id),
        CHECK (CAST(quantity AS NUMERIC) > 0 OR CAST(weight AS NUMERIC) > 0)
    )
    """,
)

_INDEXES_REWORK = (
    "CREATE INDEX IF NOT EXISTS idx_rework_orders_source_output ON rework_orders(source_output_id)",
    "CREATE INDEX IF NOT EXISTS idx_rework_orders_status ON rework_orders(status)",
    "CREATE INDEX IF NOT EXISTS idx_rework_orders_processing_order ON rework_orders(processing_order_id)",
)


def create_meat_processing_rework_schema(conn) -> None:
    """Create the PROC-17 table (idempotent). Called by migration 250."""
    for statement in _DDL_REWORK:
        conn.execute(statement)
    for index in _INDEXES_REWORK:
        conn.execute(index)


# ── PROC-18 (Trazabilidad) — migration 251 ──────────────────────────────────
_DDL_GENEALOGY = (
    # ── process_genealogy_links (§38) — polymorphic edge; no single-table FK
    # is possible for upstream/downstream_entity_id (they can point at
    # process_outputs, material_consumptions, etc.), so none is declared. ───
    f"""
    CREATE TABLE IF NOT EXISTS process_genealogy_links (
        id TEXT NOT NULL PRIMARY KEY,
        operation_id TEXT NOT NULL UNIQUE CHECK (operation_id <> id),
        upstream_entity_type TEXT NOT NULL CHECK (trim(upstream_entity_type) <> ''),
        upstream_entity_id TEXT NOT NULL,
        downstream_entity_type TEXT NOT NULL CHECK (trim(downstream_entity_type) <> ''),
        downstream_entity_id TEXT NOT NULL,
        product_id TEXT NOT NULL,
        lot_id TEXT,
        quantity TEXT NOT NULL DEFAULT '0' CHECK ({_DEC.format('quantity')}),
        weight TEXT NOT NULL DEFAULT '0' CHECK ({_DEC.format('weight')}),
        linked_by_user_id TEXT NOT NULL,
        linked_at TEXT NOT NULL
    )
    """,
)

_INDEXES_GENEALOGY = (
    "CREATE INDEX IF NOT EXISTS idx_genealogy_links_upstream ON process_genealogy_links(upstream_entity_type, upstream_entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_genealogy_links_downstream ON process_genealogy_links(downstream_entity_type, downstream_entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_genealogy_links_lot ON process_genealogy_links(lot_id)",
    "CREATE INDEX IF NOT EXISTS idx_genealogy_links_product ON process_genealogy_links(product_id)",
)


def create_meat_processing_genealogy_schema(conn) -> None:
    """Create the PROC-18 table (idempotent). Called by migration 251."""
    for statement in _DDL_GENEALOGY:
        conn.execute(statement)
    for index in _INDEXES_GENEALOGY:
        conn.execute(index)


# ── PROC-19 (Recursos y capacidad) — migration 252 ──────────────────────────
# área → centro de trabajo → estación → equipo. processing_orders.production_area_id/
# .work_center_id (and process_executions/operator_assignments.work_center_id)
# predate this table and stay soft (unvalidated TEXT) references — SQLite can't
# add a FK to an existing column without a full table rebuild, so referential
# integrity there is an application-layer concern, not enforced here.
_DDL_RESOURCES = (
    f"""
    CREATE TABLE IF NOT EXISTS production_areas (
        id TEXT NOT NULL PRIMARY KEY,
        branch_id TEXT NOT NULL,
        warehouse_id TEXT NOT NULL,
        code TEXT NOT NULL CHECK (trim(code) <> ''),
        name TEXT NOT NULL CHECK (trim(name) <> ''),
        is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
        created_at TEXT NOT NULL,
        UNIQUE (branch_id, code)
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS work_centers (
        id TEXT NOT NULL PRIMARY KEY,
        production_area_id TEXT NOT NULL REFERENCES production_areas(id),
        code TEXT NOT NULL CHECK (trim(code) <> ''),
        name TEXT NOT NULL CHECK (trim(name) <> ''),
        capacity_per_hour TEXT NOT NULL DEFAULT '0' CHECK ({_DEC.format('capacity_per_hour')}),
        capacity_basis TEXT NOT NULL DEFAULT 'weight' CHECK (capacity_basis IN ('quantity','weight')),
        is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
        created_at TEXT NOT NULL,
        UNIQUE (production_area_id, code)
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS production_stations (
        id TEXT NOT NULL PRIMARY KEY,
        work_center_id TEXT NOT NULL REFERENCES work_centers(id),
        code TEXT NOT NULL CHECK (trim(code) <> ''),
        name TEXT NOT NULL CHECK (trim(name) <> ''),
        is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
        created_at TEXT NOT NULL,
        UNIQUE (work_center_id, code)
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS production_equipment (
        id TEXT NOT NULL PRIMARY KEY,
        work_center_id TEXT NOT NULL REFERENCES work_centers(id),
        station_id TEXT REFERENCES production_stations(id),
        code TEXT NOT NULL CHECK (trim(code) <> ''),
        name TEXT NOT NULL CHECK (trim(name) <> ''),
        equipment_type TEXT NOT NULL CHECK (trim(equipment_type) <> ''),
        status TEXT NOT NULL DEFAULT 'AVAILABLE' CHECK (status IN ({EQUIPMENT_STATUSES})),
        last_maintenance_at TEXT,
        created_at TEXT NOT NULL,
        UNIQUE (work_center_id, code)
    )
    """,
    # ── equipment_assignments (§19) — structural twin of operator_assignments ──
    """
    CREATE TABLE IF NOT EXISTS equipment_assignments (
        id TEXT NOT NULL PRIMARY KEY,
        operation_id TEXT NOT NULL UNIQUE CHECK (operation_id <> id),
        processing_order_id TEXT NOT NULL REFERENCES processing_orders(id),
        equipment_id TEXT NOT NULL REFERENCES production_equipment(id),
        assigned_at TEXT NOT NULL,
        released_at TEXT
    )
    """,
)

_INDEXES_RESOURCES = (
    "CREATE INDEX IF NOT EXISTS idx_production_areas_branch ON production_areas(branch_id)",
    "CREATE INDEX IF NOT EXISTS idx_work_centers_area ON work_centers(production_area_id)",
    "CREATE INDEX IF NOT EXISTS idx_production_stations_work_center ON production_stations(work_center_id)",
    "CREATE INDEX IF NOT EXISTS idx_production_equipment_work_center ON production_equipment(work_center_id)",
    "CREATE INDEX IF NOT EXISTS idx_production_equipment_station ON production_equipment(station_id)",
    "CREATE INDEX IF NOT EXISTS idx_production_equipment_status ON production_equipment(status)",
    "CREATE INDEX IF NOT EXISTS idx_equipment_assignments_order ON equipment_assignments(processing_order_id)",
    "CREATE INDEX IF NOT EXISTS idx_equipment_assignments_equipment ON equipment_assignments(equipment_id)",
)


def create_meat_processing_resources_schema(conn) -> None:
    """Create the PROC-19 tables (idempotent). Called by migration 252."""
    for statement in _DDL_RESOURCES:
        conn.execute(statement)
    for index in _INDEXES_RESOURCES:
        conn.execute(index)


def drop_meat_processing_schema(conn) -> list[str]:
    """Drop the Meat Processing bounded-context tables (dev reset). Reverse
    dependency order."""
    dropped: list[str] = []
    for table in reversed(MEAT_PROCESSING_TABLES):
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        dropped.append(table)
    return dropped
