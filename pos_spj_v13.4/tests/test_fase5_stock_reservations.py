import sqlite3
from pathlib import Path

import pytest

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


def _src(path: str) -> str:
    return (Path(__file__).resolve().parents[1] / path).read_text(encoding="utf-8")


def test_ui_no_confirma_reserva_postventa():
    src = _src("modulos/ventas.py")
    aplicar = src.split("def _aplicar_resultado_venta", 1)[1].split("def _on_checkout_failed", 1)[0]
    assert "self._stock_reservas.confirmar(" not in aplicar
    assert "VENTA_CONFIRMADA_RESERVA" not in aplicar
    assert "STOCK_DESCONTADO_RESERVA" not in aplicar
    assert 'motivo="confirmada"' not in src


def test_ui_pasa_reserva_id_al_uc_antes_de_aplicar_resultado():
    src = _src("modulos/ventas.py")
    finalizar = src.split("def finalizar_venta", 1)[1].split("def _on_checkout_success", 1)[0]
    assert "reserva_id=self._reserva_activa_id" in finalizar
    assert "result = _uc.ejecutar" in finalizar


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


def test_reservation_failure_after_sale_does_not_mark_sale_failed():
    src = _src("modulos/ventas.py")
    aplicar = src.split("def _aplicar_resultado_venta", 1)[1].split("def _on_checkout_failed", 1)[0]
    assert "self._stock_reservas.confirmar(" not in aplicar
    assert "self._on_checkout_failed" not in aplicar


def test_confirm_reservation_called_before_print_or_non_blocking():
    sales_src = _src("core/services/sales_service.py")
    core = sales_src.split("def _execute_sale_core", 1)[1].split("# B. Guardar detalles", 1)[0]
    assert "StockReservationService(self.db, branch_id=branch_id).confirmar" in core

    ui_src = _src("modulos/ventas.py")
    aplicar = ui_src.split("def _aplicar_resultado_venta", 1)[1].split("def _on_checkout_failed", 1)[0]
    assert aplicar.find("reservation_confirmed") < aplicar.find("_imprimir_ticket_consolidado(datos_ticket)")


def test_no_liberada_confirmada_status():
    db = _db()
    svc = StockReservationService(db, branch_id=1)
    rid = svc.reservar("SUSP-NO-LIB", [{"id": 1, "cantidad": 1.0}])
    svc.confirmar(rid, venta_id=400, folio="F400")
    st = db.execute("SELECT estado FROM stock_reservas WHERE id=?", (rid,)).fetchone()[0]
    assert st == "confirmada"
    assert "liberada:confirmada" not in st


def test_sale_success_even_if_reservation_warning():
    src = _src("modulos/ventas.py")
    aplicar = src.split("def _aplicar_resultado_venta", 1)[1].split("def _on_checkout_failed", 1)[0]
    warning_idx = aplicar.find("Venta completada, pero la reserva quedó pendiente de revisión")
    toast_idx = aplicar.find("Toast.warning", warning_idx)
    fail_idx = aplicar.find("_on_checkout_failed", warning_idx)
    assert warning_idx != -1
    assert toast_idx != -1
    assert fail_idx == -1


def test_ui_warning_marks_reservation_for_review_without_canceling_sale():
    src = _src("modulos/ventas.py")
    aplicar = src.split("def _aplicar_resultado_venta", 1)[1].split("def _on_checkout_failed", 1)[0]
    warning_idx = aplicar.find("Venta completada, pero la reserva quedó pendiente de revisión")
    revision_idx = aplicar.find("self._stock_reservas.marcar_revision", warning_idx)
    clear_idx = aplicar.find("self._reserva_activa_id = None", revision_idx)
    fail_idx = aplicar.find("_on_checkout_failed", warning_idx)
    assert revision_idx != -1
    assert clear_idx != -1
    assert fail_idx == -1
