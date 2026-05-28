import sqlite3
from pathlib import Path

from core.services.stock_reservation_service import StockReservationService
from core.services.inventory_availability_service import InventoryAvailabilityService


def _db():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE branch_inventory(branch_id INTEGER, product_id INTEGER, quantity REAL)")
    db.execute("INSERT INTO branch_inventory(branch_id, product_id, quantity) VALUES(1,1,12)")
    return db


def test_inventory_availability_service_calcula_disponible_para_venta():
    db = _db()
    reservas = StockReservationService(db, branch_id=1)
    reservas.reservar("R-1", [{"id": 1, "cantidad": 5.0}])
    svc = InventoryAvailabilityService(reservas)
    assert svc.disponible_para_venta(1) == 7.0


def test_inventory_availability_service_bulk():
    db = _db()
    reservas = StockReservationService(db, branch_id=1)
    svc = InventoryAvailabilityService(reservas)
    out = svc.disponible_por_producto([1])
    assert out[1] == 12.0


def test_ventas_usa_inventory_availability_service_como_fuente_unica():
    src = Path("pos_spj_v13.4/modulos/ventas.py").read_text(encoding="utf-8")
    assert "InventoryAvailabilityService" in src
    assert "self._inventory_availability.disponible_para_venta(producto_id)" in src
