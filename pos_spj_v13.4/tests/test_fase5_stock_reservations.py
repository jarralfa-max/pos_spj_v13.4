import sqlite3
from pathlib import Path

from core.services.stock_reservation_service import StockReservationService


def _db():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE branch_inventory(branch_id INTEGER, product_id INTEGER, quantity REAL)")
    db.execute("INSERT INTO branch_inventory(branch_id, product_id, quantity) VALUES(1,1,10)")
    return db


def test_suspender_venta_crea_reserva_activa():
    db = _db()
    svc = StockReservationService(db, branch_id=1)
    rid = svc.reservar("SUSP-1", [{"id": 1, "cantidad": 2.0}])
    st = db.execute("SELECT estado FROM stock_reservas WHERE id=?", (rid,)).fetchone()[0]
    assert st == "activa"


def test_confirmar_reserva_cambia_estado_a_confirmada():
    db = _db()
    svc = StockReservationService(db, branch_id=1)
    rid = svc.reservar("SUSP-2", [{"id": 1, "cantidad": 1.0}])
    svc.confirmar(rid, venta_id=100, folio="F100")
    st = db.execute("SELECT estado FROM stock_reservas WHERE id=?", (rid,)).fetchone()[0]
    assert st == "confirmada"


def test_cancelar_reserva_cambia_estado_a_cancelada():
    db = _db()
    svc = StockReservationService(db, branch_id=1)
    rid = svc.reservar("SUSP-3", [{"id": 1, "cantidad": 1.0}])
    svc.liberar(rid, motivo="cancelada")
    st = db.execute("SELECT estado FROM stock_reservas WHERE id=?", (rid,)).fetchone()[0]
    assert st == "cancelada"


def test_stock_disponible_resta_reservas_activas():
    db = _db()
    svc = StockReservationService(db, branch_id=1)
    svc.reservar("SUSP-4", [{"id": 1, "cantidad": 4.0}])
    assert svc.stock_disponible(1) == 6.0


def test_no_liberada_confirmada_status_string():
    db = _db()
    svc = StockReservationService(db, branch_id=1)
    rid = svc.reservar("SUSP-5", [{"id": 1, "cantidad": 1.0}])
    svc.confirmar(rid, venta_id=200, folio="F200")
    st = db.execute("SELECT estado FROM stock_reservas WHERE id=?", (rid,)).fetchone()[0]
    assert "liberada:" not in st


def test_ui_confirma_reserva_en_venta_reanudada():
    src = Path("pos_spj_v13.4/modulos/ventas.py").read_text(encoding="utf-8")
    assert "self._stock_reservas.confirmar(" in src
    assert 'motivo="confirmada"' not in src
