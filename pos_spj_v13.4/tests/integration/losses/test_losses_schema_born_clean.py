import importlib
import sqlite3

import pytest

from backend.domain.losses.enums import LossClassificationCode
from backend.shared.ids import is_uuidv7, new_uuid


@pytest.fixture
def connection():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    importlib.import_module(
        "migrations.standalone.174_losses_bounded_context_schema"
    ).run(conn)
    return conn


EXPECTED_TABLES = {
    "loss_classifications", "loss_reasons", "loss_cases", "loss_lines",
    "loss_evidence", "loss_valuations", "loss_cost_references", "loss_approvals", "loss_dispositions", "loss_recoveries",
    "yield_variances", "loss_investigations", "loss_investigation_findings",
    "loss_root_cause_catalog", "loss_root_cause_analyses", "loss_root_causes",
    "loss_corrective_actions", "loss_corrective_action_tasks", "loss_audit_log",
    "loss_notification_subscriptions", "loss_notification_deliveries", "loss_notification_audit",
    "loss_outbox", "loss_processed_operations",
    "loss_offline_drafts", "loss_offline_evidence", "loss_sync_outbox",
    "loss_sync_conflicts",
}


def test_losses_schema_creates_complete_bounded_context(connection):
    tables = {row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert EXPECTED_TABLES <= tables


def test_all_loss_entity_primary_keys_are_text(connection):
    for table in EXPECTED_TABLES - {"loss_processed_operations"}:
        columns = connection.execute(f"PRAGMA table_info({table})").fetchall()
        id_column = next(column for column in columns if column[1] == "id")
        assert id_column[2].upper() == "TEXT"
        assert id_column[5] == 1


def test_classification_seed_is_complete_uuidv7_and_idempotent(connection):
    migration = importlib.import_module(
        "migrations.standalone.174_losses_bounded_context_schema")
    migration.run(connection)
    rows = connection.execute("SELECT id, code FROM loss_classifications").fetchall()
    assert {row[1] for row in rows} == {item.value for item in LossClassificationCode}
    assert all(is_uuidv7(row[0]) for row in rows)


def _insert_case(connection, *, case_id, operation_id, classification_id, reason_id):
    connection.execute(
        """INSERT INTO loss_cases(
            id, operation_id, branch_id, warehouse_id, reported_by_user_id,
            classification_id, reason_id, origin, status, requires_inventory_posting,
            occurred_at, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (case_id, operation_id, new_uuid(), new_uuid(), new_uuid(),
         classification_id, reason_id, "INVENTORY", "DRAFT", 1,
         "2026-08-03T10:00:00+00:00", "2026-08-03T10:00:00+00:00",
         "2026-08-03T10:00:00+00:00"),
    )


def test_operation_id_is_unique_and_distinct_from_entity_id(connection):
    classification = connection.execute(
        "SELECT id FROM loss_classifications WHERE code='EXPIRY'").fetchone()[0]
    reason = new_uuid()
    connection.execute(
        "INSERT INTO loss_reasons(id, classification_id, code, display_name, active) VALUES (?,?,?,?,1)",
        (reason, classification, "EXPIRED", "Caducado"),
    )
    operation = new_uuid()
    _insert_case(connection, case_id=new_uuid(), operation_id=operation,
                 classification_id=classification, reason_id=reason)
    with pytest.raises(sqlite3.IntegrityError):
        _insert_case(connection, case_id=new_uuid(), operation_id=operation,
                     classification_id=classification, reason_id=reason)
    same = new_uuid()
    with pytest.raises(sqlite3.IntegrityError):
        _insert_case(connection, case_id=same, operation_id=same,
                     classification_id=classification, reason_id=reason)


def test_internal_foreign_keys_are_enforced(connection):
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO loss_lines(id, loss_case_id, product_id, quantity, weight, unit, unit_cost, recoverable_value, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (new_uuid(), new_uuid(), new_uuid(), "1", "0", "kg", "0", "0", "now"),
        )


def test_outbox_is_idempotent_and_rejects_reused_identity(connection):
    event_id, operation_id, entity_id = new_uuid(), new_uuid(), new_uuid()
    row = (new_uuid(), event_id, "LOSS_CASE_CREATED", entity_id, operation_id,
           new_uuid(), "{}", "PENDING", 0, "now")
    connection.execute(
        "INSERT INTO loss_outbox(id,event_id,event_name,aggregate_id,operation_id,correlation_id,payload_json,status,attempt_count,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        row,
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO loss_outbox(id,event_id,event_name,aggregate_id,operation_id,correlation_id,payload_json,status,attempt_count,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (new_uuid(), event_id, "LOSS_CASE_CREATED", new_uuid(), new_uuid(),
             new_uuid(), "{}", "PENDING", 0, "now"),
        )


def test_processed_operation_is_insert_once(connection):
    operation_id = new_uuid()
    connection.execute(
        "INSERT INTO loss_processed_operations(operation_id, operation_type, result_entity_id, result_json, processed_at) VALUES (?,?,?,?,?)",
        (operation_id, "CREATE", new_uuid(), "{}", "now"),
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO loss_processed_operations(operation_id, operation_type, result_entity_id, result_json, processed_at) VALUES (?,?,?,?,?)",
            (operation_id, "CREATE", new_uuid(), "{}", "now"),
        )
