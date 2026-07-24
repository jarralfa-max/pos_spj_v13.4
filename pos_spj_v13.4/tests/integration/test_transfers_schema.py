import sqlite3

import pytest

from backend.infrastructure.db.schema.transfers_schema import (
    TRANSFER_INDEXES,
    TRANSFER_SCHEMA,
    TRANSFER_TABLES,
    create_transfers_schema,
)


def test_transfers_schema_is_uuid_decimal_constrained_and_indexed():
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    create_transfers_schema(connection)
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert set(TRANSFER_TABLES) <= tables
    ddl = "\n".join(TRANSFER_SCHEMA).upper()
    assert " REAL" not in ddl
    assert "AUTOINCREMENT" not in ddl
    assert "ID TEXT PRIMARY KEY" in ddl
    assert "UNIQUE(OPERATION_ID, EVENT_NAME, AGGREGATE_ID)" in ddl
    indexes = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert len([name for name in indexes if name.startswith("idx_")]) == len(TRANSFER_INDEXES)
    receipt_columns = {row[1] for row in connection.execute("PRAGMA table_info(transfer_receipts)")}
    assert {"qr_reference", "device_id", "local_sequence", "sync_status"} <= receipt_columns
    assert "idx_transfer_receipts_offline_sequence" in indexes
    receipt_line_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(transfer_receipt_lines)")
    }
    assert {"observed_pieces", "observed_weight", "temperature_at_receipt", "expires_on",
            "cold_chain_status", "quality_status"} <= receipt_line_columns
    transfer_line_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(stock_transfer_lines)")
    }
    assert {"pieces", "picked_weight", "temperature_at_pick"} <= transfer_line_columns
    custody_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(transfer_custody_events)")
    }
    assert {"shipment_id", "temperature", "seal_number", "evidence_reference"} <= custody_columns
    return_columns = {row[1] for row in connection.execute("PRAGMA table_info(transfer_returns)")}
    assert {"transfer_id", "reason", "status", "request_operation_id"} <= return_columns
    return_line_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(transfer_return_lines)")
    }
    assert {"quantity", "weight", "pieces", "dispatched_quantity",
            "received_quantity"} <= return_line_columns
    assert "idx_transfer_returns_transfer" in indexes
    suggestion_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(transfer_suggestions)")
    }
    assert {"suggested_quantity", "origin_days_of_supply", "destination_days_of_supply",
            "coefficient_of_variation", "urgency_score", "operation_id"} <= suggestion_columns
    assert "idx_transfer_suggestions_status" in indexes
    notification_columns = {
        row[1] for row in connection.execute(
            "PRAGMA table_info(transfer_notification_deliveries)")
    }
    assert {"event_id", "recipient_user_id", "channel", "severity",
            "destination", "delivered_at"} <= notification_columns
    assert "idx_transfer_notifications_transfer" in indexes
    offline_columns = {
        row[1] for row in connection.execute(
            "PRAGMA table_info(transfer_offline_operations)")
    }
    assert {"operation_id", "device_id", "local_sequence", "base_version",
            "payload_hash", "sync_status", "conflict_type"} <= offline_columns
    assert "idx_transfer_offline_pending" in indexes
    print_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(transfer_print_log)")
    }
    assert {"operation_id", "document_type", "original_print_id", "reprint_reason",
            "printer_id", "copies", "printed_by_user_id", "status"} <= print_columns
    assert "idx_transfer_print_log_transfer" in indexes
    blind_count_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(transfer_blind_receipt_counts)")
    }
    assert {"shipment_id", "receiver_user_id", "status", "receipt_id"} <= blind_count_columns
    assert "idx_blind_receipt_counts_shipment" in indexes
    resolution_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(transfer_difference_resolutions)")
    }
    assert {"difference_id", "resolution_type", "operation_id", "reason", "evidence"} <= resolution_columns
    assert "idx_transfer_difference_resolutions_difference" in indexes
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("INSERT INTO stock_transfers (id, transfer_number, transfer_type, source_channel, source_module, origin_node_type, destination_node_type, requested_by_user_id, priority, status, operation_id, created_at, updated_at) VALUES ('id','TRF','BRANCH_TO_BRANCH','MANUAL','transfers','WAREHOUSE','WAREHOUSE','user','NORMAL','INVALID','operation','now','now')")


