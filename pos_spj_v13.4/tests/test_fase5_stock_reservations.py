import sqlite3
from pathlib import Path

import pytest

from core.services.stock_reservation_service import StockReservationService


def _db():
    """SALES-9: this fixture had bit-rotted — `stock_disponible()` reads
    `inventory_stock` (not the `branch_inventory` table this fixture used to
    create), and `stock_reservas`/`stock_reserva_detalles` (created by
    `migrations/m000_base_schema.py`, never by this in-memory fixture) didn't
    exist at all, so every test below was failing with "no such table"
    before this fix — unrelated to, and pre-existing before, the
    reservar()-always-fails-with-NOT-NULL bug also fixed in this phase."""
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE inventory_stock(branch_id TEXT, product_id TEXT, quantity REAL)")
    db.execute("INSERT INTO inventory_stock(branch_id, product_id, quantity) VALUES('1','1',10)")
    db.execute("""
        CREATE TABLE stock_reservas (
            id           TEXT NOT NULL PRIMARY KEY,
            folio        TEXT UNIQUE,
            branch_id    TEXT NOT NULL,
            estado       TEXT NOT NULL DEFAULT 'activa',
            payload_json TEXT NOT NULL DEFAULT '[]',
            created_at   TEXT DEFAULT (datetime('now')),
            updated_at   TEXT DEFAULT (datetime('now')),
            expires_at   TEXT DEFAULT (datetime('now', '+30 minutes'))
        )
    """)
    db.execute("""
        CREATE TABLE stock_reserva_detalles (
            id          TEXT NOT NULL PRIMARY KEY,
            reserva_id  TEXT NOT NULL REFERENCES stock_reservas(id),
            producto_id TEXT NOT NULL,
            cantidad    REAL NOT NULL,
            created_at  TEXT DEFAULT (datetime('now'))
        )
    """)
    db.commit()
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


def _src(path: str) -> str:
    return (Path(__file__).resolve().parents[1] / path).read_text(encoding="utf-8")


# modulos/ventas.py (legacy) retirado (SALES-22) — reemplazado por
# frontend/desktop/modules/sales_pos/. Las pruebas que leían su código fuente
# directamente (incluida la única falla preexistente/conocida de este archivo,
# test_ui_pasa_reserva_id_al_uc_antes_de_aplicar_resultado, ya sin sujeto)
# se retiraron con él; StockReservationService y sales_service.py siguen
# vigentes y sus pruebas permanecen abajo.


def test_sales_service_confirma_reserva_en_flujo_transaccional():
    src = _src("core/services/sales_service.py")
    core = src.split("def _execute_sale_core", 1)[1].split("# B. Guardar detalles", 1)[0]
    assert "reservation_id" in core
    assert "StockReservationService(self.db, branch_id=branch_id).confirmar" in core
    assert "reservation_confirmed = True" in core


def test_confirmar_reserva_inactiva_falla_explicito():
    db = _db()
    svc = StockReservationService(db, branch_id=1)
    rid = svc.reservar("SUSP-X", [{"id": 1, "cantidad": 1.0}])
    svc.liberar(rid, motivo="cancelada")
    with pytest.raises(RuntimeError, match="no está activa"):
        svc.confirmar(rid, venta_id=300, folio="F300")


def test_confirm_reservation_called_before_print_or_non_blocking():
    sales_src = _src("core/services/sales_service.py")
    core = sales_src.split("def _execute_sale_core", 1)[1].split("# B. Guardar detalles", 1)[0]
    assert "StockReservationService(self.db, branch_id=branch_id).confirmar" in core


def test_no_liberada_confirmada_status():
    db = _db()
    svc = StockReservationService(db, branch_id=1)
    rid = svc.reservar("SUSP-NO-LIB", [{"id": 1, "cantidad": 1.0}])
    svc.confirmar(rid, venta_id=400, folio="F400")
    st = db.execute("SELECT estado FROM stock_reservas WHERE id=?", (rid,)).fetchone()[0]
    assert st == "confirmada"
    assert "liberada:confirmada" not in st


