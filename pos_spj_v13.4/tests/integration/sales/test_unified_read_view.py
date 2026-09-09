"""Migración 256 — `v_ventas_unificada`, la única fuente que contiene TODAS
las ventas durante la transición.

Hoy ninguna de las dos tablas las contiene: el POS escribe `sales` y no pasa
por `ventas`; la API REST, pedidos y cotizaciones escriben `ventas` y no
llegan a `sales`. Lo que se fija aquí es que la vista sume ambas SIN duplicar
la venta que ya fue respaldada por la migración 255, y que un lector repuntado
vea por fin las dos.
"""
from __future__ import annotations

import importlib
import sqlite3

import pytest

VIEW = "v_ventas_unificada"


def _schema(conn):
    conn.executescript(
        """
        CREATE TABLE usuarios (id TEXT PRIMARY KEY, nombre TEXT, usuario TEXT,
                               password_hash TEXT);
        INSERT INTO usuarios VALUES ('u-1','Ana','cajera1','x');
        CREATE TABLE ventas (
            id TEXT PRIMARY KEY, folio TEXT, sucursal_id TEXT, usuario TEXT,
            cliente_id TEXT, subtotal REAL, descuento REAL, total REAL,
            forma_pago TEXT, estado TEXT, fecha DATETIME);
        """
    )
    from backend.infrastructure.db.schema.sales_schema import create_sales_schema
    create_sales_schema(conn)


def _canonical_sale(conn, sale_id, *, customer="c-1", total="200.0",
                    status="COMPLETED", created="2026-06-01 12:00:00"):
    conn.execute(
        "INSERT INTO sales (id,branch_id,cashier_user_id,operation_id,status,"
        "sale_number,customer_id,channel,currency_code,gross_subtotal,"
        "discount_total,promotion_total,coupon_total,loyalty_total,tax_total,"
        "rounding_adjustment,total,sale_level_discount,loyalty_redeemed_amount,"
        "version,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,'0','0','0','0','0','0',"
        "?,'0','0',1,?)",
        (sale_id, "b1", "u-1", f"op-{sale_id}", status, f"F-{sale_id}", customer,
         "POS", "MXN", total, total, created))


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    _schema(c)
    importlib.import_module(
        "migrations.standalone.256_sales_unified_read_view").run(c)
    yield c
    c.close()


def _rows(conn, **where):
    sql = f"SELECT * FROM {VIEW}"
    if where:
        sql += " WHERE " + " AND ".join(f"{k}=?" for k in where)
    return {r["id"]: r for r in conn.execute(sql, tuple(where.values()))}


def test_the_view_is_created_by_the_migration(conn):
    assert conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='view' AND name=?", (VIEW,)
    ).fetchone() is not None


def test_it_contains_pos_sales_that_never_touch_the_legacy_table(conn):
    """El agujero que motiva la vista: sin ella, esta venta es invisible para
    todo lector que lea `ventas`."""
    _canonical_sale(conn, "s-pos")
    conn.commit()
    row = _rows(conn)["s-pos"]
    assert row["origen"] == "canonical"
    assert row["total"] == 200.0
    assert row["estado"] == "completada"
    assert row["usuario"] == "cajera1", "resuelve el id de cajero a su nombre"


def test_it_contains_legacy_sales_not_yet_migrated(conn):
    conn.execute(
        "INSERT INTO ventas (id,folio,sucursal_id,usuario,cliente_id,subtotal,"
        "descuento,total,forma_pago,estado,fecha) VALUES ('v-api','F-API','b1',"
        "'cajera1','c-1',50.0,0.0,50.0,'Tarjeta','completada','2026-06-02 10:00:00')")
    conn.commit()
    row = _rows(conn)["v-api"]
    assert row["origen"] == "legacy"
    assert row["total"] == 50.0
    assert row["forma_pago"] == "Tarjeta"


