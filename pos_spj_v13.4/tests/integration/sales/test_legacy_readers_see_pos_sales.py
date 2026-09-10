"""Lectores legacy de sólo lectura repuntados a la fuente unificada.

No son la capa canónica —viven en `repositories/` y `core/services/`— pero son
LECTORES: no escriben `ventas`, sólo consultan. Mientras sigan sirviendo
pantallas vivas, leer la tabla legacy significa no ver ninguna venta del POS.

El fixture contiene UNA venta y es canónica: cualquier consulta que siguiera
en `ventas` devuelve vacío.
"""
from __future__ import annotations

import ast
import importlib
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
STAMP = "2026-06-01 12:00:00"


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(
        """
        CREATE TABLE usuarios (id TEXT PRIMARY KEY, nombre TEXT, usuario TEXT,
                               password_hash TEXT);
        INSERT INTO usuarios VALUES ('u-1','Ana','cajera1','x');
        CREATE TABLE clientes (id TEXT PRIMARY KEY, nombre TEXT, telefono TEXT,
                              activo INTEGER DEFAULT 1, fecha_nacimiento TEXT);
        INSERT INTO clientes VALUES ('c-1','Cliente Uno','555',1,NULL);
        CREATE TABLE ventas (
            id TEXT PRIMARY KEY, folio TEXT, sucursal_id TEXT, usuario TEXT,
            cliente_id TEXT, subtotal REAL, descuento REAL, total REAL,
            forma_pago TEXT, estado TEXT, fecha DATETIME);
        CREATE TABLE detalles_venta (
            id TEXT PRIMARY KEY, venta_id TEXT, producto_id TEXT, cantidad REAL,
            precio_unitario REAL, descuento REAL, subtotal REAL, unidad TEXT,
            comentarios TEXT, batch_id TEXT, costo_unitario_real REAL,
            margen_real REAL, nombre TEXT);
        CREATE TABLE gastos (id TEXT PRIMARY KEY, monto REAL, fecha TEXT);
        """
    )
    from backend.infrastructure.db.schema.sales_schema import create_sales_schema
    create_sales_schema(c)
    for mod in ("256_sales_unified_read_view", "257_sale_lines_unified_read_view"):
        importlib.import_module(f"migrations.standalone.{mod}").run(c)
    c.execute(
        "INSERT INTO sales (id,branch_id,cashier_user_id,operation_id,status,"
        "sale_number,customer_id,channel,currency_code,gross_subtotal,"
        "discount_total,promotion_total,coupon_total,loyalty_total,tax_total,"
        "rounding_adjustment,total,sale_level_discount,loyalty_redeemed_amount,"
        "version,created_at) VALUES ('s-pos','b1','u-1','op-1','COMPLETED',"
        "'FOLIO-POS-77','c-1','POS','MXN','250.0','0','0','0','0','0','0',"
        "'250.0','0','0',1,?)", (STAMP,))
    c.commit()
    yield c
    c.close()


def test_main_window_search_finds_a_pos_sale_by_folio(conn):
    """La búsqueda global de la ventana principal no encontraba ningún folio
    del POS: buscaba en `ventas` y esas ventas nacen en `sales`."""
    from repositories.main_window_repository import MainWindowReadRepository

    rows = MainWindowReadRepository(conn).buscar_ventas_por_folio("POS-77")
    assert [r["folio"] for r in rows] == ["FOLIO-POS-77"]
    assert float(rows[0]["total"]) == 250.0


def test_ceo_dashboard_revenue_includes_the_pos(conn):
    from core.services.ceo_dashboard import CEODashboard

    total = CEODashboard(db_conn=conn)._q(
        "SELECT COALESCE(SUM(total),0) FROM v_ventas_unificada "
        "WHERE estado='completada' AND DATE(fecha) BETWEEN ? AND ?",
        ["2026-06-01", "2026-06-30"])
    assert total == 250.0


def test_customer_stats_include_pos_purchases(conn):
    from repositories.cliente_repository import ClienteRepository

    stats = ClienteRepository(conn).get_stats("c-1")
    assert stats["num_compras"] == 1
    assert float(stats["total_gastado"]) == 250.0


def test_at_risk_customers_see_the_pos_sale_as_recent_activity(conn):
    """Un cliente que compró hoy EN EL POS no puede aparecer como inactivo."""
    from repositories.loyalty_repository import LoyaltyRepository

    rows = LoyaltyRepository(conn).list_at_risk_customers(days_without_sale=1)
    por_nombre = {r["nombre"]: r for r in rows}
    assert por_nombre["Cliente Uno"]["ultima"] == STAMP, (
        "la última compra del cliente debe verse aunque sea del POS")


def test_the_repointed_readers_no_longer_name_the_legacy_table():
    """Guardrail sobre el AST: los comentarios de estos archivos citan la
    tabla legacy al explicar el cambio, y un `in source` los daría por vivos."""
    repointed = {
        "repositories/main_window_repository.py",
        "core/services/ceo_dashboard.py",
        "repositories/loyalty_repository.py",
    }
    offenders = []
    for relative in sorted(repointed):
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            for legacy in ("FROM ventas", "JOIN ventas"):
                if legacy in node.value:
                    offenders.append(f"{relative}:{node.lineno} -> {legacy}")
    assert not offenders, "\n".join(offenders)


def test_purchase_history_is_deliberately_left_on_legacy():
    """No es olvido: pide `puntos_ganados`, que la vista no expone porque la
    fidelidad es otro bounded context. Su comentario debe decirlo."""
    source = (ROOT / "repositories/cliente_repository.py").read_text(encoding="utf-8")
    assert "puntos_ganados" in source
    assert "NO se repunta" in source
