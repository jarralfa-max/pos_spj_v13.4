"""Born-clean Logistics schema; no compatibility or rescue migration."""

DDL = (
    """CREATE TABLE IF NOT EXISTS logistics_operations (
        operation_id TEXT NOT NULL PRIMARY KEY, operation_type TEXT NOT NULL,
        result_entity_id TEXT NOT NULL, result_json TEXT NOT NULL, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS logistics_container_types (
        id TEXT NOT NULL PRIMARY KEY, code TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
        category TEXT NOT NULL, reusable INTEGER NOT NULL,
        requires_permanent_qr INTEGER NOT NULL, allows_children INTEGER NOT NULL,
        maximum_children INTEGER, maximum_depth_below INTEGER NOT NULL,
        default_tare_weight TEXT NOT NULL, maximum_gross_weight TEXT,
        maximum_net_weight TEXT, maximum_volume TEXT, stackable INTEGER NOT NULL,
        seal_required INTEGER NOT NULL, temperature_controlled INTEGER NOT NULL,
        active INTEGER NOT NULL, version INTEGER NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS logistics_container_type_compatibility (
        id TEXT NOT NULL PRIMARY KEY, parent_type_id TEXT NOT NULL REFERENCES logistics_container_types(id),
        child_type_id TEXT NOT NULL REFERENCES logistics_container_types(id),
        allowed INTEGER NOT NULL, maximum_quantity INTEGER, conditions TEXT NOT NULL,
        UNIQUE(parent_type_id, child_type_id))""",
    """CREATE TABLE IF NOT EXISTS logistics_physical_containers (
        id TEXT NOT NULL PRIMARY KEY, container_code TEXT NOT NULL UNIQUE,
        container_type_id TEXT NOT NULL REFERENCES logistics_container_types(id),
        serial_number TEXT, tare_weight TEXT NOT NULL, capacity_weight TEXT,
        capacity_volume TEXT, owner_type TEXT NOT NULL, owner_supplier_id TEXT,
        current_location_id TEXT, current_custodian_id TEXT, status TEXT NOT NULL,
        condition TEXT NOT NULL, qr_version INTEGER NOT NULL, qr_signature TEXT,
        created_at TEXT NOT NULL, last_inspection_at TEXT, retired_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS logistics_shipments (
        id TEXT NOT NULL PRIMARY KEY, shipment_number TEXT NOT NULL UNIQUE, origin_type TEXT NOT NULL,
        origin_supplier_id TEXT, origin_location TEXT NOT NULL,
        destination_branch_id TEXT NOT NULL, destination_warehouse_id TEXT NOT NULL,
        buyer_user_id TEXT NOT NULL, vehicle_id TEXT, status TEXT NOT NULL,
        operation_id TEXT NOT NULL UNIQUE, version INTEGER NOT NULL DEFAULT 0,
        started_at TEXT, sealed_at TEXT,
        dispatched_at TEXT, arrived_at TEXT, closed_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS logistics_shipment_sources (
        id TEXT NOT NULL PRIMARY KEY, shipment_id TEXT NOT NULL REFERENCES logistics_shipments(id),
        source_document_type TEXT NOT NULL, source_document_id TEXT NOT NULL,
        UNIQUE(shipment_id, source_document_type, source_document_id))""",
    """CREATE TABLE IF NOT EXISTS logistics_shipment_nodes (
        id TEXT NOT NULL PRIMARY KEY, shipment_id TEXT NOT NULL REFERENCES logistics_shipments(id),
        container_id TEXT NOT NULL REFERENCES logistics_physical_containers(id),
        parent_node_id TEXT REFERENCES logistics_shipment_nodes(id), depth INTEGER NOT NULL,
        sequence INTEGER NOT NULL, position_code TEXT, status TEXT NOT NULL,
        attached_at TEXT NOT NULL, attached_by_user_id TEXT NOT NULL,
        detached_at TEXT, detached_by_user_id TEXT, operation_id TEXT NOT NULL UNIQUE,
        UNIQUE(shipment_id, container_id))""",
    """CREATE TABLE IF NOT EXISTS logistics_shipment_contents (
        id TEXT NOT NULL PRIMARY KEY, shipment_node_id TEXT NOT NULL REFERENCES logistics_shipment_nodes(id),
        source_document_type TEXT NOT NULL, source_document_id TEXT NOT NULL,
        source_line_id TEXT NOT NULL, product_id TEXT NOT NULL,
        declared_quantity TEXT NOT NULL, declared_net_weight TEXT NOT NULL,
        purchase_unit TEXT NOT NULL, inventory_unit TEXT NOT NULL,
        conversion_factor TEXT NOT NULL, lot_number TEXT, expiration_date TEXT,
        unit_cost TEXT NOT NULL, currency_code TEXT NOT NULL, temperature TEXT,
        notes TEXT NOT NULL, operation_id TEXT NOT NULL UNIQUE)""",
    """CREATE TABLE IF NOT EXISTS logistics_container_seals (
        id TEXT NOT NULL PRIMARY KEY, seal_code TEXT NOT NULL UNIQUE, seal_type TEXT NOT NULL,
        shipment_node_id TEXT NOT NULL REFERENCES logistics_shipment_nodes(id),
        applied_by TEXT NOT NULL, applied_at TEXT NOT NULL, broken_by TEXT,
        broken_at TEXT, break_reason TEXT, photo_id TEXT,
        operation_id TEXT NOT NULL UNIQUE)""",
    """CREATE TABLE IF NOT EXISTS logistics_node_movements (
        id TEXT NOT NULL PRIMARY KEY, shipment_id TEXT NOT NULL REFERENCES logistics_shipments(id),
        node_id TEXT NOT NULL REFERENCES logistics_shipment_nodes(id),
        from_parent_node_id TEXT, to_parent_node_id TEXT, actor_user_id TEXT NOT NULL,
        reason TEXT NOT NULL, operation_id TEXT NOT NULL UNIQUE, occurred_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS logistics_container_labels (
        id TEXT NOT NULL PRIMARY KEY, container_id TEXT NOT NULL REFERENCES logistics_physical_containers(id),
        shipment_id TEXT REFERENCES logistics_shipments(id), label_type TEXT NOT NULL,
        version INTEGER NOT NULL, token TEXT NOT NULL, status TEXT NOT NULL,
        created_at TEXT NOT NULL, operation_id TEXT NOT NULL UNIQUE)""",
    """CREATE TABLE IF NOT EXISTS logistics_print_jobs (
        id TEXT NOT NULL PRIMARY KEY, label_id TEXT NOT NULL REFERENCES logistics_container_labels(id),
        printer_id TEXT NOT NULL, copies INTEGER NOT NULL, status TEXT NOT NULL,
        operation_id TEXT NOT NULL UNIQUE, requested_by_user_id TEXT NOT NULL,
        requested_at TEXT NOT NULL, reprint_reason TEXT, completed_at TEXT, error TEXT)""",
    """CREATE TABLE IF NOT EXISTS logistics_custody_events (
        id TEXT NOT NULL PRIMARY KEY, container_id TEXT NOT NULL REFERENCES logistics_physical_containers(id),
        action TEXT NOT NULL, from_custodian_id TEXT, to_custodian_id TEXT,
        location_id TEXT, actor_user_id TEXT NOT NULL, reason TEXT NOT NULL,
        operation_id TEXT NOT NULL UNIQUE, occurred_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS logistics_audit_log (
        id TEXT NOT NULL PRIMARY KEY, actor_user_id TEXT NOT NULL, branch_id TEXT,
        warehouse_id TEXT, device_id TEXT, terminal_id TEXT, operation_id TEXT NOT NULL,
        entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, action TEXT NOT NULL,
        before_json TEXT, after_json TEXT, reason TEXT NOT NULL, occurred_at TEXT NOT NULL,
        correlation_id TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS logistics_outbox (
        id TEXT NOT NULL PRIMARY KEY, event_id TEXT NOT NULL UNIQUE, event_name TEXT NOT NULL,
        aggregate_id TEXT NOT NULL, operation_id TEXT NOT NULL,
        causation_id TEXT, correlation_id TEXT NOT NULL, payload_json TEXT NOT NULL,
        status TEXT NOT NULL, attempt_count INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL, dispatched_at TEXT, last_error TEXT)""",
    """CREATE INDEX IF NOT EXISTS idx_logistics_nodes_parent
        ON logistics_shipment_nodes(shipment_id,parent_node_id,sequence)""",
)


def run(connection) -> None:
    for statement in DDL:
        connection.execute(statement)
    connection.commit()


up = run
