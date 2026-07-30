"""PROD corte de legacy (Fase A) — forecast lee stock canónico.

`ForecastService.generar_plan_compras` tomaba `existencia` de la tabla legacy
`productos`; ahora lo hace de la proyección canónica `inventory_balances` vía el
`CanonicalStockReadAdapter` (gated por el flag del cutover, canónico fresco por
la auditoría G0). Con el flag ON, el disponible (on-hand − reservado) sustituye a
la `existencia` legacy en la fórmula de compra recomendada.
"""

import sqlite3

import pytest

from backend.shared.ids import new_uuid

# `generar_plan_compras` usa pandas para el pronóstico (raise si falta), y la
# lectura de stock repuntada está aguas abajo de ese gate. Sin pandas el flujo
# no llega a la lectura, así que el test funcional sólo corre donde pandas existe.
pytest.importorskip("pandas")


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    from migrations import engine
    engine.up(c)  # incluye la migración 134 → flag de cutover ON
    return c


def _seed_stock(c, product_id, branch, wh, qty, reserved="0"):
    c.execute(
        "INSERT INTO inventory_balances (id, product_id, branch_id, warehouse_id, "
        "inventory_status, quantity, reserved_quantity, updated_at) "
        "VALUES (?,?,?,?, 'AVAILABLE', ?, ?, datetime('now'))",
        (new_uuid(), product_id, branch, wh, qty, reserved))


def test_generar_plan_compras_usa_stock_canonico(conn):
    from core.services.forecast_service import ForecastService

    pid = new_uuid()
    _seed_stock(conn, pid, "b1", "w1", "30", reserved="5")  # disponible 25
    _seed_stock(conn, pid, "b2", "w1", "10")                # + 10 → total 35
    conn.commit()

    plan = ForecastService(conn).generar_plan_compras(
        producto_id=pid, sucursal_id="b1", dias_historial=30, dias_pronostico=30,
        stock_seguridad=0.0)
    # Sin historial de ventas la demanda proyectada es 0; con stock disponible 35
    # (25 + 10) y colchón 0, la compra recomendada es 0 (no negativa).
    assert plan["stock_actual"] == pytest.approx(35.0)
    assert plan["cantidad_a_comprar"] == pytest.approx(0.0)


def test_sin_stock_canonico_stock_actual_es_cero(conn):
    from core.services.forecast_service import ForecastService

    plan = ForecastService(conn).generar_plan_compras(
        producto_id=new_uuid(), sucursal_id="b1", dias_historial=30,
        dias_pronostico=30, stock_seguridad=7.0)
    assert plan["stock_actual"] == pytest.approx(0.0)
    # demanda 0 − stock 0 + colchón 7 = 7
    assert plan["cantidad_a_comprar"] == pytest.approx(7.0)