def test_transfer_outbox_is_idempotent_by_operation_event_and_aggregate():
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    create_transfers_schema(connection)
    connection.execute("INSERT INTO stock_transfers (id, transfer_number, transfer_type, source_channel, source_module, origin_node_type, destination_node_type, requested_by_user_id, priority, status, operation_id, created_at, updated_at) VALUES ('transfer','TRF','BRANCH_TO_BRANCH','MANUAL','transfers','WAREHOUSE','WAREHOUSE','user','NORMAL','DRAFT','create-operation','now','now')")
    connection.execute("INSERT INTO transfer_outbox (id, event_id, event_name, operation_id, aggregate_id, payload_json, occurred_at) VALUES ('outbox','event','TRANSFER_REQUEST_CREATED','operation','transfer','{}','now')")
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("INSERT INTO transfer_outbox (id, event_id, event_name, operation_id, aggregate_id, payload_json, occurred_at) VALUES ('outbox-2','event-2','TRANSFER_REQUEST_CREATED','operation','transfer','{}','now')")
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("INSERT INTO transfer_outbox (id, event_id, event_name, operation_id, aggregate_id, payload_json, occurred_at) VALUES ('orphan','event-3','TRANSFER_REQUEST_SUBMITTED','other','missing','{}','now')")


def test_transfer_notification_delivery_is_idempotent_per_recipient_and_channel():
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    create_transfers_schema(connection)
    connection.execute("INSERT INTO stock_transfers (id, transfer_number, transfer_type, source_channel, source_module, origin_node_type, destination_node_type, requested_by_user_id, priority, status, operation_id, created_at, updated_at) VALUES ('transfer','TRF','BRANCH_TO_BRANCH','MANUAL','transfers','WAREHOUSE','WAREHOUSE','user','NORMAL','DRAFT','create-operation','now','now')")
    statement = "INSERT INTO transfer_notification_deliveries (id, notification_id, event_id, transfer_id, operation_id, recipient_user_id, channel, severity, destination, delivered_at) VALUES (?,?,?,?,?,?,?,?,?,?)"
    connection.execute(statement, ("delivery-1", "notification-1", "event-1", "transfer",
                                    "operation-1", "user-1", "IN_APP", "CRITICAL",
                                    "user-1", "now"))
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(statement, ("delivery-2", "notification-2", "event-1", "transfer",
                                        "operation-1", "user-1", "IN_APP", "CRITICAL",
                                        "user-1", "now"))


def test_offline_operations_are_unique_by_operation_and_device_sequence():
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    create_transfers_schema(connection)
    connection.execute("INSERT INTO stock_transfers (id, transfer_number, transfer_type, source_channel, source_module, origin_node_type, destination_node_type, requested_by_user_id, priority, status, operation_id, created_at, updated_at) VALUES ('transfer','TRF','BRANCH_TO_BRANCH','MANUAL','transfers','WAREHOUSE','WAREHOUSE','user','NORMAL','DRAFT','create-operation','now','now')")
    statement = "INSERT INTO transfer_offline_operations (id, operation_id, device_id, local_sequence, transfer_id, operation_type, base_version, payload_json, payload_hash, sync_status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)"
    connection.execute(statement, ("offline-1", "operation-1", "device-1", 1,
                                    "transfer", "RECEIVE", 0, "{}", "hash",
                                    "PENDING", "now"))
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(statement, ("offline-2", "operation-2", "device-1", 1,
                                        "transfer", "RECEIVE", 0, "{}", "hash-2",
                                        "PENDING", "now"))


def test_transfer_reprint_requires_original_and_reason():
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    create_transfers_schema(connection)
    connection.execute("INSERT INTO stock_transfers (id, transfer_number, transfer_type, source_channel, source_module, origin_node_type, destination_node_type, requested_by_user_id, priority, status, operation_id, created_at, updated_at) VALUES ('transfer','TRF','BRANCH_TO_BRANCH','MANUAL','transfers','WAREHOUSE','WAREHOUSE','user','NORMAL','DRAFT','create-operation','now','now')")
    statement = "INSERT INTO transfer_print_log (id, operation_id, transfer_id, document_type, document_reference, printer_id, copies, printed_by_user_id, original_print_id, reprint_reason, media_type, filename, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
    connection.execute(statement, ("print-1", "print-operation", "transfer", "TRANSFER",
                                    "TRF", "printer", 1, "user", None, None,
                                    "text/html", "transfer.html", "PRINTED", "now"))
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(statement, ("print-2", "reprint-operation", "transfer", "TRANSFER",
                                        "TRF", "printer", 1, "user", "print-1", None,
                                        "text/html", "transfer.html", "PRINTED", "now"))
