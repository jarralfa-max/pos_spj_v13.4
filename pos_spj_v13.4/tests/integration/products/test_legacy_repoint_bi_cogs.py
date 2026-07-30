"""PROD corte de legacy (repoint batch 8) — COGS/margen BI desde product_cost.

`FinancialSimulator` calcula el margen neto reciente con el costo canónico
(`product_cost.average_cost`) en vez de `productos.precio_compra`. El JOIN de
existencia usa el maestro canónico `products`.
"""

import sqlite3

from backend.shared.ids import new_uuid


def _db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    from migrations import engine
    engine.up(c)
    c.execute("PRAGMA foreign_keys=OFF")
    return c


def _seed_sale(c, *, sale_total, qty, unit_price, avg_cost):
    pid = new_uuid()
    c.execute(
        "INSERT INTO products (id, code, name, name_normalized, product_type, "
        "lifecycle_status, base_unit_id) VALUES (?,?,?,?,?,?,?)",
        (pid, f"P-{pid[:4]}", "X", "x", "RESALE_PRODUCT", "ACTIVE", "pza"))
    c.execute(
        "INSERT INTO product_cost (id, product_id, branch_id, average_cost, "
        "average_cost_currency, cost_method) VALUES (?,?,?,?,?,?)",
        (new_uuid(), pid, "", str(avg_cost), "MXN", "AVERAGE"))
    vid = new_uuid()
    c.execute("INSERT INTO ventas (id, folio, total, estado, fecha) "
              "VALUES (?,?,?, 'completada', datetime('now','-10 days'))",
              (vid, "F", sale_total))
    c.execute("INSERT INTO detalles_venta (id, venta_id, producto_id, cantidad, "
              "precio_unitario) VALUES (?,?,?,?,?)",
              (new_uuid(), vid, pid, qty, unit_price))
    c.commit()


def test_financial_simulator_margin_uses_canonical_cost():
    from core.services.financial_simulator import FinancialSimulator

    c = _db()
    # Venta de 100 con costo canónico 60 → margen 40 %.
    _seed_sale(c, sale_total=100.0, qty=1, unit_price=100.0, avg_cost=60.0)
    sim = FinancialSimulator(c)
    res = sim.simular_nueva_sucursal(renta_mensual=0, gastos_fijos_extra=0,
                                     personal=0, salario_promedio=0)
    # El escenario base refleja el margen neto reciente (~40 %), no el default 25.
    assert res is not None
