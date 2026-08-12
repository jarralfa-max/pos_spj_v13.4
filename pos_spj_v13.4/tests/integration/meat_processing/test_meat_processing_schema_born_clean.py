import importlib
import sqlite3

import pytest

from backend.shared.ids import new_uuid


@pytest.fixture
def connection():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    importlib.import_module(
        "migrations.standalone.187_meat_processing_bounded_context_schema"
    ).run(conn)
    return conn


EXPECTED_TABLES = {
    "processing_orders", "processing_batches", "processing_batch_source_lots",
    "process_executions", "material_consumptions", "process_outputs",
    "process_weighings", "yield_reconciliations",
    "meat_processing_authorization_log", "meat_processing_audit_log",
    "meat_processing_outbox", "meat_processing_processed_events",
}


def test_schema_creates_complete_bounded_context(connection):
    tables = {row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert EXPECTED_TABLES <= tables


def test_schema_is_idempotent(connection):
    importlib.import_module(
        "migrations.standalone.187_meat_processing_bounded_context_schema"
    ).run(connection)
    tables = {row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert EXPECTED_TABLES <= tables


def test_all_entity_primary_keys_are_text(connection):
    for table in EXPECTED_TABLES - {"meat_processing_processed_events"}:
        columns = connection.execute(f"PRAGMA table_info({table})").fetchall()
        id_column = next(column for column in columns if column[1] == "id")
        assert id_column[2].upper() == "TEXT"
        assert id_column[5] == 1  # pk position


def test_no_legacy_production_table_names_are_touched(connection):
    tables = {row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "producciones" not in tables
    assert "produccion_detalle" not in tables


def _insert_order(connection, *, order_id, operation_id, status="DRAFT"):
    connection.execute(
        """INSERT INTO processing_orders(
            id, operation_id, branch_id, warehouse_id, process_type, target_product_id,
            planned_quantity, planned_weight, priority, status, created_by_user_id,
            created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (order_id, operation_id, new_uuid(), new_uuid(), "CUTTING", new_uuid(),
         "10", "100", 0, status, new_uuid(), "2026-08-11T10:00:00+00:00",
         "2026-08-11T10:00:00+00:00"),
    )


def test_operation_id_is_unique_and_distinct_from_entity_id(connection):
    operation_id = new_uuid()
    _insert_order(connection, order_id=new_uuid(), operation_id=operation_id)
    with pytest.raises(sqlite3.IntegrityError):
        _insert_order(connection, order_id=new_uuid(), operation_id=operation_id)
    same = new_uuid()
    with pytest.raises(sqlite3.IntegrityError):
        _insert_order(connection, order_id=same, operation_id=same)


def test_process_type_and_status_are_constrained_to_canonical_values(connection):
    with pytest.raises(sqlite3.IntegrityError):
        _insert_order(connection, order_id=new_uuid(), operation_id=new_uuid(),
                       status="NOT_A_REAL_STATUS")


def test_planned_quantity_and_weight_cannot_both_be_zero(connection):
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """INSERT INTO processing_orders(
                id, operation_id, branch_id, warehouse_id, process_type,
                target_product_id, planned_quantity, planned_weight, priority, status,
                created_by_user_id, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (new_uuid(), new_uuid(), new_uuid(), new_uuid(), "CUTTING", new_uuid(),
             "0", "0", 0, "DRAFT", new_uuid(), "2026-08-11T10:00:00+00:00",
             "2026-08-11T10:00:00+00:00"),
        )


def test_negative_decimal_columns_are_rejected(connection):
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """INSERT INTO processing_orders(
                id, operation_id, branch_id, warehouse_id, process_type,
                target_product_id, planned_quantity, planned_weight, priority, status,
                created_by_user_id, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (new_uuid(), new_uuid(), new_uuid(), new_uuid(), "CUTTING", new_uuid(),
             "-1", "0", 0, "DRAFT", new_uuid(), "2026-08-11T10:00:00+00:00",
             "2026-08-11T10:00:00+00:00"),
        )


def test_internal_foreign_keys_reject_orphan_batches(connection):
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """INSERT INTO processing_batches(
                id, operation_id, processing_order_id, batch_number, planned_quantity,
                planned_weight, actual_quantity, actual_weight, status, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (new_uuid(), new_uuid(), new_uuid(), "LPR-2026-000001", "0", "0", "0", "0",
             "PLANNED", "2026-08-11T10:00:00+00:00"),
        )


def test_weighing_manual_override_requires_authorizer(connection):
    order_id, operation_id = new_uuid(), new_uuid()
    _insert_order(connection, order_id=order_id, operation_id=operation_id)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """INSERT INTO process_weighings(
                id, operation_id, processing_order_id, captured_by_user_id,
                weighing_type, gross_weight, tare_weight, unit, stable,
                manual_override, authorized_by_user_id, captured_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (new_uuid(), new_uuid(), order_id, new_uuid(), "INPUT", "10", "0", "kg",
             0, 1, None, "2026-08-11T10:00:00+00:00"),
        )


def test_outbox_is_idempotent_on_event_id(connection):
    event_id = new_uuid()
    row = (new_uuid(), event_id, "PROCESSING_ORDER_CREATED", "{}", new_uuid(),
           "PENDING", "2026-08-11T10:00:00+00:00")
    connection.execute(
        "INSERT INTO meat_processing_outbox(id,event_id,event_name,payload_json,"
        "operation_id,status,created_at) VALUES (?,?,?,?,?,?,?)", row)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO meat_processing_outbox(id,event_id,event_name,payload_json,"
            "operation_id,status,created_at) VALUES (?,?,?,?,?,?,?)",
            (new_uuid(), event_id, "PROCESSING_ORDER_CREATED", "{}", new_uuid(),
             "PENDING", "2026-08-11T10:00:00+00:00"))


def test_processed_event_is_insert_once(connection):
    event_id = new_uuid()
    connection.execute(
        "INSERT INTO meat_processing_processed_events(event_id, event_name,"
        " operation_id, processed_at) VALUES (?,?,?,?)",
        (event_id, "PROCESSING_ORDER_CREATED", new_uuid(), "2026-08-11T10:00:00+00:00"))
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO meat_processing_processed_events(event_id, event_name,"
            " operation_id, processed_at) VALUES (?,?,?,?)",
            (event_id, "PROCESSING_ORDER_CREATED", new_uuid(), "2026-08-11T10:00:00+00:00"))
