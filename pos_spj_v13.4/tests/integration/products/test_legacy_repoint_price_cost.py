"""PROD corte de legacy (repoint batch 6) — precio/costo canónicos.

- `CotizacionService.productos_activos` lee el precio de venta del contexto
  Pricing (`product_price`, lista BASE, sucursal global `''`) y nombre/unidad de
  `products`, en vez de `productos`.
- `ConfigRepository.calculate_monthly_close_totals` valora la merma con el costo
  canónico (`product_cost.average_cost`) en vez de `productos.precio_compra`.

Backfills 148/150 dieron equivalencia (nombre/unidad en `products`, precio en
`product_price` BASE, costo en `product_cost`).
"""

import sqlite3

import pytest

from backend.shared.ids import new_uuid


@pytest.fixture
def db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    from migrations import engine
    engine.up(c)
    c.execute("PRAGMA foreign_keys=OFF")
    return c


def _seed_product_with_price(db, *, name, sale_price, unit="kg"):
    pid = new_uuid()
    db.execute(
        "INSERT INTO products (id, code, name, name_normalized, product_type, "
        "lifecycle_status, base_unit_id) VALUES (?,?,?,?,?,?,?)",
        (pid, f"C-{pid[:4]}", name, name.lower(), "RESALE_PRODUCT", "ACTIVE", unit))
    base = db.execute("SELECT id FROM price_list WHERE code='BASE'").fetchone()
    if base is None:
        blid = new_uuid()
        db.execute("INSERT INTO price_list (id, code, name, kind, status) "
                   "VALUES (?, 'BASE', 'Base', 'BASE', 'ACTIVE')", (blid,))
    else:
        blid = base["id"]
    db.execute(
        "INSERT INTO product_price (id, price_list_id, product_id, branch_id, "
        "sale_price) VALUES (?,?,?,?,?)",
        (new_uuid(), blid, pid, "", str(sale_price)))
    db.commit()
    return pid


def test_cotizacion_productos_activos_reads_canonical_price(db):
    from core.services.cotizacion_service import CotizacionService

    _seed_product_with_price(db, name="Arrachera", sale_price="235.00")
    rows = CotizacionService(db).productos_activos()
    assert len(rows) == 1
    r = dict(rows[0])
    assert r["nombre"] == "Arrachera"
    assert r["unidad"] == "kg"
    assert r["precio"] == pytest.approx(235.00)   # de product_price (float)


def test_monthly_close_values_waste_with_canonical_cost(db):
    from repositories.config_repository import ConfigRepository

    pid = new_uuid()
    db.execute(
        "INSERT INTO product_cost (id, product_id, branch_id, average_cost, "
        "average_cost_currency, cost_method) VALUES (?,?,?,?,?,?)",
        (new_uuid(), pid, "", "50.00", "MXN", "AVERAGE"))
    db.execute(
        "INSERT INTO mermas (id, producto_id, sucursal_id, cantidad, unidad, motivo, "
        "usuario, operation_id, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (new_uuid(), pid, "b1", 3.0, "kg", "caducidad", "ana", new_uuid(),
         "2026-06-15 10:00:00"))
    db.commit()
    totals = ConfigRepository(db).calculate_monthly_close_totals(
        "2026-06-01 00:00:00", "2026-07-01 00:00:00")
    assert totals["waste"] == pytest.approx(150.0)   # 3 * 50 (product_cost)
