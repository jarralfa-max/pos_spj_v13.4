"""Los lectores de la capa canónica leen las vistas unificadas, no `ventas`.

§5: `backend/application` no debe depender de la persistencia legacy. Pero el
motivo aquí no es de pureza: leer `ventas` dejaba fuera TODAS las ventas del
POS, que desde SALES-19..22 nacen en `sales`. En la práctica eso significaba
un forecast ciego a la demanda del POS, una elasticidad de precios estimada
sobre media muestra y una planeación de compras que no veía lo que se vendió
en mostrador.

Se prueba con datos, no sólo con el texto del SQL: cada servicio debe devolver
la venta canónica.
"""
from __future__ import annotations

import ast
import importlib
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]

# Lectores de la capa canónica repuntados. `sales_read_repository.py` NO está
# aquí a propósito: su comentario explica que pide `efectivo_recibido`/`cambio`
# (que el agregado no guarda) y ordena por `rowid` (que una vista no tiene).
REPOINTED = (
    "backend/application/analytics/queries/bi_sales_query_service.py",
    "backend/application/analytics/queries/bi_dashboard_query_service.py",
    "backend/application/analytics/queries/bi_forecast_query_service.py",
    "backend/application/analytics/queries/price_history_query_service.py",
    "backend/application/queries/purchase_planning_query_service.py",
    "backend/infrastructure/db/repositories/forecasting/sqlite_time_series_reader.py",
)


def _schema(conn):
    conn.executescript(
        """
        CREATE TABLE usuarios (id TEXT PRIMARY KEY, nombre TEXT, usuario TEXT,
                               password_hash TEXT);
        INSERT INTO usuarios VALUES ('u-1','Ana','cajera1','x');
        CREATE TABLE sucursales (id TEXT PRIMARY KEY, nombre TEXT, activa INTEGER
                                 DEFAULT 1);
        INSERT INTO sucursales VALUES ('b1','Matriz',1);
        CREATE TABLE products (id TEXT PRIMARY KEY, name TEXT, category_id TEXT,
                               base_unit_id TEXT);
        INSERT INTO products VALUES ('p-1','Pollo',NULL,'kg');
        CREATE TABLE product_categories (id TEXT PRIMARY KEY, name TEXT,
                                         active INTEGER DEFAULT 1);
        CREATE TABLE product_cost (product_id TEXT, branch_id TEXT,
                                   average_cost TEXT);
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


@pytest.fixture
def conn():
    """Una ÚNICA venta, y es del POS (canónica). Cualquier lector que siga
    leyendo `ventas` devolverá vacío."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    _schema(c)
    fecha = "2026-06-01 12:00:00"
    c.execute(
        "INSERT INTO sales (id,branch_id,cashier_user_id,operation_id,status,"
        "sale_number,customer_id,channel,currency_code,gross_subtotal,"
        "discount_total,promotion_total,coupon_total,loyalty_total,tax_total,"
        "rounding_adjustment,total,sale_level_discount,loyalty_redeemed_amount,"
        "version,created_at) VALUES ('s-pos','b1','u-1','op-1','COMPLETED',"
        "'F-1','c-1','POS','MXN','100.0','0','0','0','0','0','0','100.0','0',"
        "'0',1,?)", (fecha,))
    c.execute(
        "INSERT INTO sale_payments (id,sale_id,method,amount,captured_by_user_id,"
        "captured_at) VALUES ('pay-1','s-pos','Tarjeta','100.0','u-1',?)", (fecha,))
    c.execute(
        "INSERT INTO sale_lines (id,sale_id,product_id,product_snapshot,quantity,"
        "quantity_unit,unit_price,discount_total,tax_total,created_at,updated_at)"
        " VALUES ('l-1','s-pos','p-1','{\"name\":\"Pollo\"}','4.0','kg','25.0',"
        "'0','0',?,?)", (fecha, fecha))
    c.commit()
    yield c
    c.close()


def test_dashboard_filter_options_include_pos_payment_methods(conn):
    from backend.application.analytics.queries.bi_dashboard_query_service import (
        BiDashboardQueryService,
    )

    options = BiDashboardQueryService(conn).filter_options()
    assert "Tarjeta" in options["payment_methods"]


def test_forecast_sees_pos_demand(conn):
    from backend.application.analytics.queries.bi_forecast_query_service import (
        BiForecastQueryService,
    )

    daily = BiForecastQueryService(conn)._daily_sales("b1", 3650)
    assert sum(daily) == 100.0, "el forecast estaba ciego a las ventas del POS"


def test_price_elasticity_sees_pos_observations(conn):
    from backend.application.analytics.queries.price_history_query_service import (
        PriceHistoryQueryService,
    )

    points = PriceHistoryQueryService(conn).price_quantity_history(product_id="p-1")
    assert points == [(25.0, 4.0)]


def test_purchase_planning_sees_pos_sales_history(conn):
    from backend.application.queries.purchase_planning_query_service import (
        PurchasePlanningReadService,
    )

    history = PurchasePlanningReadService(conn).sales_history("p-1", "b1", 3650)
    assert [row["total_vendido"] for row in history] == [4.0]


def test_time_series_reader_sees_pos_demand(conn):
    from decimal import Decimal

    from datetime import date

    from backend.infrastructure.db.repositories.forecasting.sqlite_time_series_reader import (
        SERIES_KEY,
        SqliteDailyProductSalesReader,
    )

    series = SqliteDailyProductSalesReader(conn).read_observations(
        SERIES_KEY, {"product": "p-1", "branch": "b1"},
        date(2026, 6, 1), date(2026, 6, 1))
    assert [o.value for o in series] == [Decimal("4.0")]


def test_no_repointed_reader_still_queries_the_legacy_tables():
    """Guardrail de fuente sobre el AST: se inspeccionan los literales SQL, no
    el archivo entero — varios docstrings NOMBRAN las tablas legacy al explicar
    por qué se dejaron de usar, y un `in source` los marcaría como vivos."""
    offenders = []
    for relative in REPOINTED:
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        docstrings = {
            ast.get_docstring(node, clean=False)
            for node in ast.walk(tree)
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef))
        }
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            if node.value in docstrings:
                continue
            for legacy in ("FROM ventas", "JOIN ventas",
                           "FROM detalles_venta", "JOIN detalles_venta"):
                if legacy in node.value:
                    offenders.append(f"{relative}:{node.lineno} -> {legacy}")
    assert not offenders, "\n".join(offenders)


