"""Migración 255 — el histórico legacy entra al agregado canónico, y sólo lo
que de verdad es una venta.

Lo que se fija aquí no es "que copie filas", sino las cuatro decisiones que
hacen honesto el backfill:

  * los pedidos/entregas que el modelo legacy metió en `ventas` NO se migran
    (su hogar es Orders/Delivery), y no se pierden: la tabla legacy no se toca;
  * el `product_snapshot` sale de la PROPIA línea legacy, no del catálogo de
    hoy — si saliera del catálogo, sería historia inventada;
  * una fila sin identidad resoluble (sucursal o usuario) se omite en vez de
    rellenarse con `""` (§16/§17);
  * es idempotente: reejecutar no duplica.
"""
from __future__ import annotations

import importlib
import sqlite3

import pytest

MIGRATION = "migrations.standalone.255_sales_legacy_backfill"


def _legacy_schema(conn):
    conn.executescript(
        """
        CREATE TABLE sucursales (id TEXT PRIMARY KEY, nombre TEXT);
        INSERT INTO sucursales VALUES ('b1','Matriz');
        CREATE TABLE usuarios (id TEXT PRIMARY KEY, usuario TEXT);
        INSERT INTO usuarios VALUES ('u-1','cajera1');

        CREATE TABLE ventas (
            id TEXT PRIMARY KEY, folio TEXT, sucursal_id TEXT, usuario TEXT,
            cliente_id TEXT, subtotal REAL, descuento REAL, total REAL,
            forma_pago TEXT, estado TEXT, operation_id TEXT, turno_id TEXT,
            canal TEXT, source_channel TEXT, fecha DATETIME, created_at DATETIME);
        CREATE TABLE detalles_venta (
            id TEXT PRIMARY KEY, venta_id TEXT, producto_id TEXT, cantidad REAL,
            precio_unitario REAL, descuento REAL, subtotal REAL, unidad TEXT,
            comentarios TEXT, batch_id TEXT, costo_unitario_real REAL,
            margen_real REAL, nombre TEXT);
        CREATE TABLE payments (
            id TEXT PRIMARY KEY, venta_id TEXT NOT NULL, method TEXT NOT NULL,
            amount REAL NOT NULL, reference TEXT, operation_id TEXT NOT NULL,
            created_at TEXT);
        """
    )


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    _legacy_schema(c)
    from backend.infrastructure.db.schema.sales_schema import create_sales_schema
    create_sales_schema(c)

    # Una venta completada, con línea y pago reales.
    c.execute(
        "INSERT INTO ventas (id,folio,sucursal_id,usuario,cliente_id,subtotal,"
        "descuento,total,forma_pago,estado,canal,fecha) VALUES "
        "('v-1','F-1','b1','cajera1','c-1',170.0,0.0,170.0,'Efectivo',"
        "'completada','POS','2026-05-01 10:00:00')")
    c.execute(
        "INSERT INTO detalles_venta (id,venta_id,producto_id,cantidad,"
        "precio_unitario,descuento,subtotal,unidad,costo_unitario_real,nombre,batch_id)"
        " VALUES ('d-1','v-1','p-1',2.0,85.0,0.0,170.0,'kg',55.0,"
        "'Pollo kg (nombre de entonces)','lote-A')")
    c.execute(
        "INSERT INTO payments (id,venta_id,method,amount,reference,operation_id,"
        "created_at) VALUES ('pay-1','v-1','Efectivo',170.0,NULL,'op-1',"
        "'2026-05-01 10:00:05')")

    # Una cancelada.
    c.execute(
        "INSERT INTO ventas (id,sucursal_id,usuario,subtotal,descuento,total,"
        "estado,fecha) VALUES ('v-2','b1','cajera1',50.0,0.0,50.0,'cancelada',"
        "'2026-05-02 10:00:00')")
    # Un PEDIDO de WhatsApp: no es una venta.
    c.execute(
        "INSERT INTO ventas (id,sucursal_id,usuario,total,estado,fecha) VALUES "
        "('v-3','b1','cajera1',99.0,'pendiente_wa','2026-05-03 10:00:00')")
    # Una entrega en ruta: tampoco.
    c.execute(
        "INSERT INTO ventas (id,sucursal_id,usuario,total,estado,fecha) VALUES "
        "('v-4','b1','cajera1',80.0,'en_ruta','2026-05-04 10:00:00')")
    # Identidad no resoluble: usuario que no existe en `usuarios`.
    c.execute(
        "INSERT INTO ventas (id,sucursal_id,usuario,total,estado,fecha) VALUES "
        "('v-5','b1','fantasma',10.0,'completada','2026-05-05 10:00:00')")
    # Identidad no resoluble: sucursal inexistente.
    c.execute(
        "INSERT INTO ventas (id,sucursal_id,usuario,total,estado,fecha) VALUES "
        "('v-6','b-inexistente','cajera1',10.0,'completada','2026-05-06 10:00:00')")
    c.commit()
    yield c
    c.close()


def _run(conn):
    importlib.import_module(MIGRATION).run(conn)


