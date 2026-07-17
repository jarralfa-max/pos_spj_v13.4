"""PUR-4 — the procurement schema is born-clean UUIDv7 (no integer identity)."""

from backend.infrastructure.db.schema.procurement_schema import (
    PROCUREMENT_TABLES,
    create_procurement_schema,
    drop_procurement_schema,
)


def test_all_tables_created(proc_conn):
    names = {r[0] for r in proc_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    for table in PROCUREMENT_TABLES:
        assert table in names, f"falta tabla {table}"


def test_idempotent_creation(proc_conn):
    # A second create must not raise (CREATE TABLE IF NOT EXISTS).
    create_procurement_schema(proc_conn)


def test_no_integer_primary_key_identity(proc_conn):
    """Ids must be TEXT (UUIDv7), never INTEGER AUTOINCREMENT."""
    for table in PROCUREMENT_TABLES:
        cols = proc_conn.execute(f"PRAGMA table_info({table})").fetchall()
        pk_cols = [c for c in cols if c[5]]  # c[5] = pk flag
        for col in pk_cols:
            col_type = (col[2] or "").upper()
            assert "INT" not in col_type, (
                f"{table}.{col[1]} usa identidad entera ({col_type}); debe ser TEXT UUIDv7")


def test_money_columns_are_text(proc_conn):
    money_cols = {
        "direct_purchases": ("subtotal", "tax_total", "total"),
        "direct_purchase_lines": ("quantity", "unit_cost", "line_total"),
        "purchase_orders": ("total",),
        "supplier_invoices": ("total",),
    }
    for table, columns in money_cols.items():
        info = {c[1]: (c[2] or "").upper()
                for c in proc_conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for col in columns:
            assert info[col] == "TEXT", f"{table}.{col} debe ser TEXT (decimal), no REAL"


def test_direct_purchase_operation_id_unique(proc_conn):
    proc_conn.execute(
        "INSERT INTO direct_purchases (id, document_number, supplier_id, branch_id,"
        " warehouse_id, mode, payment_condition, operation_id, created_at, updated_at)"
        " VALUES ('a','CD-2026-000001','s','b','w','DIRECT_WITH_IMMEDIATE_RECEIPT',"
        " 'IMMEDIATE_PAYMENT','op-1','t','t')")
    try:
        proc_conn.execute(
            "INSERT INTO direct_purchases (id, document_number, supplier_id, branch_id,"
            " warehouse_id, mode, payment_condition, operation_id, created_at, updated_at)"
            " VALUES ('b','CD-2026-000002','s','b','w','DIRECT_WITH_IMMEDIATE_RECEIPT',"
            " 'IMMEDIATE_PAYMENT','op-1','t','t')")
        raised = False
    except Exception:
        raised = True
    assert raised, "operation_id debe ser UNIQUE (idempotencia estructural)"


def test_drop_schema_reports_tables(proc_conn):
    dropped = drop_procurement_schema(proc_conn)
    assert set(dropped) == set(PROCUREMENT_TABLES)
