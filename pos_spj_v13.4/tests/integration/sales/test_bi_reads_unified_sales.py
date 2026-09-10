"""Migración 257 + repunte de `bi_sales_query_service` a las vistas unificadas.

El agujero que esto cierra: los KPIs de ventas del dashboard leían `ventas` y
`detalles_venta`, así que NINGUNA venta del POS aparecía en ellos — desde
SALES-19..22 nacen en `sales` y no pasan por la tabla legacy.

Se fija además la parte delicada: que una venta respaldada por la migración 255
se cuente UNA vez, no dos, ni en la cabecera ni en las líneas.
"""
from __future__ import annotations

import importlib
import sqlite3
from dataclasses import dataclass

import pytest

from backend.application.analytics.queries.bi_sales_query_service import (
    BiSalesQueryService,
)


@dataclass
class _Filters:
    date_from: str = "2026-01-01"
    date_to: str = "2026-12-31"
    branch_id: str = ""
    payment_method: str = ""
    customer_id: str = ""
    category: str = ""


def _schema(conn):
    conn.executescript(
        """
        CREATE TABLE usuarios (id TEXT PRIMARY KEY, nombre TEXT, usuario TEXT,
                               password_hash TEXT);
        INSERT INTO usuarios VALUES ('u-1','Ana','cajera1','x');
        CREATE TABLE sucursales (id TEXT PRIMARY KEY, nombre TEXT);
        INSERT INTO sucursales VALUES ('b1','Matriz');
        CREATE TABLE clientes (id TEXT PRIMARY KEY, nombre TEXT);
        INSERT INTO clientes VALUES ('c-1','Cliente Uno');
        CREATE TABLE products (id TEXT PRIMARY KEY, name TEXT, category TEXT);
        INSERT INTO products VALUES ('p-1','Pollo','Aves');
        CREATE TABLE product_cost (product_id TEXT, branch_id TEXT,
                                   average_cost TEXT);
        INSERT INTO product_cost VALUES ('p-1','','40.0');

        CREATE TABLE ventas (
            id TEXT PRIMARY KEY, folio TEXT, sucursal_id TEXT, usuario TEXT,
            cliente_id TEXT, subtotal REAL, descuento REAL, total REAL,
            forma_pago TEXT, estado TEXT, fecha DATETIME);
        CREATE TABLE detalles_venta (
            id TEXT PRIMARY KEY, venta_id TEXT, producto_id TEXT, cantidad REAL,
            precio_unitario REAL, descuento REAL, subtotal REAL, unidad TEXT,
            comentarios TEXT, batch_id TEXT, costo_unitario_real REAL,
            margen_real REAL, nombre TEXT);
        """
    )
    from backend.infrastructure.db.schema.sales_schema import create_sales_schema
    create_sales_schema(conn)
    for mod in ("256_sales_unified_read_view", "257_sale_lines_unified_read_view"):
        importlib.import_module(f"migrations.standalone.{mod}").run(conn)


def _canonical_sale(conn, sale_id, *, total="100.0", created="2026-06-01 12:00:00"):
    conn.execute(
        "INSERT INTO sales (id,branch_id,cashier_user_id,operation_id,status,"
        "sale_number,customer_id,channel,currency_code,gross_subtotal,"
        "discount_total,promotion_total,coupon_total,loyalty_total,tax_total,"
        "rounding_adjustment,total,sale_level_discount,loyalty_redeemed_amount,"
        "version,created_at) VALUES (?,?,?,?,'COMPLETED',?,?,?,?,?,'0','0','0',"
        "'0','0','0',?,'0','0',1,?)",
        (sale_id, "b1", "u-1", f"op-{sale_id}", f"F-{sale_id}", "c-1", "POS",
         "MXN", total, total, created))
    conn.execute(
        "INSERT INTO sale_lines (id,sale_id,product_id,product_snapshot,quantity,"
        "quantity_unit,unit_price,discount_total,tax_total,created_at,updated_at)"
        " VALUES (?,?,?,?,?,?,?,'0','0',?,?)",
        (f"l-{sale_id}", sale_id, "p-1", '{"name":"Pollo","sku":"P1"}', "2.0",
         "kg", "50.0", created, created))


def _legacy_sale(conn, sale_id, *, total=60.0, created="2026-06-02 10:00:00"):
    conn.execute(
        "INSERT INTO ventas (id,folio,sucursal_id,usuario,cliente_id,subtotal,"
        "descuento,total,forma_pago,estado,fecha) VALUES (?,?,?,?,?,?,0.0,?,"
        "'Efectivo','completada',?)",
        (sale_id, f"F-{sale_id}", "b1", "cajera1", "c-1", total, total, created))
    conn.execute(
        "INSERT INTO detalles_venta (id,venta_id,producto_id,cantidad,"
        "precio_unitario,descuento,subtotal,unidad,costo_unitario_real,nombre)"
        " VALUES (?,?,?,?,?,0.0,?,?,0,?)",
        (f"d-{sale_id}", sale_id, "p-1", 2.0, 30.0, total, "kg", "Pollo"))


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    _schema(c)
    yield c
    c.close()