def _ids(conn, table="sales"):
    return {r[0] for r in conn.execute(f"SELECT id FROM {table}")}


def test_only_real_sales_are_migrated(conn):
    _run(conn)
    assert _ids(conn) == {"v-1", "v-2"}


def test_orders_and_deliveries_are_left_alone_not_lost(conn):
    """`pendiente_wa` y `en_ruta` son pedidos: su hogar es Orders/Delivery.
    No entran al agregado y siguen intactos en la tabla legacy."""
    _run(conn)
    assert "v-3" not in _ids(conn)
    assert "v-4" not in _ids(conn)
    legacy = {r[0] for r in conn.execute("SELECT id FROM ventas")}
    assert {"v-3", "v-4"} <= legacy, "la migración no debe tocar la tabla legacy"


def test_rows_without_resolvable_identity_are_skipped_not_faked(conn):
    """§16/§17: antes que inventar `branch_id=''` o meter un nombre de usuario
    en una columna `*_user_id`, se omite la fila."""
    _run(conn)
    assert "v-5" not in _ids(conn), "usuario no resoluble"
    assert "v-6" not in _ids(conn), "sucursal inexistente"


def test_status_and_timestamps_map_to_the_domain_enum(conn):
    _run(conn)
    rows = {r["id"]: r for r in conn.execute(
        "SELECT id, status, completed_at, cancelled_at FROM sales")}
    assert rows["v-1"]["status"] == "COMPLETED"
    assert rows["v-1"]["completed_at"] == "2026-05-01 10:00:00"
    assert rows["v-1"]["cancelled_at"] is None
    assert rows["v-2"]["status"] == "CANCELLED"
    assert rows["v-2"]["cancelled_at"] == "2026-05-02 10:00:00"
    assert rows["v-2"]["completed_at"] is None


def test_money_lands_as_decimal_text_never_float(conn):
    _run(conn)
    row = conn.execute(
        "SELECT gross_subtotal, total, typeof(total) AS t FROM sales WHERE id='v-1'"
    ).fetchone()
    assert row["t"] == "text"
    assert row["gross_subtotal"] == "170.0"
    assert row["total"] == "170.0"


def test_product_snapshot_comes_from_the_legacy_line_not_todays_catalog(conn):
    """El corazón de la fidelidad: el nombre y el precio guardados son los que
    la línea registró entonces. Si el snapshot se tomara del catálogo actual,
    este nombre no aparecería."""
    import json

    _run(conn)
    line = conn.execute(
        "SELECT product_snapshot, quantity, quantity_unit, unit_price, lot_reference"
        " FROM sale_lines WHERE sale_id='v-1'").fetchone()
    snapshot = json.loads(line["product_snapshot"])
    assert snapshot["name"] == "Pollo kg (nombre de entonces)"
    assert snapshot["unit_price"] == "85.0"
    assert snapshot["unit_cost"] == "55.0"
    assert snapshot["source"] == "legacy_backfill"
    assert line["quantity"] == "2.0"
    assert line["quantity_unit"] == "kg"
    assert line["lot_reference"] == "lote-A"


def test_existing_payments_are_migrated_and_none_are_invented(conn):
    """Sólo se migran los pagos que EXISTEN. El `forma_pago` de la cabecera no
    es un registro de pago: v-2 no tiene fila en `payments` y no debe ganar
    una inventada."""
    _run(conn)
    pagos = {r["sale_id"]: r for r in conn.execute("SELECT * FROM sale_payments")}
    assert set(pagos) == {"v-1"}
    assert pagos["v-1"]["amount"] == "170.0"
    assert pagos["v-1"]["captured_by_user_id"] == "u-1"


def test_backfill_is_idempotent(conn):
    _run(conn)
    _run(conn)
    _run(conn)
    assert len(_ids(conn)) == 2
    assert conn.execute("SELECT COUNT(*) FROM sale_lines").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM sale_payments").fetchone()[0] == 1


def test_backfilled_rows_are_identifiable(conn):
    """Reversibilidad: las filas insertadas se distinguen por su operation_id."""
    _run(conn)
    ops = {r[0] for r in conn.execute("SELECT operation_id FROM sales")}
    assert ops == {"legacy-backfill:v-1", "legacy-backfill:v-2"}


def test_a_sale_already_in_the_canonical_table_is_never_overwritten(conn):
    """Una venta del POS canónico con el mismo id no se pisa."""
    conn.execute(
        "INSERT INTO sales (id,branch_id,cashier_user_id,operation_id,status,"
        "channel,currency_code,gross_subtotal,discount_total,promotion_total,"
        "coupon_total,loyalty_total,tax_total,rounding_adjustment,total,"
        "sale_level_discount,loyalty_redeemed_amount,version,created_at) VALUES "
        "('v-1','b1','u-1','op-pos','COMPLETED','POS','MXN','1','0','0','0','0',"
        "'0','0','1','0','0',7,'2026-05-01')")
    conn.commit()
    _run(conn)
    row = conn.execute("SELECT operation_id, version FROM sales WHERE id='v-1'").fetchone()
    assert row["operation_id"] == "op-pos"
    assert row["version"] == 7