def test_the_ticket_repository_is_deliberately_left_on_legacy():
    """No es un olvido: su comentario dice por qué, y esta prueba lo ata.

    Si alguien lo repunta sin resolver antes `efectivo_recibido`/`cambio` y el
    orden de línea, imprimiría tickets con un cambio falso.
    """
    source = (ROOT / "backend/infrastructure/db/repositories/sales_read_repository.py"
              ).read_text(encoding="utf-8")
    assert "efectivo_recibido" in source
    assert "rowid" in source
    assert "NO se repunta" in source, "debe explicar por qué sigue en legacy"


# ── Consultas MOVIDAS desde el motor legacy (§33 PASO 4) ──────────────────

def _filters():
    from backend.application.analytics.dto.bi_dashboard_dto import DashboardFilters

    return DashboardFilters(preset="custom", date_from="2026-06-01",
                            date_to="2026-06-01", branch_id="b1")


def test_profitability_by_product_moved_from_the_legacy_engine(conn):
    """Era `AnalyticsEngine.product_profitability_detail`. Ahora vive en la
    capa canónica, lee las vistas unificadas y une contra `products`/
    `product_categories` (los maestros canónicos) en vez de `productos`."""
    from backend.application.analytics.queries.bi_sales_query_service import (
        BiSalesQueryService,
    )

    conn.execute("INSERT INTO product_cost VALUES ('p-1','','10.0')")
    conn.execute("INSERT INTO product_categories VALUES ('cat-1','Aves',1)")
    conn.execute("UPDATE products SET category_id='cat-1' WHERE id='p-1'")
    conn.commit()

    rows = BiSalesQueryService(conn).profitability_by_product(_filters())
    assert len(rows) == 1
    row = rows[0]
    assert row["producto_id"] == "p-1"
    assert row["nombre"] == "Pollo"
    assert row["categoria"] == "Aves"
    assert row["unidades"] == 4.0
    assert row["ingresos"] == 100.0
    assert row["costo"] == 40.0          # 4 uds * 10.0 de product_cost
    assert row["margen"] == 60.0


def test_cashier_ranking_moved_from_the_legacy_engine(conn):
    """Era `AnalyticsEngine.get_ranking_cajeros`. La vista resuelve el id de
    cajero a su nombre, así que el ranking sigue mostrando personas."""
    from backend.application.analytics.queries.bi_sales_query_service import (
        BiSalesQueryService,
    )

    rows = BiSalesQueryService(conn).cashier_ranking(_filters())
    assert len(rows) == 1
    assert rows[0]["cajero"] == "cajera1"
    assert rows[0]["num_ventas"] == 1
    assert rows[0]["total_ventas"] == 100.0
    assert rows[0]["ticket_promedio"] == 100.0


def test_the_legacy_engine_no_longer_exposes_the_moved_queries():
    """Movido, no copiado: no pueden quedar dos implementaciones (§3)."""
    import ast

    tree = ast.parse(
        (ROOT / "core/services/analytics/analytics_engine.py").read_text(
            encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    names = {n.name for n in cls.body if isinstance(n, ast.FunctionDef)}
    assert "get_ranking_cajeros" not in names
    assert "product_profitability_detail" not in names


def test_the_legacy_screen_calls_the_canonical_service():
    """La pantalla legacy ya no consume `AnalyticsEngine` para estas dos.

    Sobre el AST y no sobre el texto: los docstrings de la pantalla CITAN los
    métodos retirados para explicar de dónde vienen, y un `in source` los
    marcaría como si siguieran llamándose.
    """
    tree = ast.parse((ROOT / "modulos/reportes_bi_v2.py").read_text(encoding="utf-8"))
    called = {
        node.func.attr for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "cashier_ranking" in called
    assert "profitability_by_product" in called
    assert "get_ranking_cajeros" not in called
    assert "product_profitability_detail" not in called