def test_a_backfilled_sale_appears_once_not_twice(conn):
    """La 255 copia la venta legacy al agregado. Si la vista no excluyera el
    brazo legacy para ids ya presentes, cada venta respaldada se contaría dos
    veces y todo KPI de ingresos saldría inflado."""
    conn.execute(
        "INSERT INTO ventas (id,folio,sucursal_id,usuario,cliente_id,subtotal,"
        "descuento,total,forma_pago,estado,fecha) VALUES ('v-1','F-1','b1',"
        "'cajera1','c-1',170.0,0.0,170.0,'Efectivo','completada','2026-05-01 10:00:00')")
    _canonical_sale(conn, "v-1", total="170.0", created="2026-05-01 10:00:00")
    conn.commit()

    assert conn.execute(f"SELECT COUNT(*) FROM {VIEW} WHERE id='v-1'").fetchone()[0] == 1
    assert conn.execute(f"SELECT SUM(total) FROM {VIEW}").fetchone()[0] == 170.0
    assert _rows(conn)["v-1"]["origen"] == "canonical", "gana el canónico"


def test_payment_method_comes_from_the_canonical_payments_table(conn):
    _canonical_sale(conn, "s-pay")
    conn.execute(
        "INSERT INTO sale_payments (id,sale_id,method,amount,captured_by_user_id,"
        "captured_at) VALUES ('p-1','s-pay','Tarjeta','200.0','u-1','2026-06-01 12:00:01')")
    conn.commit()
    assert _rows(conn)["s-pay"]["forma_pago"] == "Tarjeta"


def test_cancelled_status_maps_back_to_the_legacy_vocabulary(conn):
    """Los lectores filtran por `estado='completada'`; una venta cancelada no
    debe colarse en los KPIs de ingresos."""
    _canonical_sale(conn, "s-can", status="CANCELLED")
    conn.commit()
    assert _rows(conn)["s-can"]["estado"] == "cancelada"
    assert conn.execute(
        f"SELECT COUNT(*) FROM {VIEW} WHERE estado='completada'").fetchone()[0] == 0


def test_customer_history_now_sees_both_sources(conn):
    """El lector repuntado (§33 PASO 5). Antes sólo veía la venta legacy."""
    from backend.application.customers.queries.customer_history_query_service import (
        CustomerHistoryQueryService,
    )

    conn.executescript(
        "CREATE TABLE customers (id TEXT PRIMARY KEY, legacy_customer_id TEXT);"
        "INSERT INTO customers VALUES ('cm-1','c-1');"
    )
    conn.execute(
        "INSERT INTO ventas (id,folio,sucursal_id,usuario,cliente_id,subtotal,"
        "descuento,total,forma_pago,estado,fecha) VALUES ('v-api','F-API','b1',"
        "'cajera1','c-1',50.0,0.0,50.0,'Tarjeta','completada','2026-06-02 10:00:00')")
    _canonical_sale(conn, "s-pos")
    conn.commit()

    service = CustomerHistoryQueryService(conn)
    entries = service._sales_entries("cm-1")
    assert {e.source_entity_id for e in entries} == {"v-api", "s-pos"}
    assert all(e.source_module == "ventas" for e in entries)


def test_the_reader_falls_back_when_the_view_is_absent(conn):
    """Una BD que aún no aplicó la 256 sigue funcionando contra `ventas`."""
    from backend.application.customers.queries.customer_history_query_service import (
        CustomerHistoryQueryService,
    )

    conn.execute(f"DROP VIEW {VIEW}")
    conn.executescript(
        "CREATE TABLE customers (id TEXT PRIMARY KEY, legacy_customer_id TEXT);"
        "INSERT INTO customers VALUES ('cm-1','c-1');"
    )
    conn.execute(
        "INSERT INTO ventas (id,folio,sucursal_id,usuario,cliente_id,subtotal,"
        "descuento,total,forma_pago,estado,fecha) VALUES ('v-api','F-API','b1',"
        "'cajera1','c-1',50.0,0.0,50.0,'Tarjeta','completada','2026-06-02 10:00:00')")
    _canonical_sale(conn, "s-pos")
    conn.commit()

    entries = CustomerHistoryQueryService(conn)._sales_entries("cm-1")
    assert {e.source_entity_id for e in entries} == {"v-api"}


def test_migration_is_idempotent(conn):
    module = importlib.import_module("migrations.standalone.256_sales_unified_read_view")
    module.run(conn)
    module.run(conn)
    assert conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='view' AND name=?", (VIEW,)
    ).fetchone()[0] == 1