def _svc(conn):
    return BiSalesQueryService(conn)


def test_pos_sales_now_appear_in_the_dashboard_kpis(conn):
    """El agujero, en una línea: antes esto devolvía 0."""
    _canonical_sale(conn, "s-pos")
    conn.commit()
    totals = _svc(conn).sales_totals(_Filters())
    assert totals["ventas_netas"] == 100.0
    assert totals["ordenes"] == 1


def test_legacy_and_canonical_sales_are_summed_together(conn):
    _canonical_sale(conn, "s-pos")
    _legacy_sale(conn, "v-api")
    conn.commit()
    totals = _svc(conn).sales_totals(_Filters())
    assert totals["ventas_netas"] == 160.0
    assert totals["ordenes"] == 2


def test_a_backfilled_sale_is_not_double_counted(conn):
    """La 255 deja la venta en las DOS tablas. Si la vista no excluyera el
    brazo legacy, los ingresos saldrían al doble."""
    _legacy_sale(conn, "v-1", total=100.0)
    _canonical_sale(conn, "v-1", total="100.0")  # mismo id: respaldada
    conn.commit()
    totals = _svc(conn).sales_totals(_Filters())
    assert totals["ventas_netas"] == 100.0
    assert totals["ordenes"] == 1


def test_line_level_metrics_see_canonical_lines(conn):
    """Las líneas del POS también entran: antes `top_products` las ignoraba."""
    _canonical_sale(conn, "s-pos")
    conn.commit()
    top = _svc(conn).top_products(_Filters())
    assert top, "el POS debe aparecer en top de productos"
    assert top[0][0] == "Pollo"


def test_cogs_falls_back_to_canonical_product_cost_for_canonical_lines(conn):
    """`costo_unitario_real` está vacío en TODA la base (nadie lo escribe), así
    que el costo lo aporta `product_cost` — igual para líneas canónicas y
    legacy. Aquí: 2 kg * 40.0 = 80.0."""
    _canonical_sale(conn, "s-pos")
    conn.commit()
    assert _svc(conn).cost_of_goods(_Filters()) == 80.0


def test_lines_of_a_backfilled_sale_are_not_double_counted(conn):
    _legacy_sale(conn, "v-1", total=100.0)
    _canonical_sale(conn, "v-1", total="100.0")
    conn.commit()
    assert _svc(conn).cost_of_goods(_Filters()) == 80.0


def test_cancelled_sales_stay_out_of_the_kpis(conn):
    conn.execute(
        "INSERT INTO sales (id,branch_id,cashier_user_id,operation_id,status,"
        "channel,currency_code,gross_subtotal,discount_total,promotion_total,"
        "coupon_total,loyalty_total,tax_total,rounding_adjustment,total,"
        "sale_level_discount,loyalty_redeemed_amount,version,created_at) VALUES "
        "('s-can','b1','u-1','op-can','CANCELLED','POS','MXN','500','0','0','0',"
        "'0','0','0','500','0','0',1,'2026-06-03 10:00:00')")
    conn.commit()
    assert _svc(conn).sales_totals(_Filters())["ventas_netas"] == 0.0


def test_the_service_no_longer_reads_the_legacy_tables(conn):
    """Guardrail de fuente: si alguien reintroduce un `FROM ventas`, el KPI
    vuelve a perder las ventas del POS sin que nada más falle."""
    from pathlib import Path

    # Anclado al paquete, no al cwd: una ruta relativa haría que el guardrail
    # muriera con FileNotFoundError según desde dónde se lance pytest.
    root = Path(__file__).resolve().parents[3]
    source = (
        root / "backend/application/analytics/queries/bi_sales_query_service.py"
    ).read_text(encoding="utf-8")
    body = source.split('"""', 2)[2]  # fuera el docstring, que las nombra
    for legacy in ("FROM ventas ", "JOIN ventas ", "FROM detalles_venta ",
                   "JOIN detalles_venta "):
        assert legacy not in body, f"volvió a leer la tabla legacy: {legacy!r}"
    # La fuente ya no se nombra fija: se resuelve con los helpers, que
    # prefieren la vista unificada y sólo caen a la tabla legacy si la base
    # aún no aplicó las migraciones 256/257.
    assert "sales_source(self._conn)" in body
    assert "sale_lines_source(self._conn)" in body
