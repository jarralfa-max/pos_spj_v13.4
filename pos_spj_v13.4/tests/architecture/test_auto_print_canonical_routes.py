"""Bugs 4 y 8.3: auto-impresión de corte Z y recepción de compra vía PrinterService.

- El corte Z se auto-imprime al generarse (CajaTicketService.enviar_escpos
  dentro de preview_or_print_corte), no solo al pulsar el botón.
- El comprobante de recepción de compra se auto-imprime si hay impresora de
  tickets configurada; el QPrintDialog A5 queda como ruta sin térmica.
- Bug 6: la búsqueda de devoluciones en Ventas autocompleta al 7º carácter.
"""
from __future__ import annotations

from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]


def _code(path: str) -> str:
    text = (APP_ROOT / path).read_text(encoding="utf-8")
    return "\n".join(
        line for line in text.splitlines() if not line.strip().startswith("#")
    )


def test_corte_z_auto_prints_before_preview_dialog():
    code = _code("core/services/caja_ticket_service.py")
    body = code.split("def preview_or_print_corte", 1)[1]
    auto = body.split("QDialog", 1)[0]
    assert "self.enviar_escpos(datos)" in auto, (
        "preview_or_print_corte debe auto-imprimir vía PrinterService antes "
        "de mostrar el diálogo"
    )


def test_caja_ticket_service_has_no_dead_hardware_dependency():
    code = _code("core/services/caja_ticket_service.py")
    assert "hardware_service" not in code
    assert "self._hw" not in code


def test_purchase_reception_auto_prints_via_printer_service():
    code = _code("modulos/compras_pro.py")
    body = code.split("def _ofrecer_impresion_recepcion", 1)[1].split("\n    def ", 1)[0]
    assert 'getattr(self.container, "printer_service"' in body
    assert "has_ticket_printer()" in body
    assert "print_ticket(payload)" in body
    assert '"ticket_type": "compra_recepcion"' in body
    # El auto-print ocurre ANTES de preguntar con QMessageBox
    assert body.index("print_ticket(payload)") < body.index("QMessageBox.question")


def test_ventas_devolucion_search_autocompletes_at_seventh_char():
    code = _code("modulos/ventas.py")
    body = code.split("def abrir_devolucion", 1)[1].split("\n    def ", 1)[0]
    assert ">= 7" in body, "la búsqueda debe dispararse al 7º carácter"
    assert "textChanged.connect" in body
    assert "returnPressed.connect" in body
