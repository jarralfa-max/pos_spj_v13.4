"""Born-clean UUIDv7/Decimal schema for the Transfers bounded context.

DDL is executed only by migration 154. Quantities, weights, tolerances, and
values are decimal strings for SQLite compatibility (NUMERIC in PostgreSQL).
"""
from __future__ import annotations


TRANSFER_TABLES = (
    "stock_transfers", "stock_transfer_lines", "transfer_shipments",
    "transfer_shipment_lines", "transfer_receipts", "transfer_receipt_lines",
    "transfer_differences", "transfer_operations", "transfer_authorization_log",
    "transfer_audit_log", "transfer_outbox", "transfer_blind_receipt_counts",
    "transfer_blind_receipt_count_lines", "transfer_difference_resolutions",
    "transfer_custody_events",
    "transfer_returns", "transfer_return_lines", "transfer_return_custody_events",
    "transfer_suggestions", "transfer_suggestion_generations",
    "transfer_notification_deliveries",
    "transfer_offline_operations",
    "transfer_print_log",
)

TRANSFER_SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS stock_transfers (
        id TEXT NOT NULL PRIMARY KEY, transfer_number TEXT NOT NULL UNIQUE, transfer_type TEXT NOT NULL,
        source_channel TEXT NOT NULL, source_module TEXT NOT NULL, source_document_id TEXT,
        origin_node_type TEXT NOT NULL, origin_branch_id TEXT, origin_warehouse_id TEXT, origin_location_id TEXT,
        destination_node_type TEXT NOT NULL, destination_branch_id TEXT, destination_warehouse_id TEXT, destination_location_id TEXT,
        requested_by_user_id TEXT NOT NULL, approved_by_user_id TEXT, priority TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('DRAFT','PENDING_APPROVAL','APPROVED','RESERVATION_PENDING','RESERVED','PICKING','PARTIALLY_PICKED','PICKED','READY_TO_DISPATCH','PARTIALLY_DISPATCHED','IN_TRANSIT','PARTIALLY_RECEIVED','RECEIVED','WITH_DIFFERENCES','PENDING_RESOLUTION','RETURN_IN_PROGRESS','CLOSED','REJECTED','CANCELLED','REVERSED')),
        reason_code TEXT, business_reason TEXT, transport_required INTEGER NOT NULL DEFAULT 0,
        cold_chain_required INTEGER NOT NULL DEFAULT 0, blind_receipt_required INTEGER NOT NULL DEFAULT 0,
        operation_id TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE(source_module, source_document_id, transfer_type))''',
    '''CREATE TABLE IF NOT EXISTS stock_transfer_lines (
        id TEXT NOT NULL PRIMARY KEY, transfer_id TEXT NOT NULL REFERENCES stock_transfers(id), product_id TEXT NOT NULL,
        unit_id TEXT NOT NULL, requested_quantity TEXT NOT NULL, requested_weight TEXT NOT NULL,
        approved_quantity TEXT NOT NULL, approved_weight TEXT NOT NULL, reserved_quantity TEXT NOT NULL,
        reserved_weight TEXT NOT NULL, picked_quantity TEXT NOT NULL, picked_weight TEXT NOT NULL,
        dispatched_quantity TEXT NOT NULL, dispatched_weight TEXT NOT NULL, received_quantity TEXT NOT NULL,
        received_weight TEXT NOT NULL, accepted_quantity TEXT NOT NULL, accepted_weight TEXT NOT NULL,
        rejected_quantity TEXT NOT NULL, rejected_weight TEXT NOT NULL, pieces TEXT NOT NULL,
        lot_required INTEGER NOT NULL, quality_required INTEGER NOT NULL, temperature_required INTEGER NOT NULL,
        temperature_at_pick TEXT, notes TEXT)''',
    '''CREATE TABLE IF NOT EXISTS transfer_shipments (
        id TEXT NOT NULL PRIMARY KEY, transfer_id TEXT NOT NULL REFERENCES stock_transfers(id), shipment_number TEXT NOT NULL UNIQUE,
        dispatched_by_user_id TEXT NOT NULL, verified_by_user_id TEXT, carrier_id TEXT, vehicle_id TEXT, driver_id TEXT,
        seal_number TEXT, departure_at TEXT, expected_arrival_at TEXT, temperature_at_dispatch TEXT,
        status TEXT NOT NULL CHECK (status IN ('DRAFT','READY','DISPATCHED','IN_TRANSIT','DELIVERED','CANCELLED','RETURNED')),
        dispatch_operation_id TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL, UNIQUE(transfer_id, dispatch_operation_id))''',
    '''CREATE TABLE IF NOT EXISTS transfer_shipment_lines (
        id TEXT NOT NULL PRIMARY KEY, shipment_id TEXT NOT NULL REFERENCES transfer_shipments(id),
        transfer_line_id TEXT NOT NULL REFERENCES stock_transfer_lines(id), product_id TEXT NOT NULL,
        lot_id TEXT, location_id TEXT, quantity TEXT NOT NULL, weight TEXT NOT NULL,
        UNIQUE(shipment_id, transfer_line_id, lot_id, location_id))''',
    '''CREATE TABLE IF NOT EXISTS transfer_custody_events (
        id TEXT NOT NULL PRIMARY KEY, shipment_id TEXT NOT NULL REFERENCES transfer_shipments(id),
        event_type TEXT NOT NULL, delivered_by_user_id TEXT NOT NULL,
        received_by_user_id TEXT NOT NULL, location_id TEXT, vehicle_id TEXT,
        seal_number TEXT, temperature TEXT, evidence_reference TEXT, notes TEXT,
        occurred_at TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS transfer_receipts (
        id TEXT NOT NULL PRIMARY KEY, transfer_id TEXT NOT NULL REFERENCES stock_transfers(id),
        shipment_id TEXT NOT NULL REFERENCES transfer_shipments(id), received_by_user_id TEXT NOT NULL,
        receipt_operation_id TEXT NOT NULL UNIQUE, blind INTEGER NOT NULL DEFAULT 0, received_at TEXT NOT NULL,
        qr_reference TEXT, device_id TEXT, local_sequence INTEGER,
        sync_status TEXT NOT NULL CHECK (sync_status IN ('PENDING','CONFIRMED')),
        CHECK (sync_status = 'CONFIRMED' OR (device_id IS NOT NULL AND local_sequence > 0)),
        UNIQUE(shipment_id, receipt_operation_id))''',
    '''CREATE TABLE IF NOT EXISTS transfer_receipt_lines (
        id TEXT NOT NULL PRIMARY KEY, receipt_id TEXT NOT NULL REFERENCES transfer_receipts(id),
        transfer_line_id TEXT NOT NULL REFERENCES stock_transfer_lines(id), product_id TEXT NOT NULL,
        lot_id TEXT, observed_quantity TEXT NOT NULL, observed_weight TEXT NOT NULL,
        observed_pieces TEXT NOT NULL, temperature_at_receipt TEXT, expires_on TEXT,
        cold_chain_status TEXT NOT NULL CHECK (cold_chain_status IN ('COMPLIANT','WARNING','OUT_OF_RANGE','PENDING_QUALITY','BLOCKED')),
        accepted INTEGER NOT NULL,
        quality_status TEXT NOT NULL CHECK (quality_status IN ('AVAILABLE','PENDING_INSPECTION','QUARANTINED','QUALITY_BLOCKED','REJECTED')),
        UNIQUE(receipt_id, transfer_line_id, lot_id))''',
    '''CREATE TABLE IF NOT EXISTS transfer_blind_receipt_counts (
        id TEXT NOT NULL PRIMARY KEY, transfer_id TEXT NOT NULL REFERENCES stock_transfers(id),
        shipment_id TEXT NOT NULL REFERENCES transfer_shipments(id), receiver_user_id TEXT NOT NULL,
        start_operation_id TEXT NOT NULL UNIQUE, status TEXT NOT NULL CHECK (status IN ('CAPTURING','CONFIRMED')),
        receipt_id TEXT REFERENCES transfer_receipts(id), created_at TEXT NOT NULL, confirmed_at TEXT)''',
    '''CREATE TABLE IF NOT EXISTS transfer_blind_receipt_count_lines (
        id TEXT NOT NULL PRIMARY KEY, count_id TEXT NOT NULL REFERENCES transfer_blind_receipt_counts(id),
        transfer_line_id TEXT NOT NULL REFERENCES stock_transfer_lines(id), lot_id TEXT,
        observed_quantity TEXT NOT NULL, observed_weight TEXT NOT NULL, observed_pieces TEXT NOT NULL,
        temperature_at_receipt TEXT, expires_on TEXT, accepted INTEGER NOT NULL,
        UNIQUE(count_id, transfer_line_id, lot_id))''',
    '''CREATE TABLE IF NOT EXISTS transfer_differences (
        id TEXT NOT NULL PRIMARY KEY, transfer_id TEXT NOT NULL REFERENCES stock_transfers(id),
        transfer_line_id TEXT NOT NULL REFERENCES stock_transfer_lines(id), difference_type TEXT NOT NULL,
        expected_quantity TEXT NOT NULL, actual_quantity TEXT NOT NULL, expected_weight TEXT NOT NULL,
        actual_weight TEXT NOT NULL, difference_quantity TEXT NOT NULL, difference_weight TEXT NOT NULL,
        severity TEXT NOT NULL CHECK (severity IN ('INFO','WARNING','DANGER','CRITICAL')),
        responsible_stage TEXT NOT NULL, detected_by_user_id TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('DETECTED','PENDING_REVIEW','UNDER_INVESTIGATION','ACCEPTED','REJECTED','CLAIMED','RESOLVED','CLOSED')),
        evidence TEXT, detected_at TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS transfer_difference_resolutions (
        id TEXT NOT NULL PRIMARY KEY, difference_id TEXT NOT NULL REFERENCES transfer_differences(id),
        resolution_type TEXT NOT NULL, resolved_by_user_id TEXT NOT NULL,
        operation_id TEXT NOT NULL UNIQUE, reason TEXT NOT NULL, evidence TEXT,
        resolved_at TEXT NOT NULL, UNIQUE(difference_id, operation_id))''',
    '''CREATE TABLE IF NOT EXISTS transfer_returns (
        id TEXT NOT NULL PRIMARY KEY, transfer_id TEXT NOT NULL REFERENCES stock_transfers(id),
        return_number TEXT NOT NULL UNIQUE, reason TEXT NOT NULL,
        source_branch_id TEXT, source_warehouse_id TEXT, source_location_id TEXT,
        destination_branch_id TEXT, destination_warehouse_id TEXT, destination_location_id TEXT,
        requested_by_user_id TEXT NOT NULL, approved_by_user_id TEXT,
        dispatched_by_user_id TEXT, received_by_user_id TEXT,
        request_operation_id TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL CHECK (status IN ('REQUESTED','APPROVED','DISPATCHED','IN_TRANSIT','RECEIVED','COMPLETED','REJECTED')),
        created_at TEXT NOT NULL, completed_at TEXT)''',
    '''CREATE TABLE IF NOT EXISTS transfer_return_lines (
        id TEXT NOT NULL PRIMARY KEY, return_id TEXT NOT NULL REFERENCES transfer_returns(id),
        transfer_line_id TEXT NOT NULL REFERENCES stock_transfer_lines(id), lot_id TEXT,
        quantity TEXT NOT NULL, weight TEXT NOT NULL, pieces TEXT NOT NULL,
        dispatched_quantity TEXT NOT NULL, dispatched_weight TEXT NOT NULL,
        received_quantity TEXT NOT NULL, received_weight TEXT NOT NULL,
        UNIQUE(return_id, transfer_line_id, lot_id))''',
    '''CREATE TABLE IF NOT EXISTS transfer_return_custody_events (
        id TEXT NOT NULL PRIMARY KEY, return_id TEXT NOT NULL REFERENCES transfer_returns(id),
        event_type TEXT NOT NULL, delivered_by_user_id TEXT NOT NULL,
        received_by_user_id TEXT NOT NULL, location_id TEXT, temperature TEXT,
        evidence_reference TEXT, occurred_at TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS transfer_suggestion_generations (
        id TEXT NOT NULL PRIMARY KEY, operation_id TEXT NOT NULL UNIQUE, source_channel TEXT NOT NULL,
        source_reference_id TEXT, actor_user_id TEXT NOT NULL, generated_at TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS transfer_suggestions (
        id TEXT NOT NULL PRIMARY KEY, product_id TEXT NOT NULL, unit_id TEXT NOT NULL,
        origin_node_type TEXT NOT NULL, origin_branch_id TEXT, origin_warehouse_id TEXT, origin_location_id TEXT,
        destination_node_type TEXT NOT NULL, destination_branch_id TEXT, destination_warehouse_id TEXT, destination_location_id TEXT,
        suggested_quantity TEXT NOT NULL, origin_days_of_supply TEXT NOT NULL,
        destination_days_of_supply TEXT NOT NULL, target_days_of_supply TEXT NOT NULL,
        coefficient_of_variation TEXT NOT NULL, urgency_score TEXT NOT NULL,
        operation_id TEXT NOT NULL REFERENCES transfer_suggestion_generations(operation_id),
        source_channel TEXT NOT NULL, source_reference_id TEXT,
        status TEXT NOT NULL CHECK (status IN ('PROPOSED','ACCEPTED','DISMISSED','EXPIRED')),
        created_at TEXT NOT NULL,
        UNIQUE(operation_id, product_id, origin_node_type, origin_branch_id, origin_warehouse_id,
               origin_location_id, destination_node_type, destination_branch_id,
               destination_warehouse_id, destination_location_id))''',
    '''CREATE TABLE IF NOT EXISTS transfer_operations (
        id TEXT NOT NULL PRIMARY KEY, operation_id TEXT NOT NULL UNIQUE, transfer_id TEXT NOT NULL REFERENCES stock_transfers(id),
        operation_type TEXT NOT NULL, actor_user_id TEXT NOT NULL, device_id TEXT, local_sequence INTEGER,
        sync_status TEXT NOT NULL DEFAULT 'PENDING', occurred_at TEXT NOT NULL, UNIQUE(transfer_id, operation_id))''',
    '''CREATE TABLE IF NOT EXISTS transfer_authorization_log (
        id TEXT NOT NULL PRIMARY KEY, transfer_id TEXT NOT NULL REFERENCES stock_transfers(id), shipment_id TEXT, receipt_id TEXT,
        requested_by_user_id TEXT NOT NULL, authorized_by_user_id TEXT NOT NULL, permission_code TEXT NOT NULL,
        reason TEXT NOT NULL, operation_id TEXT NOT NULL UNIQUE, quantity TEXT, weight TEXT, device_id TEXT, authorized_at TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS transfer_audit_log (
        id TEXT NOT NULL PRIMARY KEY, transfer_id TEXT NOT NULL REFERENCES stock_transfers(id), shipment_id TEXT, receipt_id TEXT,
        user_id TEXT NOT NULL, authorized_by_user_id TEXT, operation_id TEXT NOT NULL, action TEXT NOT NULL,
        before_json TEXT, after_json TEXT, reason TEXT, branch_id TEXT, warehouse_id TEXT, product_id TEXT,
        lot_id TEXT, device_id TEXT, occurred_at TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS transfer_notification_deliveries (
        id TEXT NOT NULL PRIMARY KEY, notification_id TEXT NOT NULL UNIQUE,
        event_id TEXT NOT NULL, transfer_id TEXT NOT NULL REFERENCES stock_transfers(id),
        operation_id TEXT NOT NULL, recipient_user_id TEXT NOT NULL,
        channel TEXT NOT NULL CHECK (channel IN ('IN_APP','WHATSAPP')),
        severity TEXT NOT NULL CHECK (severity IN ('INFO','WARNING','DANGER','CRITICAL')),
        destination TEXT NOT NULL, delivered_at TEXT NOT NULL,
        UNIQUE(event_id, recipient_user_id, channel))''',
    '''CREATE TABLE IF NOT EXISTS transfer_offline_operations (
        id TEXT NOT NULL PRIMARY KEY, operation_id TEXT NOT NULL UNIQUE,
        device_id TEXT NOT NULL, local_sequence INTEGER NOT NULL CHECK (local_sequence > 0),
        transfer_id TEXT NOT NULL REFERENCES stock_transfers(id), operation_type TEXT NOT NULL,
        base_version INTEGER NOT NULL CHECK (base_version >= 0), payload_json TEXT NOT NULL,
        payload_hash TEXT NOT NULL, sync_status TEXT NOT NULL
            CHECK (sync_status IN ('PENDING','SYNCED','CONFLICT','REJECTED')),
        conflict_type TEXT CHECK (conflict_type IS NULL OR conflict_type IN
            ('SEQUENCE_GAP','PAYLOAD_MISMATCH','AGGREGATE_VERSION')),
        created_at TEXT NOT NULL, synced_at TEXT,
        UNIQUE(device_id, local_sequence))''',
    '''CREATE TABLE IF NOT EXISTS transfer_print_log (
        id TEXT NOT NULL PRIMARY KEY, operation_id TEXT NOT NULL UNIQUE,
        transfer_id TEXT NOT NULL REFERENCES stock_transfers(id),
        document_type TEXT NOT NULL CHECK (document_type IN
            ('TRANSFER','PICKING_LIST','SHIPMENT','RECEIPT','PACKAGE_LABEL')),
        document_reference TEXT NOT NULL, printer_id TEXT NOT NULL,
        copies INTEGER NOT NULL CHECK (copies BETWEEN 1 AND 10),
        printed_by_user_id TEXT NOT NULL, original_print_id TEXT REFERENCES transfer_print_log(id),
        reprint_reason TEXT, media_type TEXT NOT NULL, filename TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('PRINTED','FAILED')),
        created_at TEXT NOT NULL,
        CHECK (original_print_id IS NULL OR
               (reprint_reason IS NOT NULL AND length(trim(reprint_reason)) > 0)))''',
    '''CREATE TABLE IF NOT EXISTS transfer_outbox (
        id TEXT NOT NULL PRIMARY KEY, event_id TEXT NOT NULL UNIQUE, event_name TEXT NOT NULL, operation_id TEXT NOT NULL,
        aggregate_id TEXT NOT NULL REFERENCES stock_transfers(id), payload_json TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','DISPATCHED','DEAD_LETTER')),
        occurred_at TEXT NOT NULL, published_at TEXT, UNIQUE(operation_id, event_name, aggregate_id))''',
)

TRANSFER_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_stock_transfers_status ON stock_transfers(status, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_stock_transfers_origin ON stock_transfers(origin_branch_id, origin_warehouse_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_stock_transfers_destination ON stock_transfers(destination_branch_id, destination_warehouse_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_transfer_lines_transfer ON stock_transfer_lines(transfer_id)",
    "CREATE INDEX IF NOT EXISTS idx_transfer_shipments_transfer ON transfer_shipments(transfer_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_transfer_custody_shipment ON transfer_custody_events(shipment_id, occurred_at)",
    "CREATE INDEX IF NOT EXISTS idx_transfer_receipts_shipment ON transfer_receipts(shipment_id, received_at)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_transfer_receipts_offline_sequence ON transfer_receipts(device_id, local_sequence) WHERE device_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_blind_receipt_counts_shipment ON transfer_blind_receipt_counts(shipment_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_transfer_differences_open ON transfer_differences(transfer_id, status, severity)",
    "CREATE INDEX IF NOT EXISTS idx_transfer_difference_resolutions_difference ON transfer_difference_resolutions(difference_id, resolved_at)",
    "CREATE INDEX IF NOT EXISTS idx_transfer_returns_transfer ON transfer_returns(transfer_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_transfer_return_custody ON transfer_return_custody_events(return_id, occurred_at)",
    "CREATE INDEX IF NOT EXISTS idx_transfer_suggestions_status ON transfer_suggestions(status, urgency_score, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_transfer_suggestions_product ON transfer_suggestions(product_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_transfer_operations_sync ON transfer_operations(sync_status, device_id, local_sequence)",
    "CREATE INDEX IF NOT EXISTS idx_transfer_audit_entity ON transfer_audit_log(transfer_id, occurred_at)",
    "CREATE INDEX IF NOT EXISTS idx_transfer_notifications_transfer ON transfer_notification_deliveries(transfer_id, delivered_at)",
    "CREATE INDEX IF NOT EXISTS idx_transfer_offline_pending ON transfer_offline_operations(sync_status, device_id, local_sequence)",
    "CREATE INDEX IF NOT EXISTS idx_transfer_print_log_transfer ON transfer_print_log(transfer_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_transfer_outbox_pending ON transfer_outbox(status, occurred_at)",
)


def create_transfers_schema(connection) -> None:
    """Create the canonical schema in the caller's migration transaction."""
    for statement in TRANSFER_SCHEMA:
        connection.execute(statement)
    for index in TRANSFER_INDEXES:
        connection.execute(index)
