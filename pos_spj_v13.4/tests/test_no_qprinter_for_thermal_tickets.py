from pathlib import Path


def _read(rel: str) -> str:
    return Path(rel).read_text(encoding="utf-8")


def test_ventas_no_qprinter_in_thermal_print_path():
    src = _read("modulos/ventas.py")
    start = src.index("def _imprimir_ticket_consolidado")
    end = src.index("def _imprimir_ticket_hardware", start)
    fn = src[start:end]
    assert "QPrinter" not in fn
    assert "QTextDocument" not in fn
    assert "No hay impresora térmica ESC/POS configurada." in fn


def test_ticket_designer_print_sample_uses_printer_service():
    src = _read("modulos/ticket_designer.py")
    start = src.index("def _imprimir_muestra")
    fn = src[start:]
    assert "print_ticket(" in fn
    assert "QPrinter" not in fn
    assert "QPrintDialog" not in fn


def test_delivery_ticket_printer_service_no_qprinter_for_physical():
    src = _read("core/services/ticket_printer_service.py")
    assert "def _print_via_escpos" in src
    assert "QPrinter" not in src
    assert "doc.print_(" not in src


def test_pdf_audit_path_still_present_in_ventas():
    src = _read("modulos/ventas.py")
    assert "def guardar_ticket_pdf" in src
