"""Bug 2: los KPIs diarios del Dashboard vienen SOLO de DashboardQueryService.

Verifica la fuente canónica de lectura (ventas/pedidos_whatsapp/productos)
con filtro de sucursal parametrizado (UUID string, sin default entero).
"""
from __future__ import annotations

import sqlite3

from backend.application.queries.dashboard_query_service import DashboardQueryService
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db


def _seed(conn) -> tuple[str, str]:
    suc_a, suc_b = new_uuid(), new_uuid()
    cli = new_uuid()
    conn.execute(
        "INSERT INTO clientes (id, nombre, activo) VALUES (?, 'Cliente D', 1)", (cli,)
    )
    for suc, total, forma in ((suc_a, 100.0, "Efectivo"), (suc_a, 50.0, "Tarjeta"),
                              (suc_b, 30.0, "Efectivo")):
        conn.execute(
            "INSERT INTO ventas (id, folio, cliente_id, sucursal_id, total, "
            " forma_pago, estado, fecha) "
            "VALUES (?, ?, ?, ?, ?, ?, 'completada', datetime('now'))",
            (new_uuid(), f"F-{total}", cli, suc, total, forma),
        )
    # Venta cancelada: jamás cuenta
    conn.execute(
        "INSERT INTO ventas (id, folio, sucursal_id, total, estado, fecha) "
        "VALUES (?, 'F-X', ?, 999, 'cancelada', datetime('now'))",
        (new_uuid(), suc_a),
    )
    # Venta de ayer para el comparativo
    conn.execute(
        "INSERT INTO ventas (id, folio, sucursal_id, total, estado, fecha) "
        "VALUES (?, 'F-A', ?, 80, 'completada', datetime('now','-1 day'))",
        (new_uuid(), suc_a),
    )
    conn.execute(
        "INSERT INTO pedidos_whatsapp (id, numero_whatsapp, estado, total, fecha) "
        "VALUES (?, '5215550000001', 'nuevo', 45.5, datetime('now'))",
        (new_uuid(),),
    )
    conn.execute(
        "INSERT INTO pedidos_whatsapp (id, numero_whatsapp, estado, total, fecha) "
        "VALUES (?, '5215550000002', 'entregado', 10, datetime('now'))",
        (new_uuid(),),
    )
    conn.execute(
        "INSERT INTO productos (id, nombre, existencia, stock_minimo, activo) "
        "VALUES (?, 'Producto bajo', 1, 5, 1)",
        (new_uuid(),),
    )
    return suc_a, suc_b


def test_daily_kpis_global_view():
    conn = make_db()
    _seed(conn)
    kpi = DashboardQueryService(conn).daily_kpis(None)
    assert kpi["ventas_hoy"] == 180.0
    assert kpi["tickets_hoy"] == 3
    assert kpi["ventas_ayer"] == 80.0
    assert kpi["clientes_hoy"] == 1
    assert kpi["pedidos_wa_activos"] == 1
    assert kpi["productos_stock_bajo"] == 1


def test_daily_kpis_filters_by_branch_uuid():
    conn = make_db()
    suc_a, suc_b = _seed(conn)
    qs = DashboardQueryService(conn)
    assert qs.daily_kpis(suc_a)["ventas_hoy"] == 150.0
    assert qs.daily_kpis(suc_b)["ventas_hoy"] == 30.0
    # Cadena vacía == sin filtro (jamás un default entero tipo sucursal 1)
    assert qs.daily_kpis("")["ventas_hoy"] == 180.0


def test_weekly_sales_and_activity_and_orders():
    conn = make_db()
    _seed(conn)
    qs = DashboardQueryService(conn)
    semana = qs.weekly_sales_by_day()
    assert len(semana) == 7
    assert semana[-1]["total"] == 180.0  # hoy

    actividad = qs.recent_activity(limit=8)
    tipos = {e["tipo"] for e in actividad}
    assert "venta" in tipos and "pedido" in tipos

    pedidos = qs.active_whatsapp_orders(limit=8)
    assert len(pedidos) == 1
    assert pedidos[0]["estado"] == "nuevo"
    assert isinstance(pedidos[0]["id"], str)


def test_alerts_and_drivers():
    conn = make_db()
    _seed(conn)
    conn.execute(
        "INSERT INTO drivers (id, nombre, activo, en_ruta) VALUES (?, 'Repa 1', 1, 1)",
        (new_uuid(),),
    )
    qs = DashboardQueryService(conn)
    alertas = qs.operational_alerts()
    assert any("Stock bajo" in a["texto"] for a in alertas)
    drivers = qs.drivers_status()
    assert drivers and drivers[0]["nombre"] == "Repa 1" and drivers[0]["en_ruta"] is True


def test_missing_tables_return_empty_not_crash():
    empty = sqlite3.connect(":memory:")
    qs = DashboardQueryService(empty)
    kpi = qs.daily_kpis(new_uuid())
    assert kpi["ventas_hoy"] == 0.0 and kpi["pedidos_wa_activos"] == 0
    assert qs.weekly_sales_by_day() == []
    assert qs.recent_activity() == []
    assert qs.active_whatsapp_orders() == []
    assert qs.operational_alerts() == []
    assert qs.drivers_status() == []
