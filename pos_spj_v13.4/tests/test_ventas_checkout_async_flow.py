from pathlib import Path

import pytest

from presentation.sales.workers.sale_checkout_worker import SaleCheckoutWorker

ROOT = Path(__file__).resolve().parents[1]
VENTAS = ROOT / "modulos" / "ventas.py"


class _UCOK:
    def ejecutar(self, items, datos_pago, sucursal_id, usuario):
        return {"ok": True, "folio": "V1", "venta_id": 1}


def test_ventas_checkout_worker_blocked_for_transactional_sale():
    with pytest.raises(RuntimeError, match="deshabilitado"):
        SaleCheckoutWorker(_UCOK(), [], {}, 1, "cajero")


def test_finalizar_venta_executes_uc_in_main_thread_without_sale_worker():
    src = VENTAS.read_text(encoding="utf-8")
    fn = src.split("def finalizar_venta", 1)[1].split("def _on_checkout_success", 1)[0]
    assert "result = _uc.ejecutar(_items_uc, _dp, self.sucursal_id, usuario)" in fn
    assert "SaleCheckoutWorker" not in fn
    assert "moveToThread" not in fn


def test_imprimir_ticket_no_printer_muestra_error_y_pdf():
    src = VENTAS.read_text(encoding="utf-8")
    fn = src.split("def _imprimir_ticket_consolidado", 1)[1].split("def _imprimir_ticket_hardware", 1)[0]
    assert "PrinterService no está disponible" in fn
    assert "self._guardar_ticket_pdf_async(datos_ticket)" in fn


def test_imprimir_ticket_printer_config_invalid_no_silencioso():
    src = VENTAS.read_text(encoding="utf-8")
    fn = src.split("def _imprimir_ticket_consolidado", 1)[1].split("def _imprimir_ticket_hardware", 1)[0]
    assert "validate_ticket_printer_config" in fn
    assert "Toast.warning(self, \"Impresora no válida\"" in fn


def test_printer_callback_error_llega_a_ui():
    src = VENTAS.read_text(encoding="utf-8")
    fn = src.split("def _imprimir_ticket_consolidado", 1)[1].split("def _imprimir_ticket_hardware", 1)[0]
    assert "on_error=_err" in fn
    assert "QTimer.singleShot(0, lambda: Toast.warning" in fn
    assert "La venta fue completada, pero el ticket no se imprimió" in fn


def test_finalizar_venta_no_llama_qprinter_directo():
    src = VENTAS.read_text(encoding="utf-8")
    fn = src.split("def finalizar_venta", 1)[1].split("def _on_checkout_success", 1)[0]
    assert "QPrinter" not in fn
    assert "QTextDocument" not in fn
